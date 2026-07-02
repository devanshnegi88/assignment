"""
LLM abstraction for the reply text only.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import List

from app.catalog.schema import CatalogItem
from app.core.config import settings
from app.prompts.jinja import render_prompt
from app.services.conversation import TurnDecision

logger = logging.getLogger("llm_provider")


class LLMProviderError(Exception):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def generate_reply(
        self,
        decision: TurnDecision,
        shortlist: List[CatalogItem],
        conversation_summary: str,
    ) -> str:
        raise NotImplementedError


class GeminiLLMProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, timeout: float):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

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

    def _call_gemini(self, prompt: str) -> str:
        if not settings.llm_api_key or settings.llm_provider != "gemini":
            raise LLMProviderError("Gemini is not configured")

        try:
            import google.generativeai as genai
        except Exception as exc:
            raise LLMProviderError("Gemini SDK unavailable") from exc

        genai.configure(api_key=settings.llm_api_key)

        model = genai.GenerativeModel(self.model)

        last_exc = None

        for attempt in range(settings.llm_max_retries):
            try:
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
                    logger.info("Using Gemini SDK")
                    return text.strip()

                raise ValueError("Gemini returned an empty response")

            except Exception as exc:
                last_exc = exc

                logger.warning(
                    "Gemini call failed on attempt %d: %s",
                    attempt + 1,
                    exc,
                )

                if attempt + 1 >= settings.llm_max_retries:
                    break

                time.sleep(
                    settings.llm_backoff_base_seconds * (2 ** attempt)
                )

        raise LLMProviderError(
            "Gemini request failed after retries"
        ) from last_exc

    def generate_reply(
        self,
        decision: TurnDecision,
        shortlist: List[CatalogItem],
        conversation_summary: str,
    ) -> str:
        prompt = self._build_prompt(
            decision,
            shortlist,
            conversation_summary,
        )
        return self._call_gemini(prompt)


def get_llm_provider() -> LLMProvider:
    if (
        settings.llm_provider == "gemini"
        and settings.llm_api_key
    ):
        return GeminiLLMProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )

    raise LLMProviderError("Gemini is not configured")