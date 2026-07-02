"""
Normalized schema for a single SHL catalog entry.

This is the shape every scraped item is coerced into, regardless of which
part of the scraper produced it (listing row vs. detail page). Keeping one
schema means retrieval/embedding code downstream never has to guess which
fields are present.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator

# SHL's official legend for the single-letter Test Type codes shown in the
# catalog table and on each product's detail page.
TEST_TYPE_LEGEND = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}

TEST_TYPE_LABEL_TO_CODE = {label: code for code, label in TEST_TYPE_LEGEND.items()}


def _labels_to_codes(labels: List[str]) -> List[str]:
    seen: List[str] = []
    for label in labels:
        if not isinstance(label, str):
            continue
        code = TEST_TYPE_LABEL_TO_CODE.get(label.strip())
        if code and code not in seen:
            seen.append(code)
    return seen


class CatalogItem(BaseModel):
    name: str
    url: str
    # Solutions catalog splits into "Individual Test Solutions" (in scope
    # for this project) and "Pre-packaged Job Solutions" (explicitly out of
    # scope per the assignment). We tag it so it's easy to filter/verify.
    solution_type: str = Field(default="individual_test_solution")

    test_type_codes: List[str] = Field(default_factory=list)
    test_type_labels: List[str] = Field(default_factory=list)

    remote_testing: Optional[bool] = None
    adaptive_irt: Optional[bool] = None

    description: Optional[str] = None
    job_levels: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    duration_minutes: Optional[int] = None

    downloads: List[str] = Field(default_factory=list)

    # Set to True only for records where we successfully parsed the detail
    # page. Listing-only records (e.g. if detail scraping was skipped or
    # failed) are still included but flagged, so downstream code can decide
    # whether to trust them for grounding.
    detail_scraped: bool = False

    @field_validator("test_type_codes")
    @classmethod
    def _dedupe_codes(cls, v: List[str]) -> List[str]:
        seen = []
        for c in v:
            c = c.strip().upper()
            if c and c not in seen:
                seen.append(c)
        return seen

    def with_labels(self) -> "CatalogItem":
        self.test_type_labels = [
            TEST_TYPE_LEGEND.get(c, c) for c in self.test_type_codes
        ]
        return self
