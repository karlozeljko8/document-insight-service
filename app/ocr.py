"""OCR for scanned PDF pages and image uploads (EasyOCR)."""

import fitz
from fastapi import HTTPException

from app.config import MAX_IMAGE_SIDE, OCR_LANGUAGES

_reader = None


def get_ocr_reader():
    """Load EasyOCR only when it is first needed (it is slow and memory-hungry)."""
    global _reader

    if _reader is None:
        import easyocr  # imported lazily so the API starts fast and tests need no models

        _reader = easyocr.Reader(OCR_LANGUAGES, gpu=False, verbose=False)

    return _reader


def ocr_image(png_or_jpeg_bytes: bytes) -> str:
    """Run OCR on an encoded image and return the recognised text, line by line."""
    lines = get_ocr_reader().readtext(png_or_jpeg_bytes, detail=0, paragraph=True)
    return "\n".join(line.strip() for line in lines if line.strip())


def prepare_image(image_bytes: bytes) -> bytes:
    """
    Decode an uploaded PNG/JPEG, drop transparency/CMYK and downscale very large
    images, then return PNG bytes ready for OCR. Raises 400 if it cannot be decoded.
    """
    try:
        pixmap = fitz.Pixmap(image_bytes)

        if pixmap.alpha or pixmap.colorspace is None or pixmap.colorspace.n not in (1, 3):
            pixmap = fitz.Pixmap(fitz.csRGB, pixmap)

        while max(pixmap.width, pixmap.height) > MAX_IMAGE_SIDE:
            pixmap.shrink(1)  # halves both dimensions

        return pixmap.tobytes("png")

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not read this image file.",
        ) from exc
