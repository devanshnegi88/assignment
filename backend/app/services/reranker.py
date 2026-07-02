from __future__ import annotations

import logging
from typing import List

from app.catalog.schema import CatalogItem
from app.services.llm import TemplateLLMProvider
from app.core.config import settings

logger = logging.getLogger("reranker")


def _build_rerank_prompt(query: str, decision_summary: str, candidates: List[CatalogItem]) -> str:
    lines = ["Rank the following SHL catalog items by how suitable they are for this request:", f"Request: {query}", f"Context: {decision_summary}"]
    lines.append("")
    for i, c in enumerate(candidates, start=1):
        lines.append(f"{i}. Name: {c.name}")
        lines.append(f"   URL: {c.url}")
        if c.test_type_labels:
            lines.append(f"   Types: {', '.join(c.test_type_labels)}")
        if c.job_levels:
            lines.append(f"   Levels: {', '.join(c.job_levels)}")
        if c.languages:
            lines.append(f"   Languages: {', '.join(c.languages)}")
        if c.duration_minutes:
            lines.append(f"   Duration: {c.duration_minutes} minutes")
        if c.description:
            desc = c.description.replace('\n', ' ')[:400]
            lines.append(f"   Desc: {desc}")
        lines.append("")
    lines.append(
        "Return a JSON array of the item URLs in order from most to least suitable."
    )
    return "\n".join(lines)


def rerank_candidates(candidates: List[CatalogItem], query: str, decision_summary: str) -> List[CatalogItem]:
    """Attempt to rerank candidates using Gemini (via the SDK). Fall back to
    keeping the original order if the provider is unavailable or fails."""
    if not candidates:
        return []

    prompt = _build_rerank_prompt(query, decision_summary, candidates)

    # Try google.generativeai SDK if configured
    if settings.llm_provider == "gemini" and settings.llm_api_key:
        try:
            import google.generativeai as genai
            import json

            genai.configure(api_key=settings.llm_api_key)
            resp = genai.generate(model=settings.llm_model, text=prompt)
            # extract candidate text defensively
            text = ""
            if resp and getattr(resp, "candidates", None):
                text = resp.candidates[0].content[0].text
            if not text:
                return candidates
            # find urls in returned JSON
            text = text.strip()
            # Attempt to parse JSON from the LLM response
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    urls = [u.rstrip("/").lower() for u in parsed if isinstance(u, str)]
                    ordered = []
                    seen = set()
                    for u in urls:
                        for c in candidates:
                            if c.url.rstrip("/").lower() == u and c.url not in seen:
                                ordered.append(c)
+                                seen.add(c.url)
+                                break
+                    # append any not mentioned at the end in original order
+                    for c in candidates:
+                        if c.url not in seen:
+                            ordered.append(c)
+                    return ordered
+            except Exception:
+                # Not JSON — ignore and fall through to keep original order
+                return candidates
+        except Exception as exc:
+            logger.info("Gemini reranker unavailable or failed: %s", exc)
+            return candidates
+
+    # No Gemini configured — return original order
+    return candidates
*** End Patch