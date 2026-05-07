from __future__ import annotations

import hashlib
from pathlib import Path


ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}


def validate_ingest_file(filename: str, content: bytes, max_size_mb: int) -> None:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension: {extension or 'unknown'}. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if not content:
        raise ValueError(f"File is empty: {filename}")
    max_size_bytes = max_size_mb * 1024 * 1024
    if len(content) > max_size_bytes:
        raise ValueError(f"File too large: {filename}. Max size: {max_size_mb} MB")


def build_doc_id(filename: str) -> str:
    digest = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:16]
    stem = Path(filename).stem.lower().replace(" ", "-")
    return f"{stem}-{digest}"


def parse_document_bytes(content: bytes, filename: str) -> list[dict]:
    extension = Path(filename).suffix.lower()
    if extension in {".md", ".markdown", ".txt"}:
        text = content.decode("utf-8", errors="ignore")
        return [{"page": 1, "text": text}]
    if extension == ".pdf":
        try:
            from PyPDF2 import PdfReader
        except ImportError as exc:
            raise ValueError("PDF parsing requires PyPDF2 installed in the runtime") from exc
        import io

        reader = PdfReader(io.BytesIO(content))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append({"page": index, "text": page.extract_text() or ""})
        return pages
    raise ValueError(f"Unsupported file extension: {extension or 'unknown'}")
