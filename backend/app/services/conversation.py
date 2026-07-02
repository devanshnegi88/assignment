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
from app.core.config import settings
import json
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
        # Merge deterministic heuristic extraction first, then attempt a
        # Gemini-backed extraction if configured. Gemini results are merged
        # on top so they can fill gaps the heuristics miss.
        heuristics = _extract_slots(text)
        merged = _merge_slots(self.slots, heuristics)
        try:
            gemini_slots = _gemini_extract_slots(text)
            if isinstance(gemini_slots, dict):
                merged = _merge_slots(merged, gemini_slots)
        except Exception:
            # Non-fatal: keep heuristics-only merge
            pass
        self.slots = merged

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

    # Extract hiring role/context
    # Try to find explicit role mentions first
    if any(hint in lowered for hint in _ROLE_HINTS):
        # Priority order for specific roles
        for hint in ["developer", "engineer", "manager", "analyst", "sales", "assistant", "recruiter"]:
            if hint in lowered:
                slots["hiring_role"] = hint.title()
                break
        
        # If no specific role matched but role hints are present, try broader matching
        if slots["hiring_role"] is None:
            # Look for role-like patterns: "X operator", "X role", "X position", etc.
            role_pattern_matches = re.findall(r"([\w\s]+?)\s+(operator|position|role|level|function|specialist|professional|person)", lowered)
            if role_pattern_matches:
                potential_role = role_pattern_matches[0][0].strip()
                if potential_role and len(potential_role) < 30:
                    slots["hiring_role"] = potential_role.title()
            
            # Fallback: check for common organizational/domain references
            if slots["hiring_role"] is None:
                if "leadership" in lowered or "executive" in lowered:
                    slots["hiring_role"] = "Executive / Leadership"
                elif "frontline" in lowered or "entry-level" in lowered:
                    slots["hiring_role"] = "Entry-Level"
                else:
                    slots["hiring_role"] = "Position"

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
        elif "graduate" in lowered or "final-year" in lowered:
            slots["seniority"] = "graduate"
        elif "entry-level" in lowered or "no work experience" in lowered:
            slots["seniority"] = "entry-level"
        else:
            slots["seniority"] = "seniority"

    if any(hint in lowered for hint in _PURPOSE_HINTS):
        if "development" in lowered or "developmental" in lowered or "re-skill" in lowered:
            slots["assessment_purpose"] = "development"
        elif "selection" in lowered or "benchmark" in lowered or "compare candidates" in lowered or "talent audit" in lowered:
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


def _gemini_extract_slots(text: str) -> Dict[str, Any]:
    """Attempt to extract structured slots from free text using Gemini via
    the google.generativeai SDK or HTTP fallback. On any error return
    an empty dict so deterministic heuristics remain authoritative.
    """
    if settings.llm_provider != "gemini" or not settings.llm_api_key:
        return {}

    prompt = (
        "Extract the following fields from the user's request as JSON: "
        "hiring_role, target_population, seniority, assessment_purpose, "
        "technical_skills (array), leadership_requirements (array), "
        "personality_requirements (array), competencies (array). "
        "If a field is not present, use null or an empty array as appropriate. "
        "Only output valid JSON.\n\nUser text:\n" + text
    )

    # Try SDK
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.llm_api_key)
        resp = genai.generate(model=settings.llm_model, text=prompt)
        if resp and getattr(resp, "candidates", None):
            body = resp.candidates[0].content[0].text
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
    except Exception:
        pass

    # HTTP fallback
    try:
        import httpx

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.llm_model}:generateContent?key={settings.llm_api_key}"
        )
        resp = httpx.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=settings.llm_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        body = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    except Exception:
        return {}


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
    """Determine the next missing critical information for conversation completeness.
    
    Only concrete assessment names/domains count as "specific context".
    Broad terms like "leadership", "personality", "competency" alone don't suffice.
    """
    lowered = text.lower()
    
    # ONLY concrete, measurable assessment contexts count.
    # These are actual test names or very specific skill domains.
    concrete_assessment_hints = [
        # Technical skills (assessments exist for these)
        "numerical", "java", "python", "sql", "spring", "docker", "aws", "rust",
        "excel", "word", "coding", "programming",
        # Domain/industry-specific (assessments exist for these)
        "finance", "accounting", "medical", "safety", "pharmaceutical",
        "hipaa", "healthcare",
        # Specific assessment types
        "simulation", "scenarios", "interview", "questionnaire",
    ]
    has_concrete_context = any(hint in lowered for hint in concrete_assessment_hints)
    
    has_role = bool(slots.get("hiring_role") and slots.get("hiring_role") != "Position")
    has_seniority = bool(slots.get("seniority"))
    has_purpose = bool(slots.get("assessment_purpose"))
    
    # If we have explicit purpose (selection/development), we're ready to recommend
    if has_purpose:
        return None
    
    # If we have concrete assessment context (not just vague domain), we can recommend
    if has_concrete_context:
        return None
    
    # If we have role + seniority but NO specificity → ask for purpose/clarification
    if has_role and has_seniority:
        return "assessment_purpose"
    
    # If we only have role but not seniority → ask for seniority
    if has_role and not has_seniority:
        return "seniority"
    
    # If no role → ask for role
    return "hiring_role"


