
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
    version="0.4.0",
)

MAX_FILE_SIZE = 10 * 1024 * 1024
CHUNK_WORDS = 180
CHUNK_OVERLAP_WORDS = 35
TOP_K = 5

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


def extract_pdf_pages(pdf_bytes: bytes) -> list[dict]:
    """Extract text from each PDF page while preserving page numbers."""
    pages = []

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            for page_number, page in enumerate(pdf, start=1):
                text = page.get_text("text", sort=True)
                text = re.sub(r"[ \t]+", " ", text)
                text = re.sub(r"\n{3,}", "\n\n", text).strip()

                if text:
                    pages.append(
                        {
                            "page": page_number,
                            "text": text,
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
                "similarity": float(similarity),
            }
        )

    return results


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
        chunks.extend(
            split_into_chunks(
                page["text"],
                page["page"],
            )
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
def ask_question(request: AskRequest):
    document = documents.get(request.document_id)

    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )

    document_id = request.document_id

    if document_id not in documents:
        raise HTTPException(
            status_code=404,
            detail="Document not found."
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
        result = qa(
            question=question,
            context=candidate["text"],
        )

        evaluated_candidates.append(
            {
                **candidate,
                "answer": result.get("answer", "").strip(),
                "qa_confidence": float(result.get("score", 0.0)),
            }
        )

    # Rank primarily by retrieval relevance.
    # QA confidence is retained for inspection, not added
    # directly to the FAISS similarity score.
    evaluated_candidates.sort(
        key=lambda item: item["similarity"],
        reverse=True,
    )

    # Among candidates with strong retrieval relevance,
    # prefer the answer with the highest QA confidence.
    best = max(
        evaluated_candidates,
        key=lambda item: (
            item["similarity"],
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