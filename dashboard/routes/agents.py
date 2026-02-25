from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from shared.elasticsearch_client import get_activity_logs, get_es_client
from shared.redis_client import get_redis_client, get_recent_activity

router = APIRouter()
templates: Jinja2Templates = None  # type: ignore  # set by app.py


@router.get("/agents/activity")
async def agent_log(request: Request):
    es = get_es_client()
    logs = get_activity_logs(es, size=200)
    return templates.TemplateResponse("agent_log.html", {
        "request": request,
        "logs": logs,
    })


@router.get("/api/agents/health")
async def agents_health():
    client = get_redis_client()
    recent = get_recent_activity(client, count=20)
    # Group by agent name, show latest activity
    agent_status = {}
    for log in recent:
        if log.agent_name not in agent_status:
            agent_status[log.agent_name] = {
                "agent": log.agent_name,
                "last_action": log.action,
                "last_seen": log.timestamp.isoformat(),
            }
    return {"agents": list(agent_status.values())}
