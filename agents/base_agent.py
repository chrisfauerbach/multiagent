from __future__ import annotations

import abc
import time
import traceback

import structlog

from shared.config_loader import load_pipeline_config
from shared.elasticsearch_client import get_es_client, log_activity
from shared.logging_config import setup_logging
from shared.models import ActivityLog, AgentMessage, AgentMetrics, OllamaUsage, Story
from shared.redis_client import dequeue_message, get_redis_client, publish_activity


class BaseAgent(abc.ABC):
    def __init__(self, agent_name: str, listen_queue: str):
        self.agent_name = agent_name
        self.listen_queue = listen_queue
        self.logger: structlog.stdlib.BoundLogger = setup_logging(agent_name)
        self.config = load_pipeline_config()
        self.redis = get_redis_client()
        self.es = get_es_client()
        self.timeout = self.config["pipeline"]["queue_timeout"]
        self.loop_interval = self.config["pipeline"]["agent_loop_interval"]

    def log_activity(self, action: str, detail: str = "", story_id: str = "") -> None:
        entry = ActivityLog(
            agent_name=self.agent_name,
            story_id=story_id,
            action=action,
            detail=detail,
        )
        publish_activity(self.redis, entry)
        log_activity(self.es, entry)

    def record_metrics(
        self,
        story: Story,
        action: str,
        duration: float,
        usage: OllamaUsage,
        round_number: int = 0,
    ) -> None:
        m = AgentMetrics(
            agent=self.agent_name,
            action=action,
            round_number=round_number,
            duration_seconds=round(duration, 2),
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )
        story.metrics.append(m)
        story.total_duration_seconds = round(
            sum(e.duration_seconds for e in story.metrics), 2
        )
        story.total_prompt_tokens = sum(e.prompt_tokens for e in story.metrics)
        story.total_completion_tokens = sum(e.completion_tokens for e in story.metrics)
        story.total_tokens = sum(e.total_tokens for e in story.metrics)

    @abc.abstractmethod
    def handle_message(self, message: AgentMessage) -> None:
        ...

    def run(self) -> None:
        self.logger.info("agent_starting", queue=self.listen_queue)
        self.log_activity("agent_started", f"{self.agent_name} is online")

        while True:
            try:
                message = dequeue_message(self.redis, self.listen_queue, timeout=self.timeout)
                if message is None:
                    continue
                self.logger.info(
                    "message_received",
                    action=message.action,
                    story_id=message.story_id,
                )
                self.handle_message(message)
            except Exception:
                self.logger.error("agent_error", error=traceback.format_exc())
                self.log_activity("error", traceback.format_exc())
                time.sleep(self.loop_interval)
