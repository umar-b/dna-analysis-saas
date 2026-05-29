"""LLM client seam (ADR-0014). Dev = OpenRouter (cheap Claude); prod = Anthropic.

Importing this module has no side effects; the client is built only when
`get_client()` is called.
"""

from __future__ import annotations

import os
from pathlib import Path

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEV_MODEL = "anthropic/claude-3.5-haiku"


def load_dotenv(path: str = ".env") -> None:
    """Populate os.environ from a .env file (does not overwrite existing vars)."""
    env = Path(path)
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_client_and_model():
    """Return (client, model, backend). Backend from LLM_BACKEND (default openrouter)."""
    load_dotenv()
    backend = os.environ.get("LLM_BACKEND", "openrouter")
    if backend == "openrouter":
        from openai import OpenAI

        client = OpenAI(
            base_url=OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"]
        )
        return client, os.environ.get("LLM_MODEL", DEV_MODEL), backend
    if backend == "anthropic":  # prod path (ADR-0002); not exercised in V1 dev
        from anthropic import Anthropic

        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return client, os.environ.get("LLM_MODEL", "claude-opus-4-7"), backend
    raise ValueError(f"unknown LLM_BACKEND: {backend}")


def cached_tokens(usage) -> int:
    """Cache-read tokens, normalized across backends (ADR-0014)."""
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None and getattr(details, "cached_tokens", None) is not None:
        return int(details.cached_tokens)  # OpenRouter / OpenAI-shape
    return int(getattr(usage, "cache_read_input_tokens", 0) or 0)  # Anthropic-shape
