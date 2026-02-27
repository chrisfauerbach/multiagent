from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from shared.elasticsearch_client import (
    delete_anthology,
    get_anthology,
    get_es_client,
    get_story,
    list_anthologies,
    list_stories,
    save_anthology,
)
from shared.models import Anthology
from shared.ollama_client import generate
from dashboard.pdf_export import generate_anthology_pdf

router = APIRouter()
templates: Jinja2Templates = None  # type: ignore  # set by app.py


@router.get("/anthologies")
async def anthologies_list(request: Request):
    es = get_es_client()
    anthologies = list_anthologies(es)
    return templates.TemplateResponse("anthologies_list.html", {
        "request": request,
        "anthologies": anthologies,
    })


@router.get("/anthologies/{anthology_id}")
async def anthology_detail(request: Request, anthology_id: str):
    es = get_es_client()
    anthology = get_anthology(es, anthology_id)
    if not anthology:
        return Response("Anthology not found", status_code=404)

    # Fetch included stories
    included_stories = []
    for sid in anthology.story_ids:
        story = get_story(es, sid)
        if story:
            included_stories.append(story)

    # Fetch published stories not already included for the "Add Stories" section
    all_published = list_stories(es, status="PUBLISHED", size=200)
    included_set = set(anthology.story_ids)
    available_stories = [s for s in all_published if s.story_id not in included_set]

    return templates.TemplateResponse("anthology_detail.html", {
        "request": request,
        "anthology": anthology,
        "included_stories": included_stories,
        "available_stories": available_stories,
    })


@router.post("/api/anthologies")
async def create_anthology(title: str = Form(...)):
    es = get_es_client()
    anthology = Anthology(title=title.strip())
    save_anthology(es, anthology)
    return RedirectResponse(f"/anthologies/{anthology.anthology_id}", status_code=303)


@router.post("/api/anthologies/{anthology_id}/stories")
async def add_stories(anthology_id: str, request: Request):
    es = get_es_client()
    anthology = get_anthology(es, anthology_id)
    if not anthology:
        return Response("Anthology not found", status_code=404)

    form = await request.form()
    story_ids = form.getlist("story_ids")
    existing = set(anthology.story_ids)
    for sid in story_ids:
        if sid not in existing:
            anthology.story_ids.append(sid)
            existing.add(sid)
    save_anthology(es, anthology)
    return RedirectResponse(f"/anthologies/{anthology_id}", status_code=303)


@router.post("/api/anthologies/{anthology_id}/stories/{story_id}/remove")
async def remove_story(anthology_id: str, story_id: str):
    es = get_es_client()
    anthology = get_anthology(es, anthology_id)
    if not anthology:
        return Response("Anthology not found", status_code=404)

    anthology.story_ids = [sid for sid in anthology.story_ids if sid != story_id]
    save_anthology(es, anthology)
    return RedirectResponse(f"/anthologies/{anthology_id}", status_code=303)


@router.post("/api/anthologies/{anthology_id}/title")
async def update_title(anthology_id: str, title: str = Form(...)):
    es = get_es_client()
    anthology = get_anthology(es, anthology_id)
    if not anthology:
        return Response("Anthology not found", status_code=404)

    anthology.title = title.strip()
    save_anthology(es, anthology)
    return RedirectResponse(f"/anthologies/{anthology_id}", status_code=303)


@router.post("/api/anthologies/{anthology_id}/generate-description")
async def generate_description(anthology_id: str):
    es = get_es_client()
    anthology = get_anthology(es, anthology_id)
    if not anthology:
        return Response("Anthology not found", status_code=404)

    # Build context from included stories
    story_summaries = []
    for sid in anthology.story_ids:
        story = get_story(es, sid)
        if story:
            genre = story.prompt.genre.replace("_", " ").title() if story.prompt and story.prompt.genre else "Unknown"
            excerpt = (story.current_draft or "")[:300]
            story_summaries.append(f"- \"{story.title}\" (Genre: {genre})\n  Excerpt: {excerpt}...")

    if not story_summaries:
        anthology.description = "An anthology of collected stories."
        save_anthology(es, anthology)
        return RedirectResponse(f"/anthologies/{anthology_id}", status_code=303)

    stories_context = "\n".join(story_summaries)
    prompt = (
        f"Write a compelling 2-3 sentence description for an anthology titled \"{anthology.title}\" "
        f"that contains the following stories:\n\n{stories_context}\n\n"
        f"The description should capture the themes and mood of the collection. "
        f"Write only the description, no preamble."
    )
    system_prompt = "You are a literary editor writing anthology descriptions for book covers."

    result = generate(prompt, system_prompt=system_prompt)
    anthology.description = result.text.strip()
    save_anthology(es, anthology)
    return RedirectResponse(f"/anthologies/{anthology_id}", status_code=303)


@router.post("/api/anthologies/{anthology_id}/description")
async def save_description(anthology_id: str, description: str = Form(...)):
    es = get_es_client()
    anthology = get_anthology(es, anthology_id)
    if not anthology:
        return Response("Anthology not found", status_code=404)

    anthology.description = description.strip()
    save_anthology(es, anthology)
    return RedirectResponse(f"/anthologies/{anthology_id}", status_code=303)


@router.post("/api/anthologies/{anthology_id}/delete")
async def delete_anthology_route(anthology_id: str):
    es = get_es_client()
    delete_anthology(es, anthology_id)
    return RedirectResponse("/anthologies", status_code=303)


@router.get("/anthologies/{anthology_id}/pdf")
async def download_anthology_pdf(anthology_id: str):
    es = get_es_client()
    anthology = get_anthology(es, anthology_id)
    if not anthology:
        return Response("Anthology not found", status_code=404)

    stories = []
    for sid in anthology.story_ids:
        story = get_story(es, sid)
        if story and story.current_draft:
            stories.append(story)

    if not stories:
        return Response("No stories with content found in this anthology", status_code=404)

    pdf_bytes = generate_anthology_pdf(
        stories,
        title=anthology.title,
        description=anthology.description,
    )
    slug = (anthology.title or "anthology").replace(" ", "_").lower()[:40]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{slug}.pdf"'},
    )
