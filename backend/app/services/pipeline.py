"""
Ties together conversation classification, grounded retrieval, and reply
generation into the exact response contract. Recommendations come only from
the offline catalog loaded from `catalog.json`.
"""
from __future__ import annotations

import difflib
import logging
from functools import lru_cache
import re
from typing import List

from app.catalog.loader import get_catalog, get_catalog_service
from app.core.config import settings
from app.retrieval.hybrid import HybridRetriever
from app.schemas.chat import ChatMessage, ChatResponse, Recommendation
from app.services.conversation import ConversationUnderstandingError, TurnAction, TurnDecision, classify_turn
from app.services.llm import LLMProviderError, get_llm_provider
from app.catalog.schema import CatalogItem
from app.retrieval.hybrid import RetrievalConstraints
from app.catalog.schema import TEST_TYPE_LABEL_TO_CODE


def slots_to_constraints(slots: dict) -> RetrievalConstraints:
    constraints = RetrievalConstraints()
    if not isinstance(slots, dict):
        return constraints
    # Seniority -> job_levels mapping
    seniority = slots.get("seniority")
    if isinstance(seniority, str) and seniority:
        s = seniority.lower()
        mapping = {
            "mid-level": "Mid-Professional",
            "mid professional": "Mid-Professional",
            "graduate": "Graduate",
            "entry-level": "Entry-Level",
            "senior": "Senior",
            "junior": "Entry-Level",
            "director": "Director",
            "executive": "Executive",
        }
        if s in mapping:
            constraints.job_levels.append(mapping[s])
        else:
            constraints.job_levels.append(seniority.title())

    # Assessment purpose -> test type codes
    purpose = slots.get("assessment_purpose")
    if isinstance(purpose, str) and purpose:
        p = purpose.lower()
        if "selection" in p:
            # Ability, Knowledge, Competencies, Personality
            constraints.test_type_codes.extend(["A", "K", "C", "P"])
        elif "development" in p:
            constraints.test_type_codes.extend(["D", "C", "P"])

    # Technical skills -> prefer Knowledge & Skills (K)
    tech = slots.get("technical_skills") or []
    if tech:
        constraints.test_type_codes.append("K")

    # Leadership requirements -> Competencies / Development
    if slots.get("leadership_requirements"):
        constraints.test_type_codes.extend(["C", "D"])

    # Personality requirements -> Personality code
    if slots.get("personality_requirements"):
        constraints.test_type_codes.append("P")

    # Competencies -> Competencies code
    if slots.get("competencies"):
        constraints.test_type_codes.append("C")

    # Language hints -> pass through (exact matching happens in retriever)
    langs = []
    for key in ("languages", "language"):
        val = slots.get(key)
        if isinstance(val, str) and val:
            langs.append(val)
        if isinstance(val, list):
            langs.extend(val)
    if langs:
        constraints.languages = [l for l in langs if l]

    # Deduplicate codes and job levels
    constraints.test_type_codes = list(dict.fromkeys([c for c in constraints.test_type_codes if c]))
    constraints.job_levels = list(dict.fromkeys([j for j in constraints.job_levels if j]))
    return constraints

logger = logging.getLogger("pipeline")


@lru_cache(maxsize=1)
def get_retriever() -> HybridRetriever:
    return HybridRetriever(catalog_service=get_catalog_service())


_SHORTLIST_URL_RE = re.compile(r"https?://www\.shl\.com/products/product-catalog/view/[^\s\)]+", re.IGNORECASE)

# Phrases the Gemini reply generator used for RECOMMEND / REFINE / COMPLETE
# turns. Kept in sync with app.services.conversation._ASSISTANT_SHORTLIST_HINTS
# so both modules agree on what counts as "the assistant announced a shortlist
# here".
_SHORTLIST_ANNOUNCEMENT_HINTS = [
    "that fit what you described", "i found", "i updated the shortlist",
    "final shortlist confirmed",
]
# Deliberately excludes generic words like "shortlist" or "recommend" on their
# own: both the off-topic refusal template and the compare template also use
# those words in passing, and matching on them would make an interrupting
# refusal or comparison turn look like a fresh shortlist announcement, wiping
# out the real one from a few turns back.


def _normalize_url(url: str) -> str:
    return url.rstrip("/").lower()


def _is_shortlist_announcement(text: str) -> bool:
    lowered = text.lower()
    return bool(_SHORTLIST_URL_RE.search(text)) or any(hint in lowered for hint in _SHORTLIST_ANNOUNCEMENT_HINTS)


