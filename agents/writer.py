from __future__ import annotations

import time

from shared import constants
from shared.config_loader import load_prompt
from shared.elasticsearch_client import get_story, save_story
from shared.models import AgentMessage, Revision, StoryStatus
from shared.ollama_client import generate
from shared.redis_client import enqueue_message

from agents.base_agent import BaseAgent


class WriterAgent(BaseAgent):
    def __init__(self):
        super().__init__("writer", constants.QUEUE_WRITER)
        self.system_prompt = load_prompt("writer")

    def handle_message(self, message: AgentMessage) -> None:
        if message.action == constants.ACTION_WRITE_DRAFT:
            self._write_draft(message)
        elif message.action == constants.ACTION_REVISE:
            self._revise(message)
        else:
            self.logger.warning("unknown_action", action=message.action)

    def _write_draft(self, message: AgentMessage) -> None:
        story_id = message.story_id
        self.log_activity("writing_draft", f"Writing initial draft for {story_id}", story_id)

        story = get_story(self.es, story_id)
        if not story or not story.prompt:
            self.logger.error("story_not_found", story_id=story_id)
            return

        prompt = story.prompt
        user_prompt = (
            f"Write a {prompt.genre} short story based on this prompt:\n\n"
            f"{prompt.setting}\n\n"
            f"Target word count: {prompt.target_word_count}\n"
        )

        t0 = time.monotonic()
        result = generate(user_prompt, self.system_prompt)
        elapsed = time.monotonic() - t0

        story.current_draft = result.text
        story.title = self._extract_title(result.text, story)
        story.status = StoryStatus.DRAFT_WRITTEN
        self.record_metrics(story, "write_draft", elapsed, result.usage)
        save_story(self.es, story)

        self.log_activity("draft_written", f"Draft complete ({len(result.text.split())} words, {elapsed:.1f}s)", story_id)

        enqueue_message(
            self.redis,
            constants.QUEUE_ORCHESTRATOR,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_DRAFT_READY,
                source=self.agent_name,
                target="orchestrator",
            ),
        )

    def _revise(self, message: AgentMessage) -> None:
        story_id = message.story_id
        feedback_summary = message.payload.get("feedback_summary", "")
        round_number = message.payload.get("round_number", 1)

        self.log_activity("revising", f"Revision round {round_number}", story_id)

        story = get_story(self.es, story_id)
        if not story:
            self.logger.error("story_not_found", story_id=story_id)
            return

        user_prompt = (
            f"Here is your current draft:\n\n"
            f"{story.current_draft}\n\n"
            f"Please revise it based on this feedback:\n\n"
            f"{feedback_summary}\n\n"
            f"This is revision round {round_number}. Focus on the priority fixes."
        )

        t0 = time.monotonic()
        result = generate(user_prompt, self.system_prompt)
        elapsed = time.monotonic() - t0

        story.revisions.append(
            Revision(
                round_number=round_number,
                content=result.text,
                feedback_addressed=feedback_summary,
            )
        )
        story.current_draft = result.text
        story.revision_count = round_number
        story.status = StoryStatus.REVISED
        self.record_metrics(story, "revise", elapsed, result.usage, round_number)
        save_story(self.es, story)

        self.log_activity("revision_complete", f"Round {round_number} done ({len(result.text.split())} words, {elapsed:.1f}s)", story_id)

        enqueue_message(
            self.redis,
            constants.QUEUE_ORCHESTRATOR,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_REVISION_READY,
                payload={"round_number": round_number},
                source=self.agent_name,
                target="orchestrator",
            ),
        )

    def _extract_title(self, draft: str, story) -> str:
        first_line = draft.strip().split("\n")[0].strip()
        # If the first line looks like a title (short, possibly with # markers)
        cleaned = first_line.lstrip("#").strip().strip('"').strip("*")
        if 2 < len(cleaned) < 80:
            return cleaned
        return f"Untitled {story.prompt.genre.replace('_', ' ').title()} Story"


def main():
    agent = WriterAgent()
    agent.run()


if __name__ == "__main__":
    main()
