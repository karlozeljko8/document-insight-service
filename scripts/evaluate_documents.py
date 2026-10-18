import json
import sys
from pathlib import Path

# Add the project root to Python's import path.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app import main


ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "tests" / "eval_cases_third_batch.json"
DOCS_PATH = ROOT / "sample_docs"
RESULTS_PATH = ROOT / "evaluation_results.json"


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def run_evaluation():
    with CASES_PATH.open("r", encoding="utf-8") as file:
        cases = json.load(file)

    client = TestClient(main.app)
    uploaded_documents = {}
    results = []

    try:
        # Upload each PDF once, using the real API endpoint.
        for case in cases:
            filename = case["document"]

            if filename in uploaded_documents:
                continue

            pdf_path = DOCS_PATH / filename

            if not pdf_path.is_file():
                raise FileNotFoundError(
                    f"Evaluation PDF not found: {pdf_path}"
                )

            with pdf_path.open("rb") as pdf:
                response = client.post(
                    "/upload",
                    files={
                        "file": (
                            filename,
                            pdf,
                            "application/pdf",
                        )
                    },
                )

            if response.status_code != 200:
                raise RuntimeError(
                    f"Upload failed for {filename}: "
                    f"{response.status_code} {response.text}"
                )

            uploaded_documents[filename] = response.json()[
                "document_id"
            ]

            print(f"Uploaded: {filename}")

        # Ask all evaluation questions.
        for number, case in enumerate(cases, start=1):
            response = client.post(
                "/ask",
                json={
                    "document_id": uploaded_documents[
                        case["document"]
                    ],
                    "question": case["question"],
                },
            )

            if response.status_code != 200:
                results.append(
                    {
                        **case,
                        "actual_answer": None,
                        "status": "FAIL",
                        "error": response.text,
                    }
                )
                continue

            data = response.json()
            answer = data.get("answer", "")
            source = data.get("source")
            answer_normalized = normalize(answer)

            matches_expected = any(
                normalize(term) in answer_normalized
                for term in case["expected_any"]
            )

            if case["manual_review"]:
                status = "REVIEW"
            else:
                status = "PASS" if matches_expected else "FAIL"

            result = {
                "question_number": number,
                "document": case["document"],
                "question": case["question"],
                "expected_answer": case["expected_answer"],
                "actual_answer": answer,
                "status": status,
                "source": source,
                "retrieved_chunks": data.get("retrieved_chunks"),
                "answer_method": data.get("answer_method"),
                "expected_fact_matched": (
                    matches_expected
                    if not case["manual_review"]
                    else None
                ),
            }

            results.append(result)

            print(f"\n[{status}] Question {number}")
            print(f"Q: {case['question']}")
            print(f"Expected: {case['expected_answer']}")
            print(f"Actual: {answer}")
            print(f"Source: {source}")

        RESULTS_PATH.write_text(
            json.dumps(results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        passed = sum(r["status"] == "PASS" for r in results)
        failed = sum(r["status"] == "FAIL" for r in results)
        review = sum(r["status"] == "REVIEW" for r in results)

        print("\n" + "=" * 55)
        print("DOCUMENT EVALUATION SUMMARY")
        print("=" * 55)
        print(f"Total questions: {len(results)}")
        print(f"Passed automatically: {passed}")
        print(f"Failed automatically: {failed}")
        print(f"Require manual review: {review}")
        print(f"Detailed report: {RESULTS_PATH}")

    finally:
        # Avoid leaving evaluation documents in in-memory storage.
        main.documents.clear()


if __name__ == "__main__":
    run_evaluation()