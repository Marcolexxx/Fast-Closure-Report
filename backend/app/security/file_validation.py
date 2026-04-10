from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ALLOWED_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp", ".heic",
    ".pdf",
    ".zip",
    ".csv", ".xlsx", ".xls", ".ods",
}

# Max image pixel limit (50MP)
MAX_IMAGE_PIXELS = 50_000 * 10_000
# Max file size: 100 MB
MAX_FILE_SIZE = 100 * 1024 * 1024


def sniff_magic(header: bytes) -> str:
    """Returns a rough content type from the first 16 bytes (magic bytes)."""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"%PDF-"):
        return "pdf"
    if header.startswith(b"PK\x03\x04"):
        return "zip"
    # HEIC/HEIF — ftyp box starts at offset 4
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "heic"
    return "unknown"


@dataclass(frozen=True)
class FileValidator:
    max_bytes: int = MAX_FILE_SIZE

    def validate(self, filename: str, content: bytes) -> None:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise ValueError(f"File extension '{ext}' not allowed")
        if len(content) > self.max_bytes:
            raise ValueError("File too large (max 100 MB)")
        kind = sniff_magic(content[:16])
        if ext in {".png"} and kind != "png":
            raise ValueError("Magic bytes mismatch for png")
        if ext in {".jpg", ".jpeg"} and kind != "jpeg":
            raise ValueError("Magic bytes mismatch for jpeg")
        if ext == ".pdf" and kind != "pdf":
            raise ValueError("Magic bytes mismatch for pdf")
        if ext == ".zip" and kind != "zip":
            raise ValueError("Magic bytes mismatch for zip")


def validate_upload(content: bytes, ext: str) -> None:
    """Convenience function: validate raw content by extension string (no dot)."""
    dummy_name = f"upload.{ext}"
    FileValidator().validate(dummy_name, content)

