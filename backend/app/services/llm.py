"""
LLM abstraction for the reply text only.

Key-rotation logic lives inside GeminiKeyManager (thread-safe). The
GeminiLLMProvider calls it transparently, so no other module needs to change.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import List, Optional

from app.catalog.schema import CatalogItem
from app.core.config import _GEMINI_KEYS, settings
from app.prompts.jinja import render_prompt
from app.services.conversation import TurnDecision

logger = logging.getLogger("llm_provider")

# ---------------------------------------------------------------------------
# Error taxonomy helpers
# ---------------------------------------------------------------------------

# Substrings (case-insensitive) that indicate a *quota / rate-limit* failure —
# the only class of error that warrants rotating to the next key.
_QUOTA_SIGNALS: tuple[str, ...] = (
    "429",
    "resource_exhausted",
    "quota",
    "rate limit",
    "rate_limit",
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "too many requests",
)

# Substrings that indicate a *non-retriable* error — rotating keys won't help.
_NO_ROTATE_SIGNALS: tuple[str, ...] = (
    "invalid api key",
    "api_key_invalid",
    "permission_denied",
    "api key not valid",
    "unauthenticated",
    "invalid argument",
    "invalid_argument",
    "safety",
    "blocked",
    "finish_reason: safety",
    "model not found",
    "not found",
)


def _is_quota_error(exc: BaseException) -> bool:
    """Return True when *exc* signals quota / rate-limit exhaustion."""
    msg = str(exc).lower()
    return any(sig.lower() in msg for sig in _QUOTA_SIGNALS)


def _is_non_retriable(exc: BaseException) -> bool:
    """Return True when rotating keys cannot help (auth, safety, bad request)."""
    msg = str(exc).lower()
    return any(sig.lower() in msg for sig in _NO_ROTATE_SIGNALS)


# ---------------------------------------------------------------------------
# Public exception types
# ---------------------------------------------------------------------------


class LLMProviderError(Exception):
    pass


class AllKeysExhaustedError(LLMProviderError):
    """Raised when every configured Gemini API key has hit its quota."""
    pass


# ---------------------------------------------------------------------------
# Thread-safe key manager
# ---------------------------------------------------------------------------


class GeminiKeyManager:
    """Holds the list of API keys and tracks which one is currently active.

    Thread-safety: a ``threading.Lock`` serialises index advancement so that
    concurrent requests don't simultaneously rotate to the same key.

    Key indices are logged but the actual key strings are never emitted.
    """

    def __init__(self, keys: List[str]) -> None:
        if not keys:
            raise LLMProviderError("No Gemini API keys configured")
        self._keys: List[str] = keys
        self._index: int = 0
        self._lock: threading.Lock = threading.Lock()
        logger.info(
            "GeminiKeyManager initialised with %d key(s); starting on key index 0",
            len(keys),
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def current_key(self) -> str:
        return self._keys[self._index]

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    def advance(self) -> Optional[str]:
        """Rotate to the next key and return it, or ``None`` if all keys have
        been tried (index wraps back to the first position for the next call)."""
        with self._lock:
            next_index = self._index + 1
            if next_index >= len(self._keys):
                # All keys exhausted; reset so future calls start fresh.
                self._index = 0
                return None
            self._index = next_index
            logger.info(
                "Rotating to Gemini key index %d / %d",
                self._index,
                len(self._keys) - 1,
            )
            return self._keys[self._index]


# ---------------------------------------------------------------------------
# Module-level singleton (created lazily so tests can patch _GEMINI_KEYS)
# ---------------------------------------------------------------------------

_key_manager: Optional[GeminiKeyManager] = None
_manager_lock = threading.Lock()


def _get_key_manager() -> GeminiKeyManager:
    """Return the module-level GeminiKeyManager, creating it on first call."""
    global _key_manager
    if _key_manager is None:
        with _manager_lock:
            if _key_manager is None:  # double-checked locking
                _key_manager = GeminiKeyManager(_GEMINI_KEYS)
    return _key_manager


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    @abstractmethod
    def generate_reply(
        self,
        decision: TurnDecision,
        shortlist: List[CatalogItem],
        conversation_summary: str,
    ) -> str:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Gemini provider with key rotation
# ---------------------------------------------------------------------------


class GeminiLLMProvider(LLMProvider):
    def __init__(self, model: str, timeout: float) -> None:
        self.model = model
        self.timeout = timeout

    # Keep the old signature for callers that still pass api_key (e.g. tests).
    # The value is silently ignored — the key manager is the single source of
    # truth — but the signature stays compatible so nothing breaks.
    @classmethod
    def from_config(cls) -> "GeminiLLMProvider":
        return cls(model=settings.llm_model, timeout=settings.llm_timeout_seconds)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        decision: TurnDecision,
        shortlist: List[CatalogItem],
        conversation_summary: str,
    ) -> str:
        return render_prompt(
            "reply.j2",
            action=decision.action.value,
            needs_clarification=bool(decision.clarification_question),
            clarification_question=decision.clarification_question,
            reasoning=getattr(decision, "reasoning", ""),
            conversation_summary=conversation_summary,
            shortlist=[
                {
                    "name": item.name,
                    "test_type": " ".join(item.test_type_codes)
                    if item.test_type_codes
                    else "",
                }
                for item in shortlist
            ],
        )

    def _invoke_gemini(self, key: str, prompt: str) -> str:
        """Make a single Gemini SDK call with *key*. Raises on any failure."""
        try:
            import google.generativeai as genai
        except Exception as exc:
            raise LLMProviderError("Gemini SDK unavailable") from exc

        genai.configure(api_key=key)
        model = genai.GenerativeModel(self.model)
        response = model.generate_content(prompt)

        if response is None:
            raise ValueError("Empty Gemini response")

        text = getattr(response, "text", "")

        if not text and getattr(response, "candidates", None):
            parts = response.candidates[0].content.parts
            text = "".join(
                getattr(part, "text", "")
                for part in parts
                if hasattr(part, "text")
            )

        if text and text.strip():
            return text.strip()

        raise ValueError("Gemini returned an empty response")

    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini with automatic key rotation on quota errors.

        Strategy
        --------
        1. Try the *current* active key.
        2. On quota/rate-limit error: apply exponential backoff then rotate
           to the next key and retry.
        3. On any *non-retriable* error (auth, safety, invalid request):
           raise immediately — rotating keys will not help.
        4. If every key has been tried and all failed with quota errors, raise
           ``AllKeysExhaustedError``.
        """
        if settings.llm_provider != "gemini":
            raise LLMProviderError("Gemini is not configured")

        manager = _get_key_manager()
        num_keys = manager.total_keys
        backoff_base = settings.llm_backoff_base_seconds  # 1 s by default

        # We attempt each key at most once in sequence.
        for attempt in range(num_keys):
            key_index = manager.current_index
            logger.info(
                "Gemini call attempt %d/%d using key index %d",
                attempt + 1,
                num_keys,
                key_index,
            )

            try:
                result = self._invoke_gemini(manager.current_key, prompt)
                # Success — keep using this key.
                logger.info("Gemini call succeeded on key index %d", key_index)
                return result

            except Exception as exc:
                if _is_non_retriable(exc):
                    logger.error(
                        "Non-retriable Gemini error on key index %d: %s",
                        key_index,
                        exc,
                    )
                    raise LLMProviderError(
                        f"Gemini request failed (non-retriable): {exc}"
                    ) from exc

                if _is_quota_error(exc):
                    logger.warning(
                        "Quota/rate-limit error on key index %d (attempt %d/%d): %s",
                        key_index,
                        attempt + 1,
                        num_keys,
                        exc,
                    )
                    # Exponential backoff before trying the next key.
                    sleep_secs = backoff_base * (2 ** attempt)  # 1s, 2s, 4s …
                    logger.info(
                        "Backing off %.1fs before rotating key (attempt %d/%d)",
                        sleep_secs,
                        attempt + 1,
                        num_keys,
                    )
                    time.sleep(sleep_secs)

                    next_key = manager.advance()
                    if next_key is None:
                        # advance() exhausted all keys and reset the index.
                        break
                    continue

                # Unknown / transient error — treat like quota for rotation.
                logger.warning(
                    "Unknown Gemini error on key index %d (attempt %d/%d): %s",
                    key_index,
                    attempt + 1,
                    num_keys,
                    exc,
                )
                sleep_secs = backoff_base * (2 ** attempt)
                time.sleep(sleep_secs)
                next_key = manager.advance()
                if next_key is None:
                    break
                continue

        raise AllKeysExhaustedError(
            f"All {num_keys} Gemini API key(s) exhausted. "
            "No successful response could be obtained."
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_reply(
        self,
        decision: TurnDecision,
        shortlist: List[CatalogItem],
        conversation_summary: str,
    ) -> str:
        prompt = self._build_prompt(decision, shortlist, conversation_summary)
        return self._call_gemini(prompt)


# ---------------------------------------------------------------------------
# Factory (signature unchanged — callers pass no arguments)
# ---------------------------------------------------------------------------


def get_llm_provider() -> LLMProvider:
    """Return a configured GeminiLLMProvider.

    Raises ``LLMProviderError`` if Gemini is not configured.  The provider
    carries no API key itself — the ``GeminiKeyManager`` singleton is the
    single source of truth for which key is currently active.
    """
    if settings.llm_provider == "gemini" and settings.llm_api_key:
        return GeminiLLMProvider(
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )

    raise LLMProviderError("Gemini is not configured")