from __future__ import annotations

import json
import logging
from typing import List

from app.catalog.schema import CatalogItem
from app.core.config import settings
from app.prompts.jinja import render_prompt

logger = logging.getLogger("reranker")


def _build_rerank_prompt(query: str, decision_summary: str, candidates: List[CatalogItem]) -> str:
    return render_prompt(
        "rerank.j2",
        query=query,
        decision_summary=decision_summary,
        candidates=[
            {
                "url": item.url,
                "name": item.name,
                "test_type_labels": item.test_type_labels,
                "job_levels": item.job_levels,
                "languages": item.languages,
                "duration_minutes": item.duration_minutes,
                "description": item.description or "",
            }
            for item in candidates
        ],
    )


def rerank_candidates(candidates: List[CatalogItem], query: str, decision_summary: str) -> List[CatalogItem]:
    """Attempt to rerank candidates using Gemini (via the SDK). Fall back to
    keeping the original order if the provider is unavailable or fails."""
    if not candidates:
        return []

    if settings.llm_provider != "gemini" or not settings.llm_api_key:
        return candidates

    prompt = _build_rerank_prompt(query, decision_summary, candidates)

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.llm_api_key)
        resp = genai.generate(model=settings.llm_model, text=prompt)
        text = ""
        if resp and getattr(resp, "candidates", None):
            text = resp.candidates[0].content[0].text
        if not text:
            return candidates
        parsed = json.loads(text.strip())
        if not isinstance(parsed, list):
            return candidates

        urls = [u.rstrip("/").lower() for u in parsed if isinstance(u, str)]
        ordered = []
        seen = set()
        for url in urls:
            for item in candidates:
                if item.url.rstrip("/").lower() == url and item.url not in seen:
                    ordered.append(item)
                    seen.add(item.url)
                    break
        for item in candidates:
            if item.url not in seen:
                ordered.append(item)
        return ordered
    except Exception as exc:
        logger.info("Gemini reranker unavailable or failed: %s", exc)
        return candidates
*** End Patch