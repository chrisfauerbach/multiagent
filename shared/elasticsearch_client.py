from __future__ import annotations

from datetime import datetime, timezone

from elasticsearch import Elasticsearch
import structlog

from shared.config_loader import load_pipeline_config
from shared.constants import ACTIVITY_LOGS_INDEX, ANTHOLOGIES_INDEX, STORIES_INDEX
from shared.models import ActivityLog, Anthology, Story

logger = structlog.get_logger()


def get_es_client() -> Elasticsearch:
    config = load_pipeline_config()["elasticsearch"]
    return Elasticsearch(config["hosts"])


# --- Story CRUD ---

def save_story(es: Elasticsearch, story: Story) -> None:
    story.updated_at = datetime.now(timezone.utc)
    es.index(index=STORIES_INDEX, id=story.story_id, document=story.model_dump(mode="json"))
    logger.info("story_saved", story_id=story.story_id, status=story.status)


def get_story(es: Elasticsearch, story_id: str) -> Story | None:
    try:
        result = es.get(index=STORIES_INDEX, id=story_id)
        return Story.model_validate(result["_source"])
    except Exception:
        return None


def list_stories(es: Elasticsearch, status: str | None = None, size: int = 50) -> list[Story]:
    query: dict = {"match_all": {}} if status is None else {"term": {"status": status}}
    try:
        result = es.search(
            index=STORIES_INDEX,
            query=query,
            sort=[{"updated_at": {"order": "desc"}}],
            size=size,
        )
        return [Story.model_validate(hit["_source"]) for hit in result["hits"]["hits"]]
    except Exception:
        return []


def list_in_progress_stories(es: Elasticsearch, size: int = 200) -> list[Story]:
    """Return all non-PUBLISHED stories, oldest first (for restart recovery)."""
    query = {"bool": {"must_not": [{"term": {"status": "PUBLISHED"}}]}}
    try:
        result = es.search(
            index=STORIES_INDEX,
            query=query,
            sort=[{"created_at": {"order": "asc"}}],
            size=size,
        )
        return [Story.model_validate(hit["_source"]) for hit in result["hits"]["hits"]]
    except Exception:
        logger.error("list_in_progress_stories_failed")
        return []


def get_pipeline_counts(es: Elasticsearch) -> dict[str, int]:
    try:
        result = es.search(
            index=STORIES_INDEX,
            size=0,
            aggs={"by_status": {"terms": {"field": "status", "size": 20}}},
        )
        return {
            bucket["key"]: bucket["doc_count"]
            for bucket in result["aggregations"]["by_status"]["buckets"]
        }
    except Exception:
        return {}


# --- Activity Logs ---

def log_activity(es: Elasticsearch, log: ActivityLog) -> None:
    es.index(index=ACTIVITY_LOGS_INDEX, document=log.model_dump(mode="json"))


def get_activity_logs(es: Elasticsearch, size: int = 100) -> list[ActivityLog]:
    try:
        result = es.search(
            index=ACTIVITY_LOGS_INDEX,
            query={"match_all": {}},
            sort=[{"timestamp": {"order": "desc"}}],
            size=size,
        )
        return [ActivityLog.model_validate(hit["_source"]) for hit in result["hits"]["hits"]]
    except Exception:
        return []


# --- Anthology CRUD ---

def save_anthology(es: Elasticsearch, anthology: Anthology) -> None:
    anthology.updated_at = datetime.now(timezone.utc)
    es.index(index=ANTHOLOGIES_INDEX, id=anthology.anthology_id, document=anthology.model_dump(mode="json"))
    logger.info("anthology_saved", anthology_id=anthology.anthology_id)


def get_anthology(es: Elasticsearch, anthology_id: str) -> Anthology | None:
    try:
        result = es.get(index=ANTHOLOGIES_INDEX, id=anthology_id)
        return Anthology.model_validate(result["_source"])
    except Exception:
        return None


def list_anthologies(es: Elasticsearch, size: int = 50) -> list[Anthology]:
    try:
        result = es.search(
            index=ANTHOLOGIES_INDEX,
            query={"match_all": {}},
            sort=[{"updated_at": {"order": "desc"}}],
            size=size,
        )
        return [Anthology.model_validate(hit["_source"]) for hit in result["hits"]["hits"]]
    except Exception:
        return []


def delete_anthology(es: Elasticsearch, anthology_id: str) -> None:
    try:
        es.delete(index=ANTHOLOGIES_INDEX, id=anthology_id)
        logger.info("anthology_deleted", anthology_id=anthology_id)
    except Exception:
        logger.error("anthology_delete_failed", anthology_id=anthology_id)
