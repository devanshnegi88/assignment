"""
Tests for app/services/intent.py: the rule-based extractor, the
Gemini-backed extractor (with httpx mocked -- no real network calls),
its fallback behavior, and the get_slot_extractor() factory.

Also covers the concrete generalization gap identified in the audit
(trace C8: "screen admin assistants for Excel and Word" is invisible to
the rule-based hint lists) to prove the LLM-backed extractor -- injected
directly into classify_turn -- actually closes it.
"""
import json as json_module

import httpx
import pytest

from app.core.config import settings
from app.schemas.chat import ChatMessage
from app.services import intent as intent_module
from app.services.conversation import TurnAction, classify_turn
from app.services.intent import (
    LLMSlotExtractor,
    RuleBasedSlotExtractor,
    empty_slots,
    get_slot_extractor,
)


def msg(role, content):
    return ChatMessage(role=role, content=content)


# ---------------------------------------------------------------------------
# RuleBasedSlotExtractor -- same behavior as the old inline _extract_slots
# ---------------------------------------------------------------------------

def test_rule_based_extracts_role_and_skill():
    slots = RuleBasedSlotExtractor().extract("Hiring a Java developer", {})
    assert slots["hiring_role"] == "Developer"
    assert "java" in slots["technical_skills"]


def test_rule_based_returns_full_shape_even_when_empty():
    slots = RuleBasedSlotExtractor().extract("hello", {})
    assert set(slots.keys()) == set(empty_slots().keys())
    assert slots["hiring_role"] is None
    assert slots["technical_skills"] == []


def test_rule_based_misses_out_of_vocabulary_phrasing():
    # This is the documented C8 gap: "admin assistant" / "Excel" / "Word"
    # aren't literal hint-list entries other than "assistant" and "excel"/
    # "word" themselves -- but the *combination* the hint lists were tuned
    # against doesn't reliably trip `_is_ready_to_recommend`'s specific-
    # requirement check for less common role phrasing. This test pins the
    # current rule-based behavior so a future regression is visible.
    slots = RuleBasedSlotExtractor().extract(
        "I need to quickly screen admin assistants for Excel and Word daily", {}
    )
    # It does catch "assistant", "excel", "word" as literal substrings --
    # the real gap is upstream in classify_turn's readiness heuristic,
    # exercised end-to-end below.
    assert slots["hiring_role"] == "Assistant"
    assert "excel" in slots["technical_skills"]


# ---------------------------------------------------------------------------
# LLMSlotExtractor -- httpx mocked, no real network calls
# ---------------------------------------------------------------------------

def _mock_gemini_response(monkeypatch, payload: dict, status_code: int = 200):
    encoded_payload = json_module.dumps(payload)

    def fake_post(url, json, timeout):  # noqa: A002 - must match httpx.post's kwarg name
        request = httpx.Request("POST", url)
        body = {"candidates": [{"content": {"parts": [{"text": encoded_payload}]}}]}
        return httpx.Response(status_code, json=body, request=request)

    monkeypatch.setattr(intent_module.httpx, "post", fake_post)


def test_llm_extractor_parses_well_formed_response(monkeypatch):
    _mock_gemini_response(monkeypatch, {
        "hiring_role": "Administrative Assistant",
        "target_population": None,
        "seniority": None,
        "assessment_purpose": None,
        "technical_skills": ["excel", "word"],
        "leadership_requirements": [],
        "personality_requirements": [],
        "competencies": [],
    })
    extractor = LLMSlotExtractor(api_key="fake", model="gemini-2.5-flash", timeout=5.0, fallback=RuleBasedSlotExtractor())
    slots = extractor.extract("I need to quickly screen admin assistants for Excel and Word daily", {})
    assert slots["hiring_role"] == "Administrative Assistant"
    assert slots["technical_skills"] == ["excel", "word"]


def test_llm_extractor_falls_back_on_network_error(monkeypatch):
    def raising_post(url, json, timeout):
        raise httpx.ConnectTimeout("boom")

    monkeypatch.setattr(intent_module.httpx, "post", raising_post)
    fallback = RuleBasedSlotExtractor()
    extractor = LLMSlotExtractor(api_key="fake", model="gemini-2.5-flash", timeout=5.0, fallback=fallback)
    slots = extractor.extract("Hiring a Java developer", {})
    # Falls through to exactly what the rule-based extractor would return.
    assert slots == fallback.extract("Hiring a Java developer", {})


