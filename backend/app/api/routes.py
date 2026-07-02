"""
The only two HTTP endpoints this project exposes, per the PDF spec.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.catalog.loader import CatalogUnavailable
from app.schemas.chat import ChatRequest, ChatResponse, HealthResponse
from app.services.pipeline import run_turn

logger = logging.getLogger("api")

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        return run_turn(request.messages)
    except CatalogUnavailable as exc:
        # Missing/empty catalog is a deployment problem, not a reason to
        # 500 or to fall back to LLM-memory recommendations. Return a
        # schema-valid response that's honest about the situation.
        logger.error("Catalog unavailable: %s", exc)
        return ChatResponse(
            reply=(
                "I'm temporarily unable to search the SHL assessment catalog. "
                "Please try again in a moment."
            ),
            recommendations=[],
            end_of_conversation=False,
        )
    except Exception:
        # Last-resort safety net per "Error Handling: unexpected exceptions --
        # always return valid responses." Never leak a stack trace or a
        # non-schema-compliant body to the evaluator.
        logger.exception("Unexpected error handling /chat request")
        return ChatResponse(
            reply="Something went wrong on my end -- could you try rephrasing that?",
            recommendations=[],
            end_of_conversation=False,
        )
