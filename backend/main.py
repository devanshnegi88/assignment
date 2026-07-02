from __future__ import annotations

import logging

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.catalog.loader import CatalogUnavailable, get_catalog_service
from app.schemas.chat import ChatResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(
    title="SHL Conversational Assessment Recommender",
    description="Stateless conversational agent that recommends SHL Individual Test Solutions.",
    version="1.0.0",
)

allowed_origins = os.getenv("ALLOWED_CORS_ORIGINS", "*")
if allowed_origins == "*":
    origins = ["*"]
else:
    origins = [origin.strip() for origin in allowed_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(router)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():

    assets_dir = FRONTEND_DIR / "assets"

    if assets_dir.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="assets",
        )

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(FRONTEND_DIR / "index.html")

else:

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "service": "SHL Conversational Assessment Recommender",
            "status": "running",
            "health": "/health",
            "chat": "/chat",
        }


@app.on_event("startup")
def startup_event() -> None:
    try:
        get_catalog_service()
    except CatalogUnavailable as exc:
        raise RuntimeError(f"Catalog startup failed: {exc}") from exc


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Invalid schema on POST /chat (e.g. empty messages, malformed body):
    still respond with the same ChatResponse shape rather than FastAPI's
    default 422 error body, per 'Error Handling: invalid schema -- always
    return valid responses.' /health has no request body, so this only
    ever fires for /chat."""
    logging.getLogger("api").warning("Invalid request schema: %s", exc.errors())
    fallback = ChatResponse(
        reply=(
            "I couldn't read that request -- it should include a non-empty "
            "'messages' array with 'role' and 'content' on each message."
        ),
        recommendations=[],
        end_of_conversation=False,
    )
    return JSONResponse(status_code=200, content=fallback.model_dump())
