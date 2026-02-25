from __future__ import annotations

import json

import redis
import structlog

from shared.config_loader import load_pipeline_config
from shared.constants import ACTIVITY_CHANNEL, ACTIVITY_LOG_KEY
from shared.models import ActivityLog, AgentMessage

logger = structlog.get_logger()


def get_redis_client() -> redis.Redis:
    config = load_pipeline_config()["redis"]
    return redis.Redis(
        host=config["host"],
        port=config["port"],
        db=config["db"],
        decode_responses=True,
    )


def enqueue_message(client: redis.Redis, queue: str, message: AgentMessage) -> None:
    client.lpush(queue, message.model_dump_json())
    logger.info("message_enqueued", queue=queue, action=message.action, story_id=message.story_id)


def dequeue_message(client: redis.Redis, queue: str, timeout: int = 30) -> AgentMessage | None:
    result = client.brpop(queue, timeout=timeout)
    if result is None:
        return None
    _, raw = result
    return AgentMessage.model_validate_json(raw)


def publish_activity(client: redis.Redis, log: ActivityLog) -> None:
    data = log.model_dump_json()
    client.lpush(ACTIVITY_LOG_KEY, data)
    client.ltrim(ACTIVITY_LOG_KEY, 0, 999)  # keep last 1000
    client.publish(ACTIVITY_CHANNEL, data)


def get_recent_activity(client: redis.Redis, count: int = 50) -> list[ActivityLog]:
    raw_items = client.lrange(ACTIVITY_LOG_KEY, 0, count - 1)
    return [ActivityLog.model_validate_json(item) for item in raw_items]