def _extract_prior_shortlist(messages: List[ChatMessage], catalog: List[CatalogItem]) -> List[CatalogItem]:
    """Recovers the *current* committed shortlist from conversation history.

    The API is stateless: the client only ever resends role/content text, never
    the structured `recommendations` array from a previous response. So this has
    to read the shortlist back out of the assistant's own reply text. It looks
    only at the most recent message that reads like a shortlist announcement
    (rather than unioning names across the whole history), so that an item named
    in passing during an earlier `compare` turn -- or one already dropped by a
    later `refine` -- doesn't wrongly reappear.
    """
    last_announcement: str | None = None
    for msg in reversed(messages):
        if msg.role != "assistant":
            continue
        if _is_shortlist_announcement(msg.content):
            last_announcement = msg.content
            break
    if not last_announcement:
        return []

    seen = set()
    shortlist: List[CatalogItem] = []

    for url in _SHORTLIST_URL_RE.findall(last_announcement):
        normalized = _normalize_url(url)
        if normalized in seen:
            continue
        item = next((item for item in catalog if _normalize_url(item.url) == normalized), None)
        if item:
            seen.add(normalized)
            shortlist.append(item)

    # Also match items by exact name (word-boundary safe), since the reply text
    # names items instead of linking them -- URLs live only in the structured
    # `recommendations` field the client never resends.
    lowered = last_announcement.lower()
    for item in sorted(catalog, key=lambda i: len(i.name), reverse=True):
        normalized = _normalize_url(item.url)
        if normalized in seen or not item.name:
            continue
        pattern = rf"(?<![\w-]){re.escape(item.name.lower())}(?![\w-])"
        if re.search(pattern, lowered):
            seen.add(normalized)
            shortlist.append(item)

    return shortlist


def _resolve_item_names(names: List[str], catalog: List[CatalogItem]) -> List[CatalogItem]:
    items: List[CatalogItem] = []
    seen = set()
    for name in names:
        target = name.strip().lower()
        if not target:
            continue
        match = next(
            (item for item in catalog if item.name.lower() == target),
            None,
        )
        if match and _normalize_url(match.url) not in seen:
            seen.add(_normalize_url(match.url))
            items.append(match)
    return items


def _summarize_conversation(messages: List[ChatMessage], max_chars: int = 1200) -> str:
    lines = [f"{m.role}: {m.content}" for m in messages]
    text = "\n".join(lines)
    return text[-max_chars:]


def _resolve_compare_items(terms: List[str], catalog: List[CatalogItem]) -> List[CatalogItem]:
    """Fuzzy-match extracted terms against the offline catalog only."""
    if not terms:
        return []
    names = [item.name for item in catalog]
    matched: List[CatalogItem] = []
    seen_names = set()
    for term in terms:
        substring_hits = [item for item in catalog if term.lower() in item.name.lower()]
        if substring_hits:
            candidate = substring_hits[0]
        else:
            close = difflib.get_close_matches(term, names, n=1, cutoff=0.6)
            if not close:
                continue
            candidate = next(item for item in catalog if item.name == close[0])
        if candidate.name not in seen_names:
            matched.append(candidate)
            seen_names.add(candidate.name)
    return matched[:4]


def _to_recommendations(items: List[CatalogItem]) -> List[Recommendation]:
    return [
        Recommendation(
            name=item.name,
            url=item.url,
            test_type=" ".join(item.test_type_codes) if item.test_type_codes else "",
        )
        for item in items
    ]


def _normalize_for_exact_match(text: str) -> str:
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(normalized.split())


def _has_exact_catalog_match(query: str, catalog: List[CatalogItem]) -> bool:
    normalized_query = _normalize_for_exact_match(query)
    for item in catalog:
        normalized_name = _normalize_for_exact_match(item.name)
        if not normalized_name:
            continue
        if normalized_query == normalized_name:
            return True
        if re.search(rf"\b{re.escape(normalized_name)}\b", normalized_query):
            return True
    return False


def _assistant_asked_recommendation_confirmation(messages: List[ChatMessage]) -> bool:
    confirmation_prompts = [
        "exact match",
        "closest assessments",
        "recommend the closest",
        "recommend anyway",
    ]
    for msg in messages:
        if msg.role != "assistant":
            continue
        lowered = msg.content.lower()
        if any(prompt in lowered for prompt in confirmation_prompts):
            return True
    return False


def _assess_retrieval_confidence(
    query: str,
    shortlist: List[CatalogItem],
    catalog: List[CatalogItem],
) -> str:
    """Assess confidence in retrieval results.
    Returns 'HIGH', 'MEDIUM', or 'LOW'.

    HIGH: Exact catalog match for the query term.
    MEDIUM: Results exist but fuzzy match (user said something not in catalog name).
    LOW: No or very few results (user query doesn't match catalog well).
    """
    if not shortlist:
        return "LOW"

    # Check for exact catalog match
    if _has_exact_catalog_match(query, catalog):
        return "HIGH"

    # If we have results but no exact name match, it's a fuzzy/partial match
    return "MEDIUM"


def _should_ask_recommendation_confirmation(
    decision: TurnDecision,
    shortlist: List[CatalogItem],
    messages: List[ChatMessage],
    catalog: List[CatalogItem],
) -> bool:
    """Check if we should ask for confirmation before recommending.
    Only ask confirmation if confidence is MEDIUM (results exist but no exact match).
    Don't ask if confidence is LOW (no results) - that needs more clarification instead.
    """
    if decision.action != TurnAction.RECOMMEND:
        return False

    confidence = _assess_retrieval_confidence(decision.query, shortlist, catalog)

    # Only ask for confirmation if MEDIUM confidence (fuzzy match exists)
    if confidence != "MEDIUM":
        return False

    if _assistant_asked_recommendation_confirmation(messages):
        return False

    return True