def _assistant_asked_for_slot(messages: List[ChatMessage], slot_name: str) -> bool:
    question = _clarification_question(slot_name).lower()
    for msg in messages:
        if msg.role != "assistant":
            continue
        if question in msg.content.lower():
            return True
    return False


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


def _is_conversation_complete(slots: Dict[str, Any]) -> bool:
    """Conversation is complete only when role + seniority are known,
    and either assessment_purpose is known OR we have specific domain
    hints (technical, personality, leadership, competency requirements).
    """
    has_role = bool(slots.get("hiring_role"))
    has_seniority = bool(slots.get("seniority"))
    has_purpose = bool(slots.get("assessment_purpose"))
    has_specific_domain = bool(
        slots.get("technical_skills")
        or slots.get("leadership_requirements")
        or slots.get("personality_requirements")
        or slots.get("competencies")
    )

    # Must have role + seniority
    if not (has_role and has_seniority):
        return False

    # And either explicit purpose or specific domain hints
    return has_purpose or has_specific_domain


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
        "Workflow: merged conversation state from %d user turns and %d assistant turns: %s",
        state.user_turn_count,
        state.assistant_turn_count,
        state.debug_summary(),
    )

    # ======================================================================
    # DETERMINISTIC WORKFLOW: Conversation Completeness → Retrieval
    # ======================================================================
    # Step 1: Check if conversation is complete (role → seniority → purpose/domain)
    # We ask for missing slots in strict order: never skip role or seniority.
    # ======================================================================

    next_missing_slot = state.next_missing_slot(all_user_text)

    if next_missing_slot:
        # Avoid asking the same clarification twice
        if _assistant_asked_for_slot(assistant_messages, next_missing_slot):
            # We already asked this; don't ask again. Skip to next missing slot.
            temp_slots = dict(state.slots)
            while next_missing_slot:
                temp_slots[next_missing_slot] = "_already_asked"
                next_missing_slot = _next_missing_slot(temp_slots, all_user_text)

        if next_missing_slot:
            # Found the next missing slot and haven't asked for it yet
            question = _clarification_question(next_missing_slot)
            logger.debug(
                "Conversation incomplete. Missing slot: '%s'. State: %s",
                next_missing_slot,
                state.debug_summary(),
            )
            return TurnDecision(
                action=TurnAction.CLARIFY,
                query=latest,
                clarification_slot=next_missing_slot,
                clarification_question=question,
                slots=state.slots,
            )

    # Step 2: Conversation is complete. Proceed to retrieval (pipeline.py will assess confidence).
    logger.debug("Conversation complete. Proceeding to retrieval. State: %s", state.debug_summary())
    return TurnDecision(
        action=TurnAction.RECOMMEND,
        query=all_user_text,
        constraints=RetrievalConstraints(),
        slots=state.slots,
    )