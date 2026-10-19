"""Upload validation helpers: file type detection and filename sanitising."""

import re
from pathlib import PurePosixPath, PureWindowsPath

# Magic bytes: the content decides the type, not the extension or Content-Type.
_SIGNATURES = {
    "pdf": (b"%PDF-",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpeg": (b"\xff\xd8\xff",),
}

ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
}

MAX_FILENAME_LENGTH = 100


def detect_file_type(data: bytes) -> str | None:
    """Return "pdf", "png" or "jpeg" based on the file's first bytes, else None."""
    for file_type, signatures in _SIGNATURES.items():
        if data.startswith(signatures):
            return file_type
    return None


def extension_type(filename: str) -> str | None:
    """Return the file type implied by the filename extension, else None."""
    dot = filename.rfind(".")
    return ALLOWED_EXTENSIONS.get(filename[dot:].lower()) if dot != -1 else None


def sanitize_filename(filename: str | None) -> str:
    """
    Make a client-supplied filename safe to store, log and show.

    Drops any directory part (both forward and back slashes), replaces everything
    except letters, digits, dot, dash, underscore and space, and limits the length
    while keeping the extension.
    """
    name = PurePosixPath(PureWindowsPath(filename or "").name).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")

    if len(name) > MAX_FILENAME_LENGTH:
        dot = name.rfind(".")
        extension = name[dot:] if 0 < dot and len(name) - dot <= 10 else ""
        name = name[: MAX_FILENAME_LENGTH - len(extension)] + extension

    return name
