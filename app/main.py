"""FastAPI routes for Document Insight Service."""

from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.chunking import split_into_chunks, split_tables_into_chunks
from app.config import MAX_ANSWER_LEN, MAX_FILE_SIZE, MAX_FILES_PER_UPLOAD
from app.files import (
    detect_file_type,
    extension_type,
    sanitize_filename,
)
from app.pdf_processor import extract_image_pages, extract_pdf_pages
from app.qa import get_qa_model
from app.retrieval import (
    create_document_index,
    retrieve_chunks,
    select_best_row,
)
from app.schemas import AskRequest
from app.state import add_document, documents, remove_session, sessions

app = FastAPI(
    title="Document Insight Service",
    description="Upload PDF or image documents and ask questions about their contents.",
    version="0.5.0",
)


@app.get("/")
def root():
    return {
        "message": "Document Insight Service is running.",
        "docs": "/docs",
    }


def ingest_document(filename: str, data: bytes) -> dict:
    """Validate, extract, chunk and index one PDF or image.

    Images and scanned PDF pages are read with OCR.
    Returns a document record. The caller attaches it to a session.
    Raises HTTPException when the file cannot be used.
    """
    if not filename or extension_type(filename) is None:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, PNG and JPG files are supported.",
        )

    if not data:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"The maximum file size is {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    # The content must match what the extension claims (magic bytes).
    file_type = detect_file_type(data)

    if file_type is None or file_type != extension_type(filename):
        raise HTTPException(
            status_code=400,
            detail="The file content does not match its extension "
            "(expected a real PDF, PNG or JPEG file).",
        )

    if file_type == "pdf":
        pages = extract_pdf_pages(data)
    else:
        pages = extract_image_pages(data)

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

    return {
        "document_id": str(uuid4()),
        "filename": filename,
        "pages": pages,
        "chunks": chunks,
        "index": create_document_index(chunks),
    }


@app.post("/upload")
async def upload_documents(
    files: list[UploadFile] = File(default=[]),
    file: UploadFile | None = File(default=None),  # legacy single-file field
    session_id: str | None = Form(default=None),
):
    """Upload one or more PDF or image (PNG/JPG) files.

    Documents are grouped in a session. Omit session_id to start a new
    session, or pass an existing one to add documents to it.
    """
    uploads = list(files)

    if file is not None:
        uploads.append(file)

    if not uploads:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    if len(uploads) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_FILES_PER_UPLOAD} files per upload.",
        )

    if session_id is not None and session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")

    uploaded = []
    errors = []

    for upload in uploads:
        file_bytes = await upload.read()
        safe_name = sanitize_filename(upload.filename)

        try:
            uploaded.append(ingest_document(safe_name, file_bytes))
        except HTTPException as exc:
            errors.append(
                {
                    "filename": safe_name,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )

    if not uploaded:
        # Nothing usable: report the first problem as the HTTP error.
        raise HTTPException(
            status_code=errors[0]["status_code"],
            detail=errors[0]["detail"],
        )

    session_id = session_id or str(uuid4())

    for record in uploaded:
        record["session_id"] = session_id
        add_document(record)

    summaries = [
        {
            "document_id": record["document_id"],
            "filename": record["filename"],
            "pages_processed": len(record["pages"]),
            "chunks_created": len(record["chunks"]),
            "ocr_pages": sum(1 for page in record["pages"] if page.get("ocr")),
        }
        for record in uploaded
    ]

    return {
        "session_id": session_id,
        "documents": summaries,
        "errors": errors,
        "document_id": summaries[0]["document_id"],
        "filename": summaries[0]["filename"],
        "pages_processed": sum(item["pages_processed"] for item in summaries),
        "chunks_created": sum(item["chunks_created"] for item in summaries),
        "message": "Documents uploaded and indexed successfully.",
    }


@app.get("/documents")
def list_documents(session_id: str | None = None):
    return [
        {
            "document_id": document_id,
            "session_id": document.get("session_id"),
            "filename": document["filename"],
            "pages": len(document["pages"]),
            "chunks": len(document["chunks"]),
        }
        for document_id, document in documents.items()
        if session_id is None or document.get("session_id") == session_id
    ]


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")

    removed = remove_session(session_id)

    return {"session_id": session_id, "documents_removed": removed}


@app.post("/ask")
def ask_question(payload: AskRequest):
    # Validate the request itself first (400), then look up documents (404).
    question = payload.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    if (payload.document_id is None) == (payload.session_id is None):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of document_id or session_id.",
        )

    if payload.session_id is not None:
        if payload.session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found.")

        targets = [
            documents[document_id]
            for document_id in sessions[payload.session_id]
        ]
    else:
        document = documents.get(payload.document_id)

        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Document not found.",
            )

        targets = [document]

    # Step 1: Retrieve relevant context using FAISS, per document.
    candidates = []

    for document in targets:
        for candidate in retrieve_chunks(question, document):
            candidate["filename"] = document["filename"]
            candidate["document_id"] = document["document_id"]
            candidates.append(candidate)

    if not candidates:
        return {
            "answer": "I could not find relevant text in the uploaded documents.",
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
            "answer": "I could not find relevant text in the uploaded documents.",
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
            "document_id": best["document_id"],
            "filename": best["filename"],
            "page": best["page"],
            "text": best["text"],
        },
        "retrieved_chunks": len(candidates),
        "answer_method": "faiss_retrieval_and_qa",
        "debug_candidates": evaluated_candidates,
    }
