"""Manually trigger a new story by sending start_new_story to the orchestrator.

Usage:
    python -m scripts.seed_prompt
    python -m scripts.seed_prompt "A detective who can taste lies"
"""
import sys
import uuid

from shared.constants import QUEUE_ORCHESTRATOR
from shared.models import AgentMessage
from shared.redis_client import enqueue_message, get_redis_client


def main():
    client = get_redis_client()
    story_id = uuid.uuid4().hex[:12]
    user_prompt = " ".join(sys.argv[1:]).strip()
    payload = {}
    if user_prompt:
        payload["user_prompt"] = user_prompt
    msg = AgentMessage(
        story_id=story_id,
        action="start_new_story",
        payload=payload,
        source="seed_script",
        target="orchestrator",
    )
    enqueue_message(client, QUEUE_ORCHESTRATOR, msg)
    if user_prompt:
        print(f"Seeded story {story_id} with prompt: {user_prompt}")
    else:
        print(f"Seeded story {story_id} (random prompt)")


if __name__ == "__main__":
    main()
