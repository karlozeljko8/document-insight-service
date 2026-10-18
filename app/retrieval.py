"""FAISS indexing and semantic retrieval."""

import faiss
import numpy as np

from app.config import TOP_K
from app.models import get_embedding_model


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
