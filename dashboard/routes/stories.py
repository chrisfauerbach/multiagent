from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from shared.elasticsearch_client import get_es_client, get_story, list_stories

router = APIRouter()
templates: Jinja2Templates = None  # type: ignore  # set by app.py


@router.get("/stories")
async def stories_list(request: Request, status: str | None = None):
    es = get_es_client()
    all_stories = list_stories(es, status=status, size=100)
    return templates.TemplateResponse("stories_list.html", {
        "request": request,
        "stories": all_stories,
        "current_status": status,
    })


@router.get("/stories/{story_id}")
async def story_detail(request: Request, story_id: str):
    es = get_es_client()
    story = get_story(es, story_id)
    return templates.TemplateResponse("story_detail.html", {
        "request": request,
        "story": story,
    })
