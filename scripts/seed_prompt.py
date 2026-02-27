"""Manually trigger a new story by sending start_new_story to the orchestrator.

Usage:
    python -m scripts.seed_prompt
    python -m scripts.seed_prompt "A detective who can taste lies"
    python -m scripts.seed_prompt --genre horror "a dark forest"
"""
import argparse
import uuid

from shared.config_loader import load_pipeline_config
from shared.constants import QUEUE_ORCHESTRATOR
from shared.models import AgentMessage
from shared.redis_client import enqueue_message, get_redis_client


def main():
    parser = argparse.ArgumentParser(description="Trigger a new story")
    parser.add_argument("user_prompt", nargs="?", default="", help="Optional story idea")
    parser.add_argument("--genre", default="", help="Optional genre (e.g. horror, fantasy)")
    args = parser.parse_args()

    client = get_redis_client()
    config = load_pipeline_config()
    story_id = uuid.uuid4().hex[:12]
    user_prompt = args.user_prompt.strip()
    genre = args.genre.strip()
    payload = {"model": config["ollama"]["model"]}
    if user_prompt:
        payload["user_prompt"] = user_prompt
    if genre:
        payload["genre"] = genre
    msg = AgentMessage(
        story_id=story_id,
        action="start_new_story",
        payload=payload,
        source="seed_script",
        target="orchestrator",
    )
    enqueue_message(client, QUEUE_ORCHESTRATOR, msg)
    parts = [f"Seeded story {story_id}"]
    if genre:
        parts.append(f"genre={genre}")
    if user_prompt:
        parts.append(f"prompt: {user_prompt}")
    else:
        parts.append("(random prompt)")
    print(" | ".join(parts))


if __name__ == "__main__":
    main()
