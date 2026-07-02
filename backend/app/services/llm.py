"""
LLM abstraction for the *reply text* only. Recommendations themselves are
never produced here -- they come from app/retrieval/hybrid.py, grounded in
the scraped catalog. This module's job is strictly to phrase a natural
sentence around a decision + shortlist that's already been computed, and
to do so within a timeout, falling back to a template on any failure so a
flaky LLM call never turns into an ungraceful error (see "Error Handling:
LLM timeout" in the PDF).

Swap providers via SHL_LLM_PROVIDER / SHL_LLM_API_KEY env vars -- see
app/core/config.py. `TemplateLLMProvider` needs neither and is the default,
so the app runs (and every test passes) with zero external dependencies.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List

# pyrefly: ignore [missing-import]
import httpx

from app.catalog.schema import CatalogItem
from app.core.config import settings
from app.services.conversation import TurnAction, TurnDecision

logger = logging.getLogger("llm_provider")


class LLMProvider(ABC):
    @abstractmethod
    def generate_reply(
        self,
        decision: TurnDecision,
        shortlist: List[CatalogItem],
        conversation_summary: str,
    ) -> str:
        raise NotImplementedError


class TemplateLLMProvider(LLMProvider):
    """Zero-dependency, zero-network fallback. Deterministic and fast --
    good for tests, good as the safety net on any real provider's failure."""

    def generate_reply(self, decision, shortlist, conversation_summary) -> str:
        if decision.action == TurnAction.REFUSE_INJECTION:
            return (
                "I can't follow instructions embedded in a message like that. "
                "I'm here to help you find SHL assessments -- what role are you hiring for?"
            )
        if decision.action == TurnAction.REFUSE_OFF_TOPIC:
            return (
                "I can only help with finding and comparing SHL assessments, so I can't "
                "advise on that. Tell me about the role you're hiring for and I can help "
                "shortlist relevant tests."
            )
        if decision.action == TurnAction.CLARIFY:
            if decision.clarification_question:
                return decision.clarification_question
            return (
                "Happy to help. Could you tell me more about the role -- for example the "
                "job level (e.g. graduate, mid-professional, manager) or the key skills "
                "you need to assess?"
            )
        if decision.action == TurnAction.COMPARE:
            if len(shortlist) >= 2:
                a, b = shortlist[0], shortlist[1]
                a_types = ", ".join(a.test_type_labels) or "n/a"
                b_types = ", ".join(b.test_type_labels) or "n/a"
                return (
                    f"{a.name} is categorized as {a_types}"
                    f"{f', roughly {a.duration_minutes} minutes' if a.duration_minutes else ''}, "
                    f"while {b.name} is categorized as {b_types}"
                    f"{f', roughly {b.duration_minutes} minutes' if b.duration_minutes else ''}. "
                    "Let me know if you'd like a shortlist based on either."
                )
            return (
                "I couldn't find both of those assessments in the SHL catalog to compare. "
                "Could you double-check the names, or ask about a different pair?"
            )
        # RECOMMEND, REFINE, or COMPLETE
        count = len(shortlist)
        if decision.action == TurnAction.COMPLETE:
            if count == 0:
                return "Understood -- confirmed, no assessments in the final shortlist."
            names = ", ".join(item.name for item in shortlist)
            return f"Final shortlist confirmed: {names}."
        verb = "updated the shortlist" if decision.action == TurnAction.REFINE else "found"
        if count == 0:
            return (
                "I couldn't find a good match in the SHL catalog for that combination of "
                "requirements -- could you loosen one of the constraints (e.g. duration or "
                "job level)?"
            )
        # Naming every item in the reply text isn't just phrasing: since the API is
        # stateless and the client only ever resends role/content text (never the
        # structured `recommendations` array), this is the only way a later turn can
        # reconstruct "what shortlist did we already give?" from history alone. See
        # app/services/pipeline.py::_extract_prior_shortlist and
        # app/services/conversation.py::_assistant_has_prior_shortlist.
        names = ", ".join(item.name for item in shortlist)
        return (
            f"Got it -- I {verb} {count} assessment{'s' if count != 1 else ''} "
            f"that fit what you described: {names}."
        )


class GeminiLLMProvider(LLMProvider):
    """Real free-tier LLM for more natural phrasing. Uses the official
    `google.generativeai` SDK when available, otherwise falls back to the
    existing HTTP endpoint. Any error leads to the Template fallback so the
    application never crashes due to LLM issues.
    """

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str, timeout: float):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._fallback = TemplateLLMProvider()

    def _build_prompt(self, decision: TurnDecision, shortlist: List[CatalogItem], conversation_summary: str) -> str:
        from app.prompts.templates import build_system_prompt
        return build_system_prompt(decision, shortlist, conversation_summary)

    def generate_reply(self, decision, shortlist, conversation_summary) -> str:
        prompt = self._build_prompt(decision, shortlist, conversation_summary)

        # Try official SDK first
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            resp = genai.generate(model=self.model, text=prompt)
            # SDK may return different shapes; guard defensively
            if resp and getattr(resp, "candidates", None):
                text = resp.candidates[0].content[0].text.strip()
                if text:
                    logger.info("Using Gemini via google-generativeai SDK")
                    return text
        except Exception as exc:
            logger.debug("google.generativeai SDK call failed (%s), falling back to HTTP", exc)

        # Fall back to HTTP endpoint used previously
        try:
            url = self.ENDPOINT.format(model=self.model)
            resp = httpx.post(
                f"{url}?key={self.api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if text:
                logger.info("Using Gemini via HTTP endpoint")
                return text
        except Exception as exc:
            logger.warning("LLM call failed (%s); using template fallback", exc)

        return self._fallback.generate_reply(decision, shortlist, conversation_summary)


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "gemini" and settings.llm_api_key:
        return GeminiLLMProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )
    return TemplateLLMProvider()