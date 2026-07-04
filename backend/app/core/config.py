"""
Central configuration. Everything the evaluator's limits depend on lives
here as named constants, not magic numbers scattered through the code.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _parse_gemini_keys() -> List[str]:
    """Parse GEMINI_API_KEYS (comma-separated) or fall back to legacy
    GEMINI_API_KEY / LLM_API_KEY for backward compatibility."""
    multi = os.getenv("GEMINI_API_KEYS", "")
    if multi:
        return [k.strip() for k in multi.split(",") if k.strip()]
    single = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY", "")
    return [single] if single else []


# Resolved once at import time -- the key manager in llm.py reads the full list.
_GEMINI_KEYS: List[str] = _parse_gemini_keys()


class Settings(BaseSettings):
    # -- Evaluator limits (see PDF page 4: "Limits") --------------------
    max_turns: int = 8                 # user+assistant turns per conversation
    request_timeout_seconds: int = 30  # per-call timeout budget

    # -- Recommendations -------------------------------------------------
    min_recommendations: int = 1
    max_recommendations: int = 10
    default_top_k: int = 5

    # -- Catalog ----------------------------------------------------------
    catalog_path: Path = BACKEND_ROOT.parent / "data" / "catalog.json"

    # -- Retrieval weighting (hybrid = alpha*keyword + (1-alpha)*semantic)
    hybrid_keyword_weight: float = 0.5

    # -- LLM provider ------------------------------------------------------
    # Gemini 2.5 Flash (via the official Google GenAI SDK) is the only
    # conversation-intelligence provider.
    #
    # Key rotation: set GEMINI_API_KEYS=key1,key2,key3 (comma-separated).
    # Legacy single-key vars (GEMINI_API_KEY / LLM_API_KEY) are still
    # accepted for backward compatibility.
    #
    # llm_api_key always resolves to the *first* configured key so that
    # auxiliary callers (reranker, conversation slot-extraction, intent)
    # continue to work without any code changes. The GeminiLLMProvider in
    # llm.py is the only place that performs full key-rotation.
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_api_key: str = _GEMINI_KEYS[0] if _GEMINI_KEYS else ""
    llm_model: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    llm_timeout_seconds: float = 12.0  # leaves headroom under the 30s call budget
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    llm_backoff_base_seconds: float = float(os.getenv("LLM_BACKOFF_BASE_SECONDS", "1.0"))

    model_config = SettingsConfigDict(env_prefix="SHL_")


settings = Settings()