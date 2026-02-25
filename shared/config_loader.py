import os
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/app/config"))


def load_yaml(filename: str) -> dict:
    path = CONFIG_DIR / filename
    with open(path) as f:
        return yaml.safe_load(f)


def load_genres() -> dict:
    return load_yaml("genres.yml")


def load_pipeline_config() -> dict:
    return load_yaml("pipeline.yml")


def load_prompt(agent_name: str) -> str:
    path = CONFIG_DIR / "prompts" / f"{agent_name}.txt"
    return path.read_text().strip()
