from __future__ import annotations

import re
import unicodedata


def remove_accents(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(char) != "Mn"
    )


def normalize(text: str) -> str:
    normalized = remove_accents(text or "")
    normalized = (
        normalized.strip()
        .lower()
        .replace("¿", "")
        .replace("?", "")
        .replace('"', "")
        .replace("'", "")
    )
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
