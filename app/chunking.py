"""Text and table chunking utilities."""

from app.config import CHUNK_OVERLAP_WORDS, CHUNK_WORDS


def split_into_chunks(
    text: str,
    page_number: int,
) -> list[dict]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []

    if not words:
        return chunks

    start = 0

    while start < len(words):
        end = min(start + CHUNK_WORDS, len(words))
        chunk_text = " ".join(words[start:end]).strip()

        if chunk_text:
            chunks.append(
                {
                    "text": chunk_text,
                    "page": page_number,
                }
            )

        if end == len(words):
            break

        start = end - CHUNK_OVERLAP_WORDS

    return chunks


def split_tables_into_chunks(
    tables_text: str,
    page_number: int,
) -> list[dict]:
    """
    Build table chunks from the "one sentence per row" text. Each chunk keeps
    its rows in "rows". Large tables are split into groups of rows that fit
    CHUNK_WORDS so the embedding model does not truncate them.
    """
    chunks = []

    for table_block in tables_text.split("\n\n"):
        rows = [row.strip() for row in table_block.splitlines() if row.strip()]

        group = []
        group_words = 0

        for row in rows + [None]:
            row_words = len(row.split()) if row else 0

            if group and (row is None or group_words + row_words > CHUNK_WORDS):
                chunks.append(
                    {
                        "text": "\n".join(group),
                        "page": page_number,
                        "rows": group,
                    }
                )
                group, group_words = [], 0

            if row:
                group.append(row)
                group_words += row_words

    return chunks
