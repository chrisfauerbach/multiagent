"""Create Elasticsearch indices on startup."""
import sys
import time

from elasticsearch import Elasticsearch

from shared.config_loader import load_pipeline_config
from shared.constants import ACTIVITY_LOGS_INDEX, ANTHOLOGIES_INDEX, STORIES_INDEX

STORIES_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "story_id": {"type": "keyword"},
            "title": {"type": "text"},
            "model": {"type": "keyword"},
            "status": {"type": "keyword"},
            "prompt": {
                "type": "object",
                "properties": {
                    "genre": {"type": "keyword"},
                    "theme": {"type": "text"},
                    "setting": {"type": "text"},
                    "characters": {"type": "text"},
                    "target_word_count": {"type": "integer"},
                    "additional_instructions": {"type": "text"},
                },
            },
            "current_draft": {"type": "text"},
            "revisions": {
                "type": "nested",
                "properties": {
                    "round_number": {"type": "integer"},
                    "content": {"type": "text"},
                    "feedback_addressed": {"type": "text"},
                    "timestamp": {"type": "date"},
                },
            },
            "feedback": {
                "type": "nested",
                "properties": {
                    "agent": {"type": "keyword"},
                    "round_number": {"type": "integer"},
                    "feedback": {"type": "text"},
                    "approved": {"type": "boolean"},
                    "timestamp": {"type": "date"},
                },
            },
            "cover_svg": {"type": "text", "index": False},
            "revision_count": {"type": "integer"},
            "max_revisions": {"type": "integer"},
            "metrics": {
                "type": "nested",
                "properties": {
                    "agent": {"type": "keyword"},
                    "action": {"type": "keyword"},
                    "round_number": {"type": "integer"},
                    "duration_seconds": {"type": "float"},
                    "prompt_tokens": {"type": "integer"},
                    "completion_tokens": {"type": "integer"},
                    "total_tokens": {"type": "integer"},
                    "timestamp": {"type": "date"},
                },
            },
            "total_duration_seconds": {"type": "float"},
            "total_prompt_tokens": {"type": "integer"},
            "total_completion_tokens": {"type": "integer"},
            "total_tokens": {"type": "integer"},
            "trigger_payload": {"type": "object", "enabled": False},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
        }
    },
}

ACTIVITY_LOGS_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "agent_name": {"type": "keyword"},
            "story_id": {"type": "keyword"},
            "action": {"type": "keyword"},
            "detail": {"type": "text"},
            "timestamp": {"type": "date"},
        }
    },
}


ANTHOLOGIES_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "anthology_id": {"type": "keyword"},
            "title": {"type": "text"},
            "description": {"type": "text"},
            "story_ids": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
        }
    },
}


def wait_for_elasticsearch(es: Elasticsearch, retries: int = 30, delay: int = 2) -> None:
    for i in range(retries):
        try:
            if es.ping():
                print("Elasticsearch is ready.")
                return
        except Exception:
            pass
        print(f"Waiting for Elasticsearch... ({i + 1}/{retries})")
        time.sleep(delay)
    print("ERROR: Elasticsearch not available.")
    sys.exit(1)


def create_index(es: Elasticsearch, name: str, body: dict) -> None:
    if es.indices.exists(index=name):
        print(f"Index '{name}' already exists, skipping.")
    else:
        es.indices.create(index=name, body=body)
        print(f"Index '{name}' created.")


def main():
    config = load_pipeline_config()
    es = Elasticsearch(config["elasticsearch"]["hosts"])
    wait_for_elasticsearch(es)
    create_index(es, STORIES_INDEX, STORIES_MAPPING)
    create_index(es, ACTIVITY_LOGS_INDEX, ACTIVITY_LOGS_MAPPING)
    create_index(es, ANTHOLOGIES_INDEX, ANTHOLOGIES_MAPPING)
    print("Elasticsearch initialization complete.")


if __name__ == "__main__":
    main()
