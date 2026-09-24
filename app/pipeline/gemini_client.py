"""Thin wrapper around the google-genai SDK: a shared client, a structured-output
helper with one retry on parse failure, and a grounded (Google Search) helper.
"""

from __future__ import annotations

import logging
import time
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def generate_structured(
    *,
    system_instruction: str,
    contents: str,
    schema: type[T],
    model: str | None = None,
    retries: int = 1,
) -> T:
    """Call Gemini asking for JSON matching `schema`. Retries once on a parse
    or validation failure, per the triage/draft spec.
    """
    client = get_client()
    used_model = model or settings.gemini_model
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            response = client.models.generate_content(
                model=used_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, schema):
                return parsed
            return schema.model_validate_json(response.text)
        except (ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "Structured generation parse failure on attempt %d/%d: %s",
                attempt + 1,
                retries + 1,
                exc,
            )
        except Exception as exc:  # Gemini rate limits / transient network errors
            last_error = exc
            logger.warning(
                "Gemini call failed on attempt %d/%d: %s", attempt + 1, retries + 1, exc
            )
            time.sleep(min(2 ** attempt, 8))

    raise RuntimeError(
        f"Gemini structured output failed after {retries + 1} attempts: {last_error}"
    ) from last_error


def generate_grounded(*, prompt: str, model: str | None = None) -> types.GenerateContentResponse:
    """Call Gemini with the Google Search grounding tool enabled. Returns the raw
    response so the caller can read both `.text` and `.candidates[0].grounding_metadata`
    (the real, non-hallucinated source URLs live in the grounding metadata, never in text).
    """
    client = get_client()
    used_model = model or settings.gemini_model
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    return client.models.generate_content(
        model=used_model,
        contents=prompt,
        config=types.GenerateContentConfig(tools=[grounding_tool]),
    )
