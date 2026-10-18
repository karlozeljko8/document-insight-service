"""PDF text and table extraction."""

import re

import fitz
from fastapi import HTTPException


def clean_cell(value) -> str:
    """Normalise a table cell to a single-line string."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def table_to_text(table) -> str:
    """
    Convert a PyMuPDF table into one sentence per row, keeping the
    row/column relationship, e.g.:

        "Country: Germany. Employees at 31 Dec 2025: 980."

    This avoids the flat word stream ("Denmark 1,420 Germany 980 ...") in which
    an extractive QA model cannot tell which number belongs to which row.
    """
    rows = table.extract()

    if not rows:
        return ""

    rows = [[clean_cell(cell) for cell in row] for row in rows]

    # A table with a single row has no header to pair with.
    if len(rows) < 2:
        return " | ".join(cell for cell in rows[0] if cell)

    header = [
        cell if cell else f"Column {index + 1}"
        for index, cell in enumerate(rows[0])
    ]

    lines = []

    for row in rows[1:]:
        parts = [
            f"{head}: {cell}"
            for head, cell in zip(header, row)
            if cell
        ]

        if parts:
            lines.append(". ".join(parts) + ".")

    return "\n".join(lines)


def extract_page_content(page) -> tuple[str, str]:
    """
    Return (body_text, tables_text) for one page.

    Table regions are removed from the body text and converted separately,
    so the same content is not indexed twice in two different shapes.
    """
    tables = []

    try:
        tables = page.find_tables().tables
    except Exception:
        tables = []

    if not tables:
        body = page.get_text("text", sort=True)
        return body, ""

    table_rects = [fitz.Rect(table.bbox) for table in tables]

    body_blocks = []

    # Block tuple: (x0, y0, x1, y1, text, block_no, block_type); type 0 = text.
    for block in page.get_text("blocks", sort=True):
        if block[6] != 0:
            continue

        block_rect = fitz.Rect(block[:4])

        if any(block_rect.intersects(rect) for rect in table_rects):
            continue

        body_blocks.append(block[4])

    body = "\n".join(body_blocks)
    tables_text = "\n\n".join(
        text for text in (table_to_text(table) for table in tables) if text
    )

    return body, tables_text


def normalise_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_pages(pdf_bytes: bytes) -> list[dict]:
    """Extract text from each PDF page while preserving page numbers."""
    pages = []

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            for page_number, page in enumerate(pdf, start=1):
                body, tables_text = extract_page_content(page)

                body = normalise_text(body)
                tables_text = normalise_text(tables_text)

                if body or tables_text:
                    pages.append(
                        {
                            "page": page_number,
                            "text": body,
                            "tables_text": tables_text,
                        }
                    )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not read this PDF file.",
        ) from exc

    if not pages:
        raise HTTPException(
            status_code=400,
            detail=(
                "No selectable text was found in this PDF. "
                "Scanned PDFs require OCR, which is not implemented yet."
            ),
        )

    return pages
