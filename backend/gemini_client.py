"""Shared Gemini client factory with Windows SSL trust-store workaround."""

import os
import ssl

from google import genai
from google.genai.types import HttpOptions


def _unverified_ssl_context() -> ssl.SSLContext:
    """Bypass broken local CA stores (same pattern as rag/ingest.py)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def create_gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")

    ssl_ctx = _unverified_ssl_context()
    return genai.Client(
        api_key=api_key,
        http_options=HttpOptions(
            client_args={"verify": ssl_ctx},
            async_client_args={"verify": ssl_ctx},
        ),
    )
