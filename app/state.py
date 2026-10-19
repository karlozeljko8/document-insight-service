"""In-memory application state."""

# Documents remain in memory, as required by the current project scope.
documents: dict = {}

# A session groups the documents uploaded together: session_id -> [document_id, ...]
sessions: dict[str, list[str]] = {}


def add_document(record: dict) -> None:
    """Store a document and attach it to its session (record["session_id"])."""
    documents[record["document_id"]] = record
    sessions.setdefault(record["session_id"], []).append(record["document_id"])


def remove_session(session_id: str) -> int:
    """Delete a session and its documents. Returns the number of documents removed."""
    document_ids = sessions.pop(session_id)

    for document_id in document_ids:
        documents.pop(document_id, None)

    return len(document_ids)