def _should_ask_for_clarification_on_retrieval(
    decision: TurnDecision,
    shortlist: List[CatalogItem],
    catalog: List[CatalogItem],
) -> bool:
    """Check if retrieval confidence is too low.
    If so, ask for clarification instead of trying to recommend.
    """
    if decision.action != TurnAction.RECOMMEND:
        return False

    confidence = _assess_retrieval_confidence(decision.query, shortlist, catalog)
    return confidence == "LOW"


def run_turn(messages: List[ChatMessage]) -> ChatResponse:
    catalog_service = get_catalog_service()
    catalog = catalog_service.get_items()
    retriever = get_retriever()
    llm = get_llm_provider()

    turn_cap_reached = len(messages) >= settings.max_turns
    try:
        decision: TurnDecision = classify_turn(messages)
    except (ConversationUnderstandingError, LLMProviderError) as exc:
        logger.exception("Conversation understanding failed")
        return ChatResponse(
            reply=(
                "I'm temporarily unable to understand your request. "
                "Please try again in a moment."
            ),
            recommendations=[],
            end_of_conversation=False,
        )

    # Map extracted conversation slots into hard retrieval constraints so
    # that user-specified metadata (seniority, purpose, skills, languages)
    # influence the HybridRetriever.
    if decision.slots and (not decision.constraints or decision.constraints.is_empty()):
        try:
            from app.services.pipeline import slots_to_constraints as _s2c

            decision.constraints = _s2c(decision.slots)
        except Exception:
            pass
    shortlist: List[CatalogItem] = []
    previous_shortlist = _extract_prior_shortlist(messages, catalog)

    if decision.preferred_item_names:
        shortlist = _resolve_item_names(decision.preferred_item_names, catalog)
    elif decision.action == TurnAction.COMPLETE and previous_shortlist:
        shortlist = previous_shortlist
    elif decision.action == TurnAction.REFINE and previous_shortlist and not decision.preferred_item_names:
        shortlist = retriever.search(decision.query, decision.constraints)
    elif decision.action in (TurnAction.RECOMMEND, TurnAction.REFINE, TurnAction.COMPLETE):
        shortlist = retriever.search(decision.query, decision.constraints)
    elif decision.action == TurnAction.COMPARE:
        shortlist = _resolve_compare_items(decision.compare_terms, catalog)

    # Rerank candidates using Gemini if available (safe fallback keeps order)
    try:
        from app.services.reranker import rerank_candidates

        if shortlist and decision.action in (TurnAction.RECOMMEND, TurnAction.REFINE, TurnAction.COMPLETE):
            conversation_summary = _summarize_conversation(messages)
            shortlist = rerank_candidates(shortlist, decision.query, conversation_summary)
    except Exception:
        # Non-fatal: proceed with original shortlist
        pass

    # Assess retrieval confidence and decide outcome
    if _should_ask_for_clarification_on_retrieval(decision, shortlist, catalog):
        # LOW confidence: no results found. Ask for more specific clarification.
        # Don't offer "closest assessments" - ask the user to be more specific.
        decision = TurnDecision(
            action=TurnAction.CLARIFY,
            query=decision.query,
            clarification_question=(
                "I need more specific details to find the right assessment. "
                "Could you tell me more about: the seniority level, specific skills needed, "
                "or whether this is for selection or development?"
            ),
            slots=decision.slots,
        )
        shortlist = []
    elif _should_ask_recommendation_confirmation(decision, shortlist, messages, catalog):
        # MEDIUM confidence: results exist but no exact catalog name match. 
        # Ask if they want closest matches.
        decision = TurnDecision(
            action=TurnAction.CLARIFY,
            query=decision.query,
            clarification_question=(
                "I couldn't find an exact match for that request in the SHL catalog. "
                "Would you like me to recommend the closest assessments anyway?"
            ),
            slots=decision.slots,
        )
        shortlist = []

    conversation_summary = _summarize_conversation(messages)
    try:
        reply = llm.generate_reply(decision, shortlist, conversation_summary)
    except LLMProviderError:
        logger.exception("LLM reply generation failed")
        return ChatResponse(
            reply=(
                "I'm temporarily unable to generate a response right now. "
                "Please try again in a moment."
            ),
            recommendations=[],
            end_of_conversation=False,
        )

    recommendations = (
        _to_recommendations(shortlist)
        if decision.action in (TurnAction.RECOMMEND, TurnAction.REFINE, TurnAction.COMPLETE)
        else []
    )

    end_of_conversation = turn_cap_reached or decision.end_of_conversation
    if turn_cap_reached:
        reply = reply + " We've reached the end of this conversation -- feel free to start a new one if you'd like to keep refining."

    return ChatResponse(
        reply=reply,
        recommendations=recommendations,
        end_of_conversation=end_of_conversation,
    )