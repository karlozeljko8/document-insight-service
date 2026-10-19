"""Application configuration constants."""

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 10
CHUNK_WORDS = 180
CHUNK_OVERLAP_WORDS = 35
TOP_K = 5
MAX_ANSWER_LEN = 60

# --- OCR (scanned PDF pages and image uploads) ---
OCR_LANGUAGES = ["en"]
OCR_DPI = 200  # resolution used to render scanned PDF pages for OCR
MAX_OCR_PAGES = 20  # upper bound of OCR'd pages per PDF, to keep latency bounded
MAX_IMAGE_SIDE = 3000  # larger images are downscaled before OCR
