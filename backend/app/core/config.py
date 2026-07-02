"""
Central configuration. Everything the evaluator's limits depend on lives
here as named constants, not magic numbers scattered through the code.
"""
from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


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
    # "template" needs no API key and no network access -- it's the safe
    # default and the fallback used on LLM timeout/error. Swap to "gemini"
    # or "groq" or "openrouter" once you have a free-tier key; the
    # abstraction in app/services/llm.py is what makes that a one-line change.
    llm_provider: str = os.getenv("LLM_PROVIDER", "template")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    llm_timeout_seconds: float = 12.0  # reply generation call; leaves headroom under 30s

    # -- Slot/intent extraction (app/services/intent.py) ------------------
    # Runs BEFORE reply generation, so its timeout has to leave headroom
    # for that second call too: intent (8s) + reply (12s) + local
    # retrieval leaves ~10s of slack under the evaluator's 30s call budget.
    # Falls back to the rule-based extractor on timeout, same as the LLM
    # reply provider falls back to the template on timeout.
    intent_timeout_seconds: float = 8.0

    model_config = SettingsConfigDict(env_prefix="SHL_")


settings = Settings()
