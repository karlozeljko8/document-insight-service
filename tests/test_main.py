
import pytest
from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clear_documents():
    """Keep tests isolated from one another."""
    main.documents.clear()
    yield
    main.documents.clear()


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