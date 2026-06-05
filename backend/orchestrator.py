import asyncio
import logging
import os
import re

from dotenv import load_dotenv

from gemini_generation import (
    GeminiQuotaExhaustedError,
    generate_content_with_fallback,
    is_resource_exhausted,
)
from memory_manager import (
    extract_and_store_user_facts,
    get_or_create_chat_session,
    get_recent_history,
    get_user_facts,
    save_chat_message,
)
from persona_prompt import build_master_system_prompt
from rag.retrieve import retrieve_context_and_sources
from semantic_cache import read_cache, write_cache
from text_sanitize import sanitize_api_text

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)

_SCRATCHPAD_RE = re.compile(
    r"<technical_scratchpad\b[^>]*>(.*?)</technical_scratchpad>",
    flags=re.DOTALL | re.IGNORECASE,
)
_FEYNMAN_RESPONSE_RE = re.compile(
    r"<feynman_response\b[^>]*>(.*?)</feynman_response>",
    flags=re.DOTALL | re.IGNORECASE,
)
_FEYNMAN_RESPONSE_OPEN_RE = re.compile(
    r"<feynman_response\b[^>]*>(.*)",
    flags=re.DOTALL | re.IGNORECASE,
)
_XML_TAG_STRIP_RE = re.compile(
    r"</?(?:technical_scratchpad|feynman_response)\b[^>]*>",
    flags=re.IGNORECASE,
)


def _strip_loose_xml_tags(text: str) -> str:
    """Remove any leftover block tag literals from fallback text."""
    cleaned = _XML_TAG_STRIP_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _log_scratchpad(scratchpad: str) -> None:
    """Print internal monologue to the backend terminal (never sent to the UI)."""
    print("\n--- technical_scratchpad (debug only) ---")
    print(scratchpad if scratchpad else "(empty)")
    print("--- end technical_scratchpad ---\n")


def _format_chat_history(messages) -> str:
    if not messages:
        return "(No prior messages in this session.)"
    return "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)


def _build_generation_payload(
    system_prompt: str,
    chat_history: str,
    user_message: str,
) -> str:
    return (
        f"{system_prompt}\n\n"
        f"--- CHAT HISTORY ---\n{chat_history}\n\n"
        f"--- LATEST USER MESSAGE ---\nUSER: {user_message}\n\n"
        "Respond now using the required XML blocks."
    )


def _parse_tagged_response(raw_text: str) -> tuple[str, str]:
    """
    Split Gemini output into hidden scratchpad vs user-facing reply.
    Only feynman_response inner text should reach the API/frontend.
    """
    text = (raw_text or "").strip()

    scratchpad_match = _SCRATCHPAD_RE.search(text)
    scratchpad = scratchpad_match.group(1).strip() if scratchpad_match else ""

    response_match = _FEYNMAN_RESPONSE_RE.search(text)
    if response_match:
        feynman_response = response_match.group(1).strip()
    else:
        # Unclosed tag: take everything after opening feynman_response
        open_match = _FEYNMAN_RESPONSE_OPEN_RE.search(text)
        if open_match:
            feynman_response = open_match.group(1).strip()
            feynman_response = _strip_loose_xml_tags(feynman_response)
        else:
            # No response tags: remove scratchpad block entirely, strip tag literals
            remainder = text
            if scratchpad_match:
                remainder = (text[: scratchpad_match.start()] + text[scratchpad_match.end() :]).strip()
            feynman_response = _strip_loose_xml_tags(remainder)
            logger.warning(
                "Model output missing <feynman_response>; using stripped fallback text."
            )

    _log_scratchpad(scratchpad)

    return (
        sanitize_api_text(scratchpad),
        sanitize_api_text(feynman_response),
    )


def _call_gemini_generate(prompt: str) -> str:
    try:
        return generate_content_with_fallback(prompt)
    except GeminiQuotaExhaustedError:
        raise
    except Exception as exc:
        if is_resource_exhausted(exc):
            print("Primary model quota exhausted. Initiating fallback mechanism...")
            raise GeminiQuotaExhaustedError() from exc
        print(f"Gemini API call failed: {str(exc)}")
        raise


def _sanitize_sources(sources: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for item in sources:
        filename = sanitize_api_text(str(item.get("filename", "")))
        snippet = sanitize_api_text(str(item.get("snippet", "")))
        if not filename and not snippet:
            continue
        cleaned.append(
            {
                "filename": filename or "unknown_source.md",
                "friendly_name": sanitize_api_text(str(item.get("friendly_name", ""))),
                "snippet": snippet,
            }
        )
    return cleaned


async def generate_twin_response(
    session_id: str | None,
    user_message: str,
    mode: str = "tutor",
) -> dict[str, object]:
    """
    Unified orchestration: semantic cache → memory → RAG → persona → Gemini →
    background fact extraction → cache write.

    Args:
        session_id:   Existing session UUID or None (a new one is created).
        user_message: Raw message text from the user.
        mode:         "tutor"   — Feynman teaches (default)
                      "student" — Reverse Feynman: Feynman evaluates the user

    Returns dict with keys:
        session_id, response, sources, is_cached
    """
    session_id = get_or_create_chat_session(session_id)
    save_chat_message(session_id, "user", sanitize_api_text(user_message))

    # ── 1. Semantic cache read ────────────────────────────────────────────────
    # Only cache tutor-mode responses; student-mode evaluations are personal.
    if mode == "tutor":
        cached = await asyncio.to_thread(read_cache, user_message)
        if cached:
            return {
                "session_id": session_id,
                "response": cached,
                "sources": [],
                "is_cached": True,
            }

    # ── 2. Memory + RAG ───────────────────────────────────────────────────────
    recent_history = get_recent_history(session_id, limit=10)
    user_facts = get_user_facts(session_id)

    rag_sources: list[dict] = []
    try:
        rag_context, rag_sources = await asyncio.to_thread(
            retrieve_context_and_sources, user_message
        )
        rag_sources = _sanitize_sources(rag_sources)
    except Exception as exc:
        print(f"RAG retrieval failed: {str(exc)}")
        raise

    # ── 3. Build prompt (mode-aware) ──────────────────────────────────────────
    system_prompt = build_master_system_prompt(user_facts, rag_context, mode=mode)
    history_for_prompt = _format_chat_history(recent_history)
    payload = _build_generation_payload(system_prompt, history_for_prompt, user_message)

    # ── 4. LLM generation ─────────────────────────────────────────────────────
    try:
        raw_output = await asyncio.to_thread(_call_gemini_generate, payload)
    except GeminiQuotaExhaustedError as exc:
        print(f"generate_twin_response quota exhausted: {str(exc)}")
        raise
    except Exception as exc:
        print(f"generate_twin_response Gemini step failed: {str(exc)}")
        raise

    _scratchpad, feynman_response = _parse_tagged_response(raw_output)

    save_chat_message(session_id, "assistant", feynman_response)

    # ── 5. Background tasks: fact extraction + cache write ────────────────────
    messages_for_extraction = get_recent_history(session_id, limit=10)
    asyncio.create_task(
        extract_and_store_user_facts(session_id, messages_for_extraction)
    )

    if mode == "tutor":
        # Fire-and-forget cache population — never blocks the response
        asyncio.create_task(
            asyncio.to_thread(write_cache, user_message, feynman_response)
        )

    return {
        "session_id": session_id,
        "response": feynman_response,
        "sources": rag_sources,
        "is_cached": False,
    }
