"""Download the Hugging Face models into the local cache (used at Docker build time)."""

from sentence_transformers import SentenceTransformer
from transformers import pipeline

SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
pipeline("question-answering", model="deepset/roberta-base-squad2")
print("Models downloaded.")
