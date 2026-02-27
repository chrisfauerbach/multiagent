from __future__ import annotations

import re
import time

from shared import constants
from shared.svg_utils import sanitize_svg
from shared.config_loader import load_prompt
from shared.elasticsearch_client import get_story, save_story
from shared.models import AgentMessage, StoryStatus
from shared.ollama_client import generate
from shared.redis_client import enqueue_message

from agents.base_agent import BaseAgent


class CoverDesignerAgent(BaseAgent):
    def __init__(self):
        super().__init__("cover_designer", constants.QUEUE_COVER_DESIGNER)
        self.system_prompt = load_prompt("cover_designer")

    def handle_message(self, message: AgentMessage) -> None:
        if message.action == constants.ACTION_DESIGN_COVER:
            self._design_cover(message)
        else:
            self.logger.warning("unknown_action", action=message.action)

    def _design_cover(self, message: AgentMessage) -> None:
        story_id = message.story_id
        self.log_activity("designing_cover", f"Designing cover for {story_id}", story_id)

        story = get_story(self.es, story_id)
        if not story:
            self.logger.error("story_not_found", story_id=story_id)
            return

        title = story.title or "Untitled"
        genre = story.prompt.genre if story.prompt else "fiction"
        theme = story.prompt.theme if story.prompt else ""
        # Use first ~200 words of draft as synopsis
        draft_words = story.current_draft.split()
        synopsis = " ".join(draft_words[:200]) + ("..." if len(draft_words) > 200 else "")

        user_prompt = (
            f"Design an SVG book cover for:\n\n"
            f"Title: {title}\n"
            f"Genre: {genre}\n"
            f"Theme: {theme}\n"
            f"Synopsis: {synopsis}\n"
        )

        t0 = time.monotonic()
        result = generate(user_prompt, self.system_prompt, model=story.model)
        elapsed = time.monotonic() - t0

        svg = self._extract_svg(result.text)
        story.cover_svg = svg
        story.status = StoryStatus.DESIGNING_COVER
        self.record_metrics(story, "design_cover", elapsed, result.usage)
        save_story(self.es, story)

        self.log_activity(
            "cover_designed",
            f"Cover ready ({len(svg)} chars, {elapsed:.1f}s)",
            story_id,
        )

        enqueue_message(
            self.redis,
            constants.QUEUE_ORCHESTRATOR,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_COVER_READY,
                source=self.agent_name,
                target="orchestrator",
            ),
        )

    _FALLBACK_SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 900">'
        '<rect width="600" height="900" fill="#1a1a2e"/>'
        '<text x="300" y="400" text-anchor="middle" font-family="serif" '
        'font-size="36" fill="#e0e0e0">Cover Unavailable</text>'
        '<text x="300" y="850" text-anchor="middle" font-family="sans-serif" '
        'font-size="16" fill="#888">AI Publishing House</text>'
        '</svg>'
    )

    def _extract_svg(self, text: str) -> str:
        """Extract the SVG element from LLM output and sanitize it."""
        match = re.search(r"(<svg[\s\S]*?</svg>)", text)
        if not match:
            return self._FALLBACK_SVG
        svg = match.group(1)
        svg = sanitize_svg(svg)
        return svg


def main():
    agent = CoverDesignerAgent()
    agent.run()


if __name__ == "__main__":
    main()
