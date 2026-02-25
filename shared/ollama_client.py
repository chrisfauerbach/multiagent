from __future__ import annotations

import re

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from shared.config_loader import load_pipeline_config
from shared.models import GenerateResult, OllamaUsage

logger = structlog.get_logger()


def _get_ollama_config() -> dict:
    return load_pipeline_config()["ollama"]


def _strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks from deepseek-r1 output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(5),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    before_sleep=lambda retry_state: logger.warning(
        "ollama_retry", attempt=retry_state.attempt_number
    ),
)
def generate(prompt: str, system_prompt: str = "") -> GenerateResult:
    config = _get_ollama_config()
    url = f"{config['base_url']}/api/generate"

    payload = {
        "model": config["model"],
        "prompt": prompt,
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

    with httpx.Client(timeout=config["timeout"]) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        raw_text = result.get("response", "")
        usage = OllamaUsage(
            prompt_tokens=result.get("prompt_eval_count", 0),
            completion_tokens=result.get("eval_count", 0),
            total_tokens=result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
        )
        return GenerateResult(text=_strip_thinking_tags(raw_text), usage=usage)
