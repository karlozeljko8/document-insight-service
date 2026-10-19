
import pytest
from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clear_documents():
    """Keep tests isolated from one another."""
    main.documents.clear()
    main.sessions.clear()
    yield
    main.documents.clear()
    main.sessions.clear()


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_split_into_chunks_returns_page_metadata():
    text = " ".join(f"word{i}" for i in range(250))

    chunks = main.split_into_chunks(text, page_number=2)

    assert len(chunks) == 2
    assert chunks[0]["page"] == 2
    assert chunks[1]["page"] == 2
    assert len(chunks[0]["text"].split()) == 180
    assert len(chunks[1]["text"].split()) == 105


def test_split_into_chunks_handles_empty_text():
    assert main.split_into_chunks("   ", page_number=1) == []


def test_upload_rejects_non_pdf():
    response = client.post(
        "/upload",
        files={
            "file": (
                "notes.txt",
                b"This is not a PDF",
                "text/plain",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported."


def test_upload_rejects_empty_file():
    response = client.post(
        "/upload",
        files={
            "file": (
                "empty.pdf",
                b"",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded file is empty."


def test_ask_returns_404_for_unknown_document():
    response = client.post(
        "/ask",
        json={
            "document_id": "nonexistent-document",
            "question": "How many employees are there?",
        },
    )

    assert response.status_code == 404


def test_ask_rejects_empty_question():
    response = client.post(
        "/ask",
        json={
            "document_id": "nonexistent-document",
            "question": "   ",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Question cannot be empty."

def _fake_document(document_id, session_id, filename="a.pdf"):
    return {
        "document_id": document_id,
        "session_id": session_id,
        "filename": filename,
        "pages": [],
        "chunks": [],
        "index": None,
    }


def test_ask_requires_exactly_one_of_document_or_session():
    response = client.post("/ask", json={"question": "Anything?"})
    assert response.status_code == 400

    response = client.post(
        "/ask",
        json={"document_id": "d", "session_id": "s", "question": "Anything?"},
    )
    assert response.status_code == 400


def test_ask_returns_404_for_unknown_session():
    response = client.post(
        "/ask", json={"session_id": "nope", "question": "Anything?"}
    )

    assert response.status_code == 404


def test_delete_session_removes_its_documents():
    main.add_document(_fake_document("d1", "s1"))
    main.add_document(_fake_document("d2", "s1", "b.pdf"))
    main.add_document(_fake_document("d3", "s2", "c.pdf"))

    response = client.delete("/sessions/s1")

    assert response.status_code == 200
    assert response.json()["documents_removed"] == 2
    assert list(main.documents) == ["d3"]
    assert "s1" not in main.sessions


def test_delete_unknown_session_returns_404():
    assert client.delete("/sessions/missing").status_code == 404


def test_ask_over_session_picks_best_answer_and_reports_filename(monkeypatch):
    main.add_document(_fake_document("d1", "s1", "low.pdf"))
    main.add_document(_fake_document("d2", "s1", "high.pdf"))

    def fake_retrieve(question, document):
        return [{"text": document["filename"], "page": 1, "similarity": 0.5}]

    def fake_qa(question, context, max_answer_len):
        score = 0.9 if context == "high.pdf" else 0.1
        return {"answer": f"from {context}", "score": score}

    monkeypatch.setattr(main, "retrieve_chunks", fake_retrieve)
    monkeypatch.setattr(main, "get_qa_model", lambda: fake_qa)

    response = client.post(
        "/ask", json={"session_id": "s1", "question": "Which file?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "from high.pdf"
    assert body["source"]["filename"] == "high.pdf"
    assert body["retrieved_chunks"] == 2
