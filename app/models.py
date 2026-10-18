"""Lazy loading for the embedding model."""

from sentence_transformers import SentenceTransformer

embedding_model = None

def get_embedding_model():
    """Load the embedding model only when it is first needed."""
    global embedding_model
    if embedding_model is None:
        embedding_model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
    return embedding_model
