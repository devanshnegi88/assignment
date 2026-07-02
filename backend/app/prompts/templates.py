"""
Turns a conversation history into a decision: what should this turn do?

The decision logic now reconstructs slot-based conversation state from the
entire message history so it can preserve what the user has already said
and ask only for the next missing piece of information.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.retrieval.hybrid import RetrievalConstraints
from app.schemas.chat import ChatMessage


logger = logging.getLogger(__name__)


class TurnAction(str, Enum):
    REFUSE_INJECTION = "refuse_injection"
    REFUSE_OFF_TOPIC = "refuse_off_topic"
    CLARIFY = "clarify"
    RECOMMEND = "recommend"
    REFINE = "refine"
    COMPARE = "compare"
    COMPLETE = "complete"


@dataclass
class TurnDecision:
    action: TurnAction
    query: str
    constraints: RetrievalConstraints = field(default_factory=RetrievalConstraints)
    compare_terms: List[str] = field(default_factory=list)
    preferred_item_names: List[str] = field(default_factory=list)
    end_of_conversation: bool = False
    should_return_recommendations: bool = True
    clarification_slot: Optional[str] = None
    clarification_question: Optional[str] = None
    slots: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationState:
    slots: Dict[str, Any] = field(default_factory=dict)
    user_turn_count: int = 0
    assistant_turn_count: int = 0

    def merge_user_text(self, text: str) -> None:
        self.user_turn_count += 1
        self.slots = _merge_slots(self.slots, _extract_slots(text))

    def next_missing_slot(self, text: str) -> Optional[str]:
        return _next_missing_slot(self.slots, text)

    def is_ready_to_recommend(self, text: str, already_clarified_once: bool) -> bool:
        return _is_ready_to_recommend(self.slots, text, already_clarified_once)

    def debug_summary(self) -> Dict[str, Any]:
        return {
            "slots": self.slots,
            "user_turn_count": self.user_turn_count,
            "assistant_turn_count": self.assistant_turn_count,
        }


def _reconstruct_conversation_state(messages: List[ChatMessage]) -> ConversationState:
    state = ConversationState()
    for message in messages:
        if message.role == "user":
            state.merge_user_text(message.content)
        elif message.role == "assistant":
            state.assistant_turn_count += 1
    return state


_INJECTION_PATTERNS = [
    r"ignore (all|the|any) (previous|prior|above) instructions",
    r"disregard (all|the|any) (previous|prior|above) instructions",
    r"you are now",
    r"act as (?!a hiring|an? recruiter)",
    r"system prompt",
    r"reveal (your|the) (instructions|prompt|system)",
    r"pretend (you are|to be)",
    r"jailbreak",
    r"developer mode",
    r"\bDAN\b",
    r"override your (guidelines|rules|instructions)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

_SHL_ON_TOPIC_HINTS = [
    "assessment", "test", "shl", "candidate", "hire", "hiring", "recruit",
    "skill", "job", "role", "developer", "engineer", "manager", "personality",
    "cognitive", "aptitude", "interview", "screening", "opq", "gsa", "verify",
    "language", "duration", "compare", "difference", "vs", "shortlist",
]
_OFF_TOPIC_HINTS = [
    "weather", "recipe", "poem", "joke", "movie", "sports score",
    "stock price", "legal advice", "lawsuit", "medical advice", "diagnose",
    "write me code", "write a python script", "translate this",
]

_REFINE_HINTS = [
    "actually", "instead", "also add", "add ", "remove ", "change to",
    "what about", "can you also", "update the", "on second thought",
    "one more thing", "as well", "drop ", "replace ", "shorter",
]
_COMPARE_HINTS = [
    "difference between", "compare", "versus", " vs ", "vs.", "which is better",
    "how does .* differ", "different from", "is .* different",
]
_COMPARE_RE = re.compile("|".join(_COMPARE_HINTS), re.IGNORECASE)

_ASSISTANT_SHORTLIST_HINTS = [
    "here are some options", "here are some recommendations", "here are some options.",
    "here are some options for you", "your options", "these options", "here are some solutions",
    "you can choose from", "you might consider", "we suggest", "we recommend",
    # Phrases the reply generator (app/services/llm.py TemplateLLMProvider, and the
    # Gemini prompt in app/prompts/templates.py) actually produces for RECOMMEND /
    # REFINE / COMPLETE turns. Because the API is stateless, this reply text is the
    # *only* place state about "did we already give a shortlist?" can live -- there
    # is no separate structured history to fall back on.
    "that fit what you described", "i found", "i updated the shortlist",
    "final shortlist confirmed",
]
# Deliberately excludes bare "shortlist"/"recommendations"/"recommended"/
# "options for": the off-topic-refusal and compare reply templates also use
# those words in passing ("I can help shortlist relevant tests", "let me know
# if you'd like a shortlist based on either"), so matching on them would make
# a refusal or a comparison look like a fresh shortlist announcement and mask
# the real one from a few turns back.

_ROLE_HINTS = [
    "developer", "engineer", "manager", "analyst", "recruiter", "assistant",
    "sales", "customer service", "administrator", "designer", "leader", "leadership",
]
_TARGET_POPULATION_HINTS = [
    "cxos", "director", "executive", "leadership", "population", "candidates",
    "people", "pool", "employees", "staff", "graduates", "entry-level",
]
_SENIORITY_HINTS = [
    "senior", "junior", "graduate", "mid-level", "mid professional", "entry-level",
    "director-level", "executive", "experienced", "years", "15+", "15 years",
    "5+ years", "4 years", "10 years",
]
_SKILL_HINTS = [
    "java", "python", ".net", "sql", "spring", "aws", "docker", "rust", "excel",
    "word", "hipaa", "medical terminology", "angular", "react", "node", "rest",
]
_LEADERSHIP_HINTS = [
    "leadership", "strategic thinking", "influencing", "people management", "mentor",
    "team", "manage others", "leadership benchmark",
]
_PERSONALITY_HINTS = [
    "personality", "behavior", "behaviour", "opq", "fit", "workplace behavior",
]
_COMPETENCY_HINTS = [
    "competency", "competencies", "skills", "capabilities", "capability", "behavioural",
]
_PURPOSE_HINTS = [
    "selection", "development", "developmental", "benchmark", "compare candidates",
    "re-skill", "talent audit",
]


def _is_injection_attempt(text: str) -> bool:
    return bool(_INJECTION_RE.search(text))


def _is_off_topic(text: str) -> bool:
    lowered = text.lower()
    on_topic_hit = any(hint in lowered for hint in _SHL_ON_TOPIC_HINTS)
    off_topic_hit = any(hint in lowered for hint in _OFF_TOPIC_HINTS)
    if on_topic_hit:
        return False
    return off_topic_hit


def _assistant_has_prior_shortlist(messages: List[ChatMessage]) -> bool:
    shortlist_url_re = re.compile(r"https?://www\.shl\.com/products/product-catalog/view/[\w\-]+/?", re.IGNORECASE)
    for msg in messages:
        if msg.role != "assistant":
            continue
        if shortlist_url_re.search(msg.content):
            return True
        lowered = msg.content.lower()
        if any(hint in lowered for hint in _ASSISTANT_SHORTLIST_HINTS):
            return True
    return False


def _is_compare(text: str) -> bool:
    return bool(_COMPARE_RE.search(text))


def _is_refine(text: str, has_prior_shortlist: bool) -> bool:
    if not has_prior_shortlist:
        return False
    lowered = text.lower()
    return any(hint in lowered for hint in _REFINE_HINTS)


def _is_confirmation(text: str) -> bool:
    """Detects an explicit sign-off on an existing shortlist.

    This intentionally excludes generic acknowledgements ("ok", "yes",
    "thanks", "perfect" on their own) -- those show up constantly mid-refine
    ("Thanks! Can you also add personality tests?") and would end the
    conversation right when the user is asking for more. Only phrases that
    plausibly stand for "we are done deciding" count. This is a heuristic,
    not a semantic classifier, so it will not catch every creative phrasing
    (e.g. "that covers it") -- a Gemini-backed intent signal would generalize
    further, but must still only ever *inform* this decision, never make it.
    """
    lowered = text.lower()
    confirmation_phrases = [
        "final list", "final shortlist", "that's final", "keep the shortlist",
        "keep the short list", "confirmed", "that's what we need",
        "that's what we need.", "lock it in", "locking it in", "go with that",
        "go with these", "we'll go with", "as-is", "finalize", "sign off",
        "shortlist as-is", "that works.", "that works,",
    ]
    return any(phrase in lowered for phrase in confirmation_phrases)


def _assistant_asked_recommendation_confirmation(messages: List[ChatMessage]) -> bool:
    for msg in messages:
        if msg.role != "assistant":
            continue
        lowered = msg.content.lower()
        if "exact match" in lowered or "closest assessments" in lowered or "recommend the closest" in lowered:
            return True
    return False


def _extract_slots(text: str) -> Dict[str, Any]:
    lowered = text.lower()
    slots: Dict[str, Any] = {
        "hiring_role": None,
        "target_population": None,
        "seniority": None,
        "assessment_purpose": None,
        "technical_skills": [],
        "leadership_requirements": [],
        "personality_requirements": [],
        "competencies": [],
    }

    if any(hint in lowered for hint in _ROLE_HINTS):
        for hint in ["developer", "engineer", "manager", "analyst", "assistant", "sales", "recruiter"]:
            if hint in lowered:
                slots["hiring_role"] = hint.title()
                break
        if slots["hiring_role"] is None:
            slots["hiring_role"] = "Role"

    if any(hint in lowered for hint in _TARGET_POPULATION_HINTS):
        if "cxos" in lowered or "director" in lowered or "executive" in lowered:
            slots["target_population"] = "executive / leadership population"
        elif "graduate" in lowered:
            slots["target_population"] = "graduates"
        else:
            slots["target_population"] = "target population"

    if any(hint in lowered for hint in _SENIORITY_HINTS):
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

    if any(hint in lowered for hint in _PURPOSE_HINTS):
        if "development" in lowered or "developmental" in lowered or "re-skill" in lowered:
            slots["assessment_purpose"] = "development"
        elif "selection" in lowered or "benchmark" in lowered or "compare candidates" in lowered:
            slots["assessment_purpose"] = "selection"

    for hint in _SKILL_HINTS:
        if hint in lowered:
            slots["technical_skills"].append(hint)
    for hint in _LEADERSHIP_HINTS:
        if hint in lowered:
            slots["leadership_requirements"].append(hint)
    for hint in _PERSONALITY_HINTS:
        if hint in lowered:
            slots["personality_requirements"].append(hint)
    for hint in _COMPETENCY_HINTS:
        if hint in lowered:
            slots["competencies"].append(hint)

    return slots


def _merge_slots(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                continue
            existing_list = merged.get(key, []) or []
            merged[key] = sorted(set(existing_list + value))
        elif not merged.get(key):
            merged[key] = value
    return merged


def _next_missing_slot(slots: Dict[str, Any], text: str) -> Optional[str]:
    lowered = text.lower()

    if not slots.get("assessment_purpose") and (
        "selection" in lowered or "development" in lowered or "developmental" in lowered or "benchmark" in lowered
        or slots.get("target_population") or slots.get("hiring_role") or slots.get("leadership_requirements")
    ):
        return "assessment_purpose"

    if not slots.get("target_population") and (
        "target population" in lowered or "leadership" in lowered or "cxos" in lowered or "director" in lowered
        or "executive" in lowered or "people" in lowered or "pool" in lowered or "candidates" in lowered
    ):
        return "target_population"

    if not slots.get("seniority") and (
        slots.get("hiring_role") or slots.get("technical_skills") or slots.get("target_population")
    ):
        return "seniority"

    if not slots.get("hiring_role") and (
        any(hint in lowered for hint in _ROLE_HINTS) or "hiring" in lowered or "role" in lowered
    ):
        return "hiring_role"

    if not slots.get("technical_skills") and (
        slots.get("hiring_role") or any(hint in lowered for hint in _SKILL_HINTS)
    ):
        return "technical_skills"

    if not slots.get("leadership_requirements") and (
        any(hint in lowered for hint in _LEADERSHIP_HINTS) or "leadership" in lowered
    ):
        return "leadership_requirements"

    if not slots.get("personality_requirements") and (
        any(hint in lowered for hint in _PERSONALITY_HINTS) or "personality" in lowered
    ):
        return "personality_requirements"

    if not slots.get("competencies") and (
        any(hint in lowered for hint in _COMPETENCY_HINTS) or "competencies" in lowered
    ):
        return "competencies"

    return None


def _clarification_question(slot_name: str) -> str:
    questions = {
        "target_population": "Who is the target population for this role?",
        "seniority": "What seniority level are you targeting?",
        "assessment_purpose": "Is this for selection or leadership development?",
        "hiring_role": "What role are you hiring for?",
        "technical_skills": "What technical skills are most important for this role?",
        "leadership_requirements": "What leadership requirements should the assessment capture?",
        "personality_requirements": "What personality or behavior traits matter most?",
        "competencies": "What competencies should the assessment cover?",
    }
    return questions.get(slot_name, "Could you tell me a bit more about the role and the hiring context?")


def _is_ready_to_recommend(slots: Dict[str, Any], all_user_text: str, already_clarified_once: bool) -> bool:
    has_context = bool(slots.get("hiring_role") or slots.get("target_population") or slots.get("technical_skills") or slots.get("leadership_requirements") or slots.get("personality_requirements") or slots.get("competencies"))
    has_seniority = bool(slots.get("seniority"))
    has_purpose = bool(slots.get("assessment_purpose"))
    has_specific_requirement = any(hint in all_user_text.lower() for hint in ["knowledge test", "numerical reasoning", "excel", "word", "sql", "spring", "java", "docker", "aws", "rust", "safety", "hipaa"])

    if has_context and (has_seniority or has_purpose or has_specific_requirement or already_clarified_once):
        return True

    if slots.get("assessment_purpose") and (slots.get("target_population") or slots.get("hiring_role") or slots.get("technical_skills") or slots.get("leadership_requirements")):
        return True

    return False


def classify_turn(messages: List[ChatMessage]) -> TurnDecision:
    user_messages = [m for m in messages if m.role == "user"]
    assistant_messages = [m for m in messages if m.role == "assistant"]
    latest = user_messages[-1].content if user_messages else ""
    all_user_text = " ".join(m.content for m in user_messages)

    if _is_injection_attempt(latest):
        return TurnDecision(action=TurnAction.REFUSE_INJECTION, query=latest)

    if _is_off_topic(latest):
        return TurnDecision(action=TurnAction.REFUSE_OFF_TOPIC, query=latest)

    has_prior_shortlist = _assistant_has_prior_shortlist(messages)
    state = _reconstruct_conversation_state(messages)

    if has_prior_shortlist and _is_confirmation(latest):
        # The user might finalize AND edit in the same breath ("Drop the OPQ.
        # Final list: Verify G+ and Graduate Scenarios."). Treat that as a
        # REFINE so the edit is actually applied, just with the conversation
        # marked complete -- rather than a COMPLETE that silently ignores the
        # edit and echoes the stale prior shortlist.
        if _is_refine(latest, has_prior_shortlist):
            return TurnDecision(
                action=TurnAction.REFINE,
                query=all_user_text,
                constraints=RetrievalConstraints(),
                end_of_conversation=True,
            )
        return TurnDecision(action=TurnAction.COMPLETE, query=all_user_text, end_of_conversation=True)

    if _assistant_asked_recommendation_confirmation(messages) and _is_confirmation(latest):
        return TurnDecision(
            action=TurnAction.RECOMMEND,
            query=all_user_text,
            constraints=RetrievalConstraints(),
            slots=state.slots,
        )

    if _is_compare(latest):
        terms = re.findall(r"\b[A-Z][A-Za-z0-9\+\.]{1,30}\b", latest)
        return TurnDecision(action=TurnAction.COMPARE, query=latest, compare_terms=terms[:4])

    if has_prior_shortlist and _is_refine(latest, has_prior_shortlist):
        return TurnDecision(
            action=TurnAction.REFINE,
            query=all_user_text,
            constraints=RetrievalConstraints(),
        )

    state = _reconstruct_conversation_state(messages)
    logger.debug(
        "Reconstructed conversation state from %d user turns and %d assistant turns: %s",
        state.user_turn_count,
        state.assistant_turn_count,
        state.debug_summary(),
    )

    next_slot = state.next_missing_slot(all_user_text)
    already_clarified_once = len(assistant_messages) >= 1

    if state.is_ready_to_recommend(all_user_text, already_clarified_once):
        logger.debug("Recommendation ready with recovered slots: %s", state.debug_summary())
        return TurnDecision(
            action=TurnAction.RECOMMEND,
            query=all_user_text,
            constraints=RetrievalConstraints(),
            slots=state.slots,
        )

    if next_slot:
        question = _clarification_question(next_slot)
        logger.debug(
            "Clarification required for slot '%s' because the state is still missing it: %s",
            next_slot,
            state.debug_summary(),
        )
        return TurnDecision(
            action=TurnAction.CLARIFY,
            query=latest,
            clarification_slot=next_slot,
            clarification_question=question,
            slots=state.slots,
        )

    logger.debug("No next missing slot found; defaulting to clarification with recovered state: %s", state.debug_summary())
    return TurnDecision(action=TurnAction.CLARIFY, query=latest, slots=state.slots)