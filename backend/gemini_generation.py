"""Resilient Gemini text generation with model fallback and quota retry."""

import logging
import time

from google.genai import errors as genai_errors

from gemini_client import create_gemini_client

logger = logging.getLogger(__name__)

# Raw model IDs for google-genai SDK (no "models/" prefix)
PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.0-flash"
TERTIARY_MODEL = "gemini-1.5-flash"
MODEL_CHAIN = (PRIMARY_MODEL, FALLBACK_MODEL, TERTIARY_MODEL)

FINAL_RETRY_SLEEP_SEC = 2

USER_FRIENDLY_QUOTA_MESSAGE = (
    "The Feynman twin is experiencing high demand on the AI service right now. "
    "Please wait a few seconds and try again."
)


class GeminiQuotaExhaustedError(RuntimeError):
    """Raised when primary, fallback, and final retry all hit rate limits."""

    def __init__(self, message: str = USER_FRIENDLY_QUOTA_MESSAGE):
        super().__init__(message)
        self.user_message = message


def is_resource_exhausted(exc: BaseException) -> bool:
    """True for 429/503 / RESOURCE_EXHAUSTED / UNAVAILABLE from the google-genai SDK.

    Google's API intermittently returns 503 UNAVAILABLE or "high demand" messages
    instead of the canonical 429 RESOURCE_EXHAUSTED when capacity is constrained.
    Both codes should trigger the model-fallback chain identically.
    """
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        status = (getattr(exc, "status", None) or "").upper()
        if code in (429, 503):
            return True
        if status in ("RESOURCE_EXHAUSTED", "UNAVAILABLE"):
            return True
    text = str(exc).upper()
    return (
        "RESOURCE_EXHAUSTED" in text
        or "UNAVAILABLE" in text
        or "HIGH DEMAND" in text
        or ("429" in text and ("EXHAUST" in text or "QUOTA" in text))
        or ("503" in text and ("UNAVAILABLE" in text or "OVERLOAD" in text or "DEMAND" in text))
    )


def _generate_once(client, model: str, contents: str) -> str:
    response = client.models.generate_content(
        model=model,
        contents=contents,
    )
    return (response.text or "").strip()


def generate_content_with_fallback(
    contents: str,
    *,
    primary_model: str = PRIMARY_MODEL,
    fallback_model: str = FALLBACK_MODEL,
    tertiary_model: str = TERTIARY_MODEL,
) -> str:
    """
    Generate text across a model chain, then one delayed retry on the last model.

    Order: primary -> fallback -> tertiary -> (sleep) -> tertiary retry.

    Raises GeminiQuotaExhaustedError if all attempts hit rate limits.
    Re-raises non-quota errors immediately.
    """
    client = create_gemini_client()
    models = (primary_model, fallback_model, tertiary_model)
    last_quota_error: BaseException | None = None

    for index, model in enumerate(models):
        try:
            return _generate_once(client, model, contents)
        except Exception as exc:
            if not is_resource_exhausted(exc):
                logger.error("Gemini generation failed (non-quota): %s", exc)
                raise

            last_quota_error = exc
            if index == 0:
                print(
                    "Primary model quota exhausted. Initiating fallback mechanism..."
                )
                logger.warning(
                    "Primary model %s quota exhausted; trying %s",
                    primary_model,
                    fallback_model,
                )
            elif index < len(models) - 1:
                next_model = models[index + 1]
                print(
                    f"Model {model} quota exhausted. Trying fallback {next_model}..."
                )
                logger.warning(
                    "Model %s quota exhausted; falling back to %s",
                    model,
                    next_model,
                )
            else:
                print(
                    f"Model {model} quota exhausted. "
                    f"Waiting {FINAL_RETRY_SLEEP_SEC}s before final retry..."
                )
                logger.warning(
                    "Tertiary model %s quota exhausted; sleeping %ss for final retry",
                    tertiary_model,
                    FINAL_RETRY_SLEEP_SEC,
                )
                time.sleep(FINAL_RETRY_SLEEP_SEC)
                try:
                    return _generate_once(client, model, contents)
                except Exception as retry_exc:
                    if not is_resource_exhausted(retry_exc):
                        raise
                    last_quota_error = retry_exc

    logger.error("All Gemini generation attempts exhausted quota: %s", last_quota_error)
    raise GeminiQuotaExhaustedError() from last_quota_error
