"""FastAPI routes for Document Insight Service."""

from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.chunking import split_into_chunks, split_tables_into_chunks
from app.config import MAX_ANSWER_LEN, MAX_FILE_SIZE
from app.pdf_processor import extract_pdf_pages
from app.qa import get_qa_model
from app.retrieval import (
    create_document_index,
    retrieve_chunks,
    select_best_row,
)
from app.schemas import AskRequest
from app.state import documents

app = FastAPI(
    title="Document Insight Service",
    description="Upload PDF documents and ask questions about their contents.",
    version="0.5.0",
)


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


@app.post("/ask")
def ask_question(payload: AskRequest):
    # Validate the request itself first (400), then look up the document (404).
    question = payload.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    document = documents.get(payload.document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
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
            item["similarity"],
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
        "debug_candidates": evaluated_candidates,
    }
