"""Pydantic request and response schemas."""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    document_id: str
    question: str = Field(min_length=1, max_length=1000)
