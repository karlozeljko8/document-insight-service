
import re
from uuid import uuid4

import faiss
import fitz
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from requests import request
from sentence_transformers import SentenceTransformer
from transformers import pipeline


app = FastAPI(
    title="Document Insight Service",
    description="Upload PDF documents and ask questions about their contents.",
    version="0.5.0",
)

MAX_FILE_SIZE = 10 * 1024 * 1024
CHUNK_WORDS = 180
CHUNK_OVERLAP_WORDS = 35
TOP_K = 5
MAX_ANSWER_LEN = 60

# In-memory storage for this initial version.
documents = {}

embedding_model = None
qa_model = None


def get_embedding_model():
    global embedding_model

    if embedding_model is None:
        embedding_model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

    return embedding_model



def get_qa_model():
    global qa_model

    if qa_model is None:
        # Previous model — kept for easy comparison:
        # qa_model = pipeline(
        #     "question-answering",
        #     model="distilbert/distilbert-base-cased-distilled-squad",
        # )

        # New QA model:
        qa_model = pipeline(
            "question-answering",
            model="deepset/roberta-base-squad2",
        )

    return qa_model


# ------------------------------------------------------------------------
# PDF extraction (with table-aware handling)
# ------------------------------------------------------------------------

def clean_cell(value) -> str:
    """Normalise a table cell to a single-line string."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def table_to_text(table) -> str:
    """
    Convert a PyMuPDF table into one sentence per row, keeping the
    row/column relationship, e.g.:

        "Country: Germany. Employees at 31 Dec 2025: 980."

    This avoids the flat word stream ("Denmark 1,420 Germany 980 ...") in which
    an extractive QA model cannot tell which number belongs to which row.
    """
    rows = table.extract()

    if not rows:
        return ""

    rows = [[clean_cell(cell) for cell in row] for row in rows]

    # A table with a single row has no header to pair with.
    if len(rows) < 2:
        return " | ".join(cell for cell in rows[0] if cell)

    header = [
        cell if cell else f"Column {index + 1}"
        for index, cell in enumerate(rows[0])
    ]

    lines = []

    for row in rows[1:]:
        parts = [
            f"{head}: {cell}"
            for head, cell in zip(header, row)
            if cell
        ]

        if parts:
            lines.append(". ".join(parts) + ".")

    return "\n".join(lines)


def extract_page_content(page) -> tuple[str, str]:
    """
    Return (body_text, tables_text) for one page.

    Table regions are removed from the body text and converted separately,
    so the same content is not indexed twice in two different shapes.
    """
    tables = []

    try:
        tables = page.find_tables().tables
    except Exception:
        tables = []

    if not tables:
        body = page.get_text("text", sort=True)
        return body, ""

    table_rects = [fitz.Rect(table.bbox) for table in tables]

    body_blocks = []

    # Block tuple: (x0, y0, x1, y1, text, block_no, block_type); type 0 = text.
    for block in page.get_text("blocks", sort=True):
        if block[6] != 0:
            continue

        block_rect = fitz.Rect(block[:4])

        if any(block_rect.intersects(rect) for rect in table_rects):
            continue

        body_blocks.append(block[4])

    body = "\n".join(body_blocks)
    tables_text = "\n\n".join(
        text for text in (table_to_text(table) for table in tables) if text
    )

    return body, tables_text


def normalise_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_pages(pdf_bytes: bytes) -> list[dict]:
    """Extract text from each PDF page while preserving page numbers."""
    pages = []

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            for page_number, page in enumerate(pdf, start=1):
                body, tables_text = extract_page_content(page)

                body = normalise_text(body)
                tables_text = normalise_text(tables_text)

                if body or tables_text:
                    pages.append(
                        {
                            "page": page_number,
                            "text": body,
                            "tables_text": tables_text,
                        }
                    )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not read this PDF file.",
        ) from exc

    if not pages:
        raise HTTPException(
            status_code=400,
            detail=(
                "No selectable text was found in this PDF. "
                "Scanned PDFs require OCR, which is not implemented yet."
            ),
        )

    return pages


# ------------------------------------------------------------------------
# Chunking and indexing
# ------------------------------------------------------------------------

def split_into_chunks(
    text: str,
    page_number: int,
) -> list[dict]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []

    if not words:
        return chunks

    start = 0

    while start < len(words):
        end = min(start + CHUNK_WORDS, len(words))
        chunk_text = " ".join(words[start:end]).strip()

        if chunk_text:
            chunks.append(
                {
                    "text": chunk_text,
                    "page": page_number,
                }
            )

        if end == len(words):
            break

        start = end - CHUNK_OVERLAP_WORDS

    return chunks


def split_tables_into_chunks(
    tables_text: str,
    page_number: int,
) -> list[dict]:
    """
    Build table chunks from the "one sentence per row" text. Each chunk keeps
    its rows in "rows". Large tables are split into groups of rows that fit
    CHUNK_WORDS so the embedding model does not truncate them.
    """
    chunks = []

    for table_block in tables_text.split("\n\n"):
        rows = [row.strip() for row in table_block.splitlines() if row.strip()]

        group = []
        group_words = 0

        for row in rows + [None]:
            row_words = len(row.split()) if row else 0

            if group and (row is None or group_words + row_words > CHUNK_WORDS):
                chunks.append(
                    {
                        "text": "\n".join(group),
                        "page": page_number,
                        "rows": group,
                    }
                )
                group, group_words = [], 0

            if row:
                group.append(row)
                group_words += row_words

    return chunks


def select_best_row(question: str, rows: list[str]) -> str:
    """Pick the table row most similar to the question."""
    if len(rows) == 1:
        return rows[0]

    model = get_embedding_model()

    embeddings = model.encode(
        [question] + rows,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    scores = embeddings[1:] @ embeddings[0]

    return rows[int(np.argmax(scores))]


def create_document_index(chunks: list[dict]):
    """Create a FAISS index using cosine similarity."""
    model = get_embedding_model()

    texts = [chunk["text"] for chunk in chunks]

    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    embeddings = np.asarray(embeddings, dtype=np.float32)

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    return index


def retrieve_chunks(
    question: str,
    document: dict,
) -> list[dict]:
    """Retrieve the most semantically relevant chunks from FAISS."""
    model = get_embedding_model()

    query_embedding = model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    query_embedding = np.asarray(
        query_embedding,
        dtype=np.float32,
    )

    number_to_retrieve = min(TOP_K, len(document["chunks"]))

    similarities, indices = document["index"].search(
        query_embedding,
        number_to_retrieve,
    )

    results = []

    for similarity, chunk_index in zip(
        similarities[0],
        indices[0],
    ):
        if chunk_index < 0:
            continue

        chunk = document["chunks"][int(chunk_index)]

        results.append(
            {
                "text": chunk["text"],
                "page": chunk["page"],
                "rows": chunk.get("rows"),
                "similarity": float(similarity),
            }
        )

    return results


# ------------------------------------------------------------------------
# API
# ------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Document Insight Service is running.",
        "docs": "/docs",
    }


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported.",
        )

    pdf_bytes = await file.read()

    if not pdf_bytes:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="The maximum file size is 10 MB.",
        )

    pages = extract_pdf_pages(pdf_bytes)

    chunks = []

    for page in pages:
        # Body text and table text are chunked separately, so table rows
        # are never blended into surrounding prose.
        chunks.extend(split_into_chunks(page["text"], page["page"]))

        # Table chunks keep their rows. The whole table is indexed as ONE chunk
        # (so retrieval and ranking behave like normal text), but at question
        # time only the best-matching row is passed to the QA model.
        chunks.extend(
            split_tables_into_chunks(page["tables_text"], page["page"])
        )

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="Could not create searchable text chunks.",
        )

    index = create_document_index(chunks)
    document_id = str(uuid4())

    documents[document_id] = {
        "filename": file.filename,
        "pages": pages,
        "chunks": chunks,
        "index": index,
    }

    return {
        "document_id": document_id,
        "filename": file.filename,
        "pages_processed": len(pages),
        "chunks_created": len(chunks),
        "message": "Document uploaded and indexed successfully.",
    }


@app.get("/documents")
def list_documents():
    return [
        {
            "document_id": document_id,
            "filename": document["filename"],
            "pages": len(document["pages"]),
            "chunks": len(document["chunks"]),
        }
        for document_id, document in documents.items()
    ]


class AskRequest(BaseModel):
    document_id: str
    question: str = Field(min_length=1, max_length=1000)


@app.post("/ask")
def ask_question(payload: AskRequest):
    document = documents.get(payload.document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    question = payload.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    # Step 1: Retrieve relevant context using FAISS.
    candidates = retrieve_chunks(question, document)

    if not candidates:
        return {
            "answer": "I could not find relevant text in this document.",
            "source": None,
            "retrieved_chunks": 0,
            "debug_candidates": [],
        }


    # Step 2: Extract an answer from each retrieved chunk.
    qa = get_qa_model()
    evaluated_candidates = []

    for candidate in candidates:
        # For table chunks, run QA on the best-matching row only.
        # "text" is replaced by that row; the full table stays in "table_text".
        if candidate.get("rows"):
            candidate["table_text"] = candidate["text"]
            candidate["text"] = select_best_row(question, candidate["rows"])

        result = qa(
            question=question,
            context=candidate["text"],
            max_answer_len=MAX_ANSWER_LEN,
        )

        evaluated_candidates.append(
            {
                **candidate,
                "answer": result.get("answer", "").strip(),
                "qa_confidence": float(result.get("score", 0.0)),
            }
        )

    answered = [item for item in evaluated_candidates if item["answer"]]

    if not answered:
        return {
            "answer": "I could not find relevant text in this document.",
            "source": None,
            "retrieved_chunks": len(candidates),
            "answer_method": "faiss_retrieval_and_qa",
            "debug_candidates": evaluated_candidates,
        }

    # Prefer the answer with the highest QA confidence,
    # using retrieval similarity as a tie-breaker.
    best = max(
        answered,
        key=lambda item: (
            item["qa_confidence"],
        ),
    )
    return {
        "answer": best["answer"],
        "source": {
            "filename": document["filename"],
            "page": best["page"],
            "text": best["text"],
        },
        "retrieved_chunks": len(candidates),
        "answer_method": "faiss_retrieval_and_qa",
        "debug_candidates": evaluated_candidates,
    }