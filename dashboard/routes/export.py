from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response

from shared.elasticsearch_client import get_es_client, get_story
from dashboard.pdf_export import generate_single_story_pdf, generate_anthology_pdf

router = APIRouter()


@router.get("/stories/{story_id}/pdf")
async def download_story_pdf(story_id: str):
    es = get_es_client()
    story = get_story(es, story_id)
    if not story:
        return Response("Story not found", status_code=404)

    pdf_bytes = generate_single_story_pdf(story)
    slug = (story.title or "story").replace(" ", "_").lower()[:40]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{slug}.pdf"'},
    )


@router.get("/api/stories/pdf")
async def download_anthology_pdf(ids: list[str] = Query(...)):
    es = get_es_client()
    stories = [get_story(es, sid) for sid in ids]
    stories = [s for s in stories if s and s.current_draft]

    if not stories:
        return Response("No stories found", status_code=404)

    if len(stories) == 1:
        pdf_bytes = generate_single_story_pdf(stories[0])
        slug = (stories[0].title or "story").replace(" ", "_").lower()[:40]
        filename = f"{slug}.pdf"
    else:
        pdf_bytes = generate_anthology_pdf(stories)
        filename = "anthology.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
