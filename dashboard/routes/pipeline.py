from __future__ import annotations

import uuid

import httpx
import structlog
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from shared.config_loader import load_pipeline_config
from shared.constants import QUEUE_ORCHESTRATOR
from shared.elasticsearch_client import get_es_client, get_pipeline_counts, list_stories
from shared.models import AgentMessage
from shared.redis_client import enqueue_message, get_redis_client

logger = structlog.get_logger()
router = APIRouter()
templates: Jinja2Templates = None  # type: ignore  # set by app.py


def _fetch_ollama_models() -> list[dict]:
    """Fetch installed models from Ollama's /api/tags endpoint."""
    config = load_pipeline_config()["ollama"]
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{config['base_url']}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return [
                {"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 1)}
                for m in models
            ]
    except Exception:
        logger.warning("ollama_models_fetch_failed")
        return []


@router.get("/")
async def index(request: Request):
    es = get_es_client()
    counts = get_pipeline_counts(es)
    active_stories = list_stories(es, size=20)
    config = load_pipeline_config()["ollama"]
    models = _fetch_ollama_models()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "counts": counts,
        "stories": active_stories,
        "models": models,
        "default_model": config["model"],
    })


@router.post("/api/pipeline/trigger")
async def trigger_story(user_prompt: str = Form(""), model: str = Form("")):
    client = get_redis_client()
    story_id = uuid.uuid4().hex[:12]
    payload = {}
    if user_prompt.strip():
        payload["user_prompt"] = user_prompt.strip()
    if model.strip():
        payload["model"] = model.strip()
    msg = AgentMessage(
        story_id=story_id,
        action="start_new_story",
        payload=payload,
        source="dashboard",
        target="orchestrator",
    )
    enqueue_message(client, QUEUE_ORCHESTRATOR, msg)
    return RedirectResponse(url="/", status_code=303)
