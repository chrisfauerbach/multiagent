from __future__ import annotations

import difflib
from markupsafe import Markup

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from shared.elasticsearch_client import get_es_client, get_story, list_stories

router = APIRouter()
templates: Jinja2Templates = None  # type: ignore  # set by app.py


def _word_diff(old: str, new: str) -> str:
    """Return HTML with <ins>/<del> tags showing word-level changes."""
    old_words = old.split()
    new_words = new.split()
    sm = difflib.SequenceMatcher(None, old_words, new_words)
    parts: list[str] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            parts.append(" ".join(old_words[i1:i2]))
        elif op == "delete":
            parts.append(f'<del>{"  ".join(old_words[i1:i2])}</del>')
        elif op == "insert":
            parts.append(f'<ins>{" ".join(new_words[j1:j2])}</ins>')
        elif op == "replace":
            parts.append(f'<del>{" ".join(old_words[i1:i2])}</del>')
            parts.append(f'<ins>{" ".join(new_words[j1:j2])}</ins>')
    return " ".join(parts)


def _build_revision_diffs(story) -> list[dict]:
    """Build diff HTML for each revision against its predecessor."""
    if not story or not story.revisions:
        return []

    diffs: list[dict] = []
    for i, rev in enumerate(story.revisions):
        if i == 0:
            # No prior version stored — show full text as all-new
            diff_html = f"<ins>{rev.content}</ins>"
            label = "Initial draft → Revision 1"
        else:
            prev = story.revisions[i - 1]
            diff_html = _word_diff(prev.content, rev.content)
            label = f"Revision {prev.round_number} → Revision {rev.round_number}"

        diffs.append({
            "round_number": rev.round_number,
            "label": label,
            "timestamp": rev.timestamp,
            "feedback_addressed": rev.feedback_addressed,
            "diff_html": Markup(diff_html),
        })

    return diffs


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
    diffs = _build_revision_diffs(story)
    return templates.TemplateResponse("story_detail.html", {
        "request": request,
        "story": story,
        "revision_diffs": diffs,
    })
