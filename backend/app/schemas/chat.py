"""
API contract, verbatim from the assignment PDF (page 3-4).

These shapes are non-negotiable per the spec: "Deviating breaks our
automated evaluator, and your submission will not score." Do not add
fields, rename fields, or wrap the response -- even for good reasons.
"""
from __future__ import annotations

from typing import List, Literal
from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]

    @field_validator("messages")
    @classmethod
    def _not_empty(cls, v: List[ChatMessage]) -> List[ChatMessage]:
        if not v:
            raise ValueError("messages must not be empty")
        return v


class Recommendation(BaseModel):
    name: str
    url: str
    test_type: str


class ChatResponse(BaseModel):
    reply: str
    recommendations: List[Recommendation] = Field(default_factory=list)
    end_of_conversation: bool = False

    @field_validator("recommendations")
    @classmethod
    def _at_most_ten(cls, v: List[Recommendation]) -> List[Recommendation]:
        if len(v) > 10:
            raise ValueError("recommendations must contain at most 10 items")
        return v


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
