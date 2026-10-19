"""Download all models into the local cache (used at Docker build time)."""

import easyocr
from sentence_transformers import SentenceTransformer
from transformers import pipeline

SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
pipeline("question-answering", model="deepset/roberta-base-squad2")
easyocr.Reader(["en"],  # keep in sync with OCR_LANGUAGES in app/config.py
                gpu=False, verbose=False)
print("Models downloaded.")
