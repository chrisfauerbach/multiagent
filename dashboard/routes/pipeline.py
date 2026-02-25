from __future__ import annotations

import uuid

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from shared.constants import QUEUE_ORCHESTRATOR
from shared.elasticsearch_client import get_es_client, get_pipeline_counts, list_stories
from shared.models import AgentMessage
from shared.redis_client import enqueue_message, get_redis_client

router = APIRouter()
templates: Jinja2Templates = None  # type: ignore  # set by app.py


@router.get("/")
async def index(request: Request):
    es = get_es_client()
    counts = get_pipeline_counts(es)
    active_stories = list_stories(es, size=20)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "counts": counts,
        "stories": active_stories,
    })


@router.post("/api/pipeline/trigger")
async def trigger_story(user_prompt: str = Form("")):
    client = get_redis_client()
    story_id = uuid.uuid4().hex[:12]
    payload = {}
    if user_prompt.strip():
        payload["user_prompt"] = user_prompt.strip()
    msg = AgentMessage(
        story_id=story_id,
        action="start_new_story",
        payload=payload,
        source="dashboard",
        target="orchestrator",
    )
    enqueue_message(client, QUEUE_ORCHESTRATOR, msg)
    return RedirectResponse(url="/", status_code=303)
