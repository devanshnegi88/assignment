"""
Slot/intent extraction: turns a single user message into a partial slot
dict, in the exact shape `conversation.py`'s state machine merges turn
over turn.

Two implementations, same interface:

- RuleBasedSlotExtractor: the original hand-written keyword-hint
  extractor. Zero dependencies, zero network calls, fully deterministic.
  It's also the correct default when no LLM key is configured, and it's
  what tests exercise unless they explicitly inject an LLM extractor.

- LLMSlotExtractor: asks Gemini to extract the same slot shape from the
  raw user message. This exists because the rule-based extractor can
  only ever recognize the literal strings someone thought to hard-code
  (e.g. it has no entry for "admin assistant" or "Excel"/"Word" even
  though those are exactly the kind of specific, answerable request the
  PDF's "Recommend" behavior is meant to act on immediately). Falls back
  to RuleBasedSlotExtractor on any network error, timeout, or malformed
  response -- extraction failure must never break the conversation.

`conversation.py` depends only on the `SlotExtractor` interface, not on
which implementation is active, so swapping providers doesn't touch the
decision logic (clarify/recommend/refine/compare/refuse) at all.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Dict, List

import httpx

from app.core.config import settings

logger = logging.getLogger("intent_extraction")

# ---------------------------------------------------------------------------
# Shared slot vocabulary
# ---------------------------------------------------------------------------

SLOT_KEYS = (
    "hiring_role",
    "target_population",
    "seniority",
    "assessment_purpose",
    "technical_skills",
    "leadership_requirements",
    "personality_requirements",
    "competencies",
)
_LIST_SLOTS = {
    "technical_skills",
    "leadership_requirements",
    "personality_requirements",
    "competencies",
}


def empty_slots() -> Dict[str, Any]:
    return {key: ([] if key in _LIST_SLOTS else None) for key in SLOT_KEYS}


# ---------------------------------------------------------------------------
# Rule-based extractor (moved from conversation.py, logic unchanged)
# ---------------------------------------------------------------------------

ROLE_HINTS = [
    "developer", "engineer", "manager", "analyst", "recruiter", "assistant",
    "sales", "customer service", "administrator", "designer", "leader", "leadership",
]
TARGET_POPULATION_HINTS = [
    "cxos", "director", "executive", "leadership", "population", "candidates",
    "people", "pool", "employees", "staff", "graduates", "entry-level",
]
SENIORITY_HINTS = [
    "senior", "junior", "graduate", "mid-level", "mid professional", "entry-level",
    "director-level", "executive", "experienced", "years", "15+", "15 years",
    "5+ years", "4 years", "10 years",
]
SKILL_HINTS = [
    "java", "python", ".net", "sql", "spring", "aws", "docker", "rust", "excel",
    "word", "hipaa", "medical terminology", "angular", "react", "node", "rest",
]
LEADERSHIP_HINTS = [
    "leadership", "strategic thinking", "influencing", "people management", "mentor",
    "team", "manage others", "leadership benchmark",
]
PERSONALITY_HINTS = [
    "personality", "behavior", "behaviour", "opq", "fit", "workplace behavior",
]
COMPETENCY_HINTS = [
    "competency", "competencies", "skills", "capabilities", "capability", "behavioural",
]
PURPOSE_HINTS = [
    "selection", "development", "developmental", "benchmark", "compare candidates",
    "re-skill", "talent audit",
]


def _extract_slots_rule_based(text: str) -> Dict[str, Any]:
    lowered = text.lower()
    slots = empty_slots()

    if any(hint in lowered for hint in ROLE_HINTS):
        for hint in ["developer", "engineer", "manager", "analyst", "assistant", "sales", "recruiter"]:
            if hint in lowered:
                slots["hiring_role"] = hint.title()
                break
        if slots["hiring_role"] is None:
            slots["hiring_role"] = "Role"

    if any(hint in lowered for hint in TARGET_POPULATION_HINTS):
        if "cxos" in lowered or "director" in lowered or "executive" in lowered:
            slots["target_population"] = "executive / leadership population"
        elif "graduate" in lowered:
            slots["target_population"] = "graduates"
        else:
            slots["target_population"] = "target population"

    if any(hint in lowered for hint in SENIORITY_HINTS):
        if "15+" in lowered or "15 years" in lowered or "more than 15" in lowered:
            slots["seniority"] = "15+ years"
        elif "senior" in lowered:
            slots["seniority"] = "senior"
        elif "mid-level" in lowered or "mid professional" in lowered:
            slots["seniority"] = "mid-level"
        elif "graduate" in lowered:
            slots["seniority"] = "graduate"
        elif "entry-level" in lowered:
            slots["seniority"] = "entry-level"
        else:
            slots["seniority"] = "seniority"

    if any(hint in lowered for hint in PURPOSE_HINTS):
        if "development" in lowered or "developmental" in lowered or "re-skill" in lowered:
            slots["assessment_purpose"] = "development"
        elif "selection" in lowered or "benchmark" in lowered or "compare candidates" in lowered:
            slots["assessment_purpose"] = "selection"

    for hint in SKILL_HINTS:
        if hint in lowered:
            slots["technical_skills"].append(hint)
    for hint in LEADERSHIP_HINTS:
        if hint in lowered:
            slots["leadership_requirements"].append(hint)
    for hint in PERSONALITY_HINTS:
        if hint in lowered:
            slots["personality_requirements"].append(hint)
    for hint in COMPETENCY_HINTS:
        if hint in lowered:
            slots["competencies"].append(hint)

    return slots


class SlotExtractor(ABC):
    @abstractmethod
    def extract(self, text: str, prior_slots: Dict[str, Any]) -> Dict[str, Any]:
        """Return only what THIS message adds/changes, in the SLOT_KEYS
        shape. Callers merge this into running state -- extractors must
        not try to do the merging themselves."""
        raise NotImplementedError


class RuleBasedSlotExtractor(SlotExtractor):
    """Keyword-hint extractor. Deterministic, zero dependencies. Default
    provider, and the LLM extractor's fallback on any failure."""

    def extract(self, text: str, prior_slots: Dict[str, Any]) -> Dict[str, Any]:
        return _extract_slots_rule_based(text)


