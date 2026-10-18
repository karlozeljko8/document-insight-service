"""Question-answering model loading."""

from transformers import pipeline

qa_model = None

def get_qa_model():
    """Load the QA model only when it is first needed."""
    global qa_model
    if qa_model is None:
        qa_model = pipeline(
            "question-answering",
            model="deepset/roberta-base-squad2",
        )
    return qa_model
