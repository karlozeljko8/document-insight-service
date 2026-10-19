"""Pydantic request and response schemas."""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    # Ask about one document OR about every document in a session.
    document_id: str | None = None
    session_id: str | None = None
    question: str = Field(min_length=1, max_length=1000)
