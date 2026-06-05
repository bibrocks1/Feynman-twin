"""Sanitize model output before DB persistence and JSON API responses."""

import json
import re
import unicodedata

# Smart / typographic quote variants → ASCII
_QUOTE_MAP = str.maketrans(
    {
        "\u2018": "'",  # left single
        "\u2019": "'",  # right single
        "\u201a": "'",  # single low-9
        "\u201b": "'",  # single high-reversed-9
        "\u2032": "'",  # prime
        "\u2035": "'",  # reversed prime
        "\u201c": '"',  # left double
        "\u201d": '"',  # right double
        "\u201e": '"',  # double low-9
        "\u201f": '"',  # double high-reversed-9
        "\u2033": '"',  # double prime
        "\u00ab": '"',  # «
        "\u00bb": '"',  # »
        "`": "'",
    }
)


def sanitize_api_text(text: str | None) -> str:
    """
    Normalize LLM/XML text so it is safe for SQLite storage and JSON responses.

    - Collapses doubled apostrophes/quotes (e.g. '' → ')
    - Maps curly quotes to ASCII
    - Strips control characters (keeps newline/tab/carriage return)
    - Validates round-trip through json.dumps
    """
    if text is None:
        return ""

    cleaned = unicodedata.normalize("NFKC", str(text)).translate(_QUOTE_MAP)

    # Repeated straight quotes from model formatting artifacts
    cleaned = re.sub(r"''+", "'", cleaned)
    cleaned = re.sub(r'""+', '"', cleaned)

    # Remove ASCII control chars except common whitespace
    cleaned = "".join(
        ch
        for ch in cleaned
        if ch in "\n\r\t" or (ord(ch) >= 32 and ord(ch) != 127)
    )

    # Drop lone surrogate halves / replacement chars that break some parsers
    cleaned = cleaned.replace("\ufffd", "")

    cleaned = cleaned.strip()

    # Prove the string is JSON-serializable (FastAPI uses the same encoder)
    json.dumps(cleaned, ensure_ascii=False)

    return cleaned
