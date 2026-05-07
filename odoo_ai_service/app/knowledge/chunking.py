from __future__ import annotations


def split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    clean_text = (text or "").strip()
    if not clean_text:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[str] = []
    start = 0
    total = len(clean_text)
    while start < total:
        end = min(start + chunk_size, total)
        chunk = clean_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= total:
            break
        start = end - overlap
    return chunks


def build_chunks(
    pages: list[dict],
    doc_id: str,
    doc_name: str,
    source_type: str,
    module: str | None,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[dict]:
    chunk_rows: list[dict] = []
    chunk_index = 0
    for page in pages:
        for chunk_text in split_text(page.get("text", ""), chunk_size=chunk_size, overlap=overlap):
            chunk_index += 1
            page_number = page.get("page")
            normalized_page = page_number if isinstance(page_number, int) else None
            chunk_rows.append(
                {
                    "id": f"{doc_id}-p{normalized_page or 0}-c{chunk_index:04d}",
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "source_type": source_type,
                    "page": normalized_page,
                    "module": module,
                    "chunk_index": chunk_index,
                    "content": chunk_text,
                }
            )
    return chunk_rows