class LLMSlotExtractor(SlotExtractor):
    """Gemini-backed extractor for open-vocabulary phrasing the rule-based
    hint lists can't cover. Falls back to RuleBasedSlotExtractor on any
    network error, timeout, or malformed response."""

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str, timeout: float, fallback: SlotExtractor):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._fallback = fallback

    def extract(self, text: str, prior_slots: Dict[str, Any]) -> Dict[str, Any]:
        try:
            url = self.ENDPOINT.format(model=self.model)
            resp = httpx.post(
                f"{url}?key={self.api_key}",
                json={
                    "contents": [{"parts": [{"text": self._build_prompt(text, prior_slots)}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0,
                    },
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_text)
            slots = self._sanitize(parsed)
            logger.debug("LLM slot extraction succeeded: %s", slots)
            return slots
        except Exception as exc:
            logger.warning("LLM slot extraction failed (%s); using rule-based fallback", exc)
            return self._fallback.extract(text, prior_slots)

    @staticmethod
    def _sanitize(parsed: Any) -> Dict[str, Any]:
        """Never trust the model's output shape blindly -- coerce into
        exactly the slot schema the state machine expects, silently
        dropping anything else (extra keys, wrong types, junk values)."""
        slots = empty_slots()
        if not isinstance(parsed, dict):
            return slots
        for key in SLOT_KEYS:
            value = parsed.get(key)
            if key in _LIST_SLOTS:
                if isinstance(value, list):
                    cleaned: List[str] = []
                    for item in value:
                        if isinstance(item, (str, int, float)):
                            text = str(item).strip().lower()
                            if text:
                                cleaned.append(text)
                    slots[key] = cleaned
            else:
                if isinstance(value, str):
                    text = value.strip()
                    if text and text.lower() not in ("null", "none", "unknown", "n/a", ""):
                        slots[key] = text
        return slots

    @staticmethod
    def _build_prompt(text: str, prior_slots: Dict[str, Any]) -> str:
        known = {k: v for k, v in (prior_slots or {}).items() if v}
        return (
            "You extract structured hiring-context slots from ONE message in a "
            "conversation about choosing SHL assessments. Return ONLY a JSON object "
            "with exactly these keys, no prose, no markdown fences:\n"
            '{"hiring_role": string|null, "target_population": string|null, '
            '"seniority": string|null, "assessment_purpose": "selection"|"development"|null, '
            '"technical_skills": string[], "leadership_requirements": string[], '
            '"personality_requirements": string[], "competencies": string[]}\n\n'
            "Rules:\n"
            "- Only report information stated in THIS message, not the whole conversation.\n"
            "- Do not repeat values already known below unless this message changes them.\n"
            "- technical_skills means concrete skills/tools/languages "
            "(e.g. \"excel\", \"java\", \"sql\", \"word\"), lowercase, as they literally "
            "appear in the message.\n"
            "- If nothing new is stated for a field, use null (or [] for list fields).\n"
            "- Never invent information that is not present in the message.\n\n"
            f"Already known this conversation: {json.dumps(known)}\n"
            f"Message: {text}\n"
        )


@lru_cache(maxsize=1)
def get_slot_extractor() -> SlotExtractor:
    rule_based = RuleBasedSlotExtractor()
    if settings.llm_provider == "gemini" and settings.llm_api_key:
        logger.info("Slot extraction: Gemini (%s) active, rule-based fallback armed", settings.llm_model)
        return LLMSlotExtractor(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.intent_timeout_seconds,
            fallback=rule_based,
        )
    logger.info("Slot extraction: rule-based extractor (no Gemini key configured)")
    return rule_based
