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
    # Gemini 2.5 Flash (via the official Google GenAI SDK) is the only
    # conversation-intelligence provider. The API key is read from the
    # environment -- never hardcoded. Accepts either GEMINI_API_KEY (the
    # SDK's own conventional name) or SHL_LLM_API_KEY (this app's prefix).
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_api_key: str = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    llm_timeout_seconds: float = 12.0  # leaves headroom under the 30s call budget
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    llm_backoff_base_seconds: float = float(os.getenv("LLM_BACKOFF_BASE_SECONDS", "1.0"))

    model_config = SettingsConfigDict(env_prefix="SHL_")


settings = Settings()