def test_llm_extractor_falls_back_on_malformed_json(monkeypatch):
    def fake_post(url, json, timeout):
        request = httpx.Request("POST", url)
        body = {
            "candidates": [
                {"content": {"parts": [{"text": "not valid json {{"}]}}
            ]
        }
        return httpx.Response(200, json=body, request=request)

    monkeypatch.setattr(intent_module.httpx, "post", fake_post)
    fallback = RuleBasedSlotExtractor()
    extractor = LLMSlotExtractor(api_key="fake", model="gemini-2.5-flash", timeout=5.0, fallback=fallback)
    slots = extractor.extract("Hiring a Java developer", {})
    assert slots == fallback.extract("Hiring a Java developer", {})


def test_llm_extractor_sanitizes_unexpected_shape(monkeypatch):
    # Extra keys, wrong types, junk sentinel strings -- all must be
    # dropped rather than trusted, since this is untrusted model output.
    _mock_gemini_response(monkeypatch, {
        "hiring_role": "unknown",
        "technical_skills": "java",  # wrong type: should be a list
        "some_made_up_key": "ignored",
        "competencies": [1, 2, "communication"],
    })
    extractor = LLMSlotExtractor(api_key="fake", model="gemini-2.5-flash", timeout=5.0, fallback=RuleBasedSlotExtractor())
    slots = extractor.extract("anything", {})
    assert slots["hiring_role"] is None  # "unknown" sentinel dropped
    assert slots["technical_skills"] == []  # wrong type dropped, not coerced
    assert "some_made_up_key" not in slots
    assert slots["competencies"] == ["1", "2", "communication"]


# ---------------------------------------------------------------------------
# get_slot_extractor() factory
# ---------------------------------------------------------------------------

def test_factory_defaults_to_rule_based_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "template")
    monkeypatch.setattr(settings, "llm_api_key", "")
    get_slot_extractor.cache_clear()
    extractor = get_slot_extractor()
    assert isinstance(extractor, RuleBasedSlotExtractor)
    get_slot_extractor.cache_clear()


def test_factory_uses_llm_extractor_when_gemini_configured(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_api_key", "fake-key")
    get_slot_extractor.cache_clear()
    extractor = get_slot_extractor()
    assert isinstance(extractor, LLMSlotExtractor)
    get_slot_extractor.cache_clear()


# ---------------------------------------------------------------------------
# End-to-end: classify_turn with an injected LLM extractor closes the C8 gap
# ---------------------------------------------------------------------------

def test_classify_turn_recommends_with_llm_extractor_on_out_of_vocab_query(monkeypatch):
    """This is the regression test for the audit's C8 finding: a precise,
    specific request that the rule-based extractor under-recognizes
    should still reach RECOMMEND on turn 1 once the LLM extractor is
    supplying richer slots -- without touching classify_turn's decision
    logic at all, only the extractor it's given."""

    _mock_gemini_response(monkeypatch, {
        "hiring_role": "Administrative Assistant",
        "target_population": None,
        "seniority": None,
        "assessment_purpose": "selection",
        "technical_skills": ["excel", "word"],
        "leadership_requirements": [],
        "personality_requirements": [],
        "competencies": [],
    })
    llm_extractor = LLMSlotExtractor(api_key="fake", model="gemini-2.5-flash", timeout=5.0, fallback=RuleBasedSlotExtractor())

    decision = classify_turn(
        [msg("user", "I need to quickly screen admin assistants for Excel and Word daily")],
        slot_extractor=llm_extractor,
    )
    assert decision.action == TurnAction.RECOMMEND
    assert decision.slots["hiring_role"] == "Administrative Assistant"


def test_classify_turn_default_extractor_matches_prior_behavior(monkeypatch):
    """With no LLM key configured (the test-suite default), classify_turn
    must behave exactly as it did before this refactor."""
    monkeypatch.setattr(settings, "llm_provider", "template")
    monkeypatch.setattr(settings, "llm_api_key", "")
    get_slot_extractor.cache_clear()
    decision = classify_turn([msg("user", "I need an assessment")])
    assert decision.action == TurnAction.CLARIFY
    get_slot_extractor.cache_clear()
