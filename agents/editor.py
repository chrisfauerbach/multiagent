from __future__ import annotations

import time

from shared import constants
from shared.config_loader import load_prompt
from shared.elasticsearch_client import get_story, save_story
from shared.models import AgentMessage, FeedbackItem
from shared.ollama_client import generate
from shared.redis_client import enqueue_message

from agents.base_agent import BaseAgent


class EditorAgent(BaseAgent):
    def __init__(self):
        super().__init__("editor", constants.QUEUE_EDITOR)
        self.system_prompt = load_prompt("editor")

    def handle_message(self, message: AgentMessage) -> None:
        if message.action != constants.ACTION_EDIT:
            self.logger.warning("unknown_action", action=message.action)
            return

        story_id = message.story_id
        round_number = message.payload.get("round_number", 1)
        self.log_activity("editing", f"Edit round {round_number}", story_id)

        story = get_story(self.es, story_id)
        if not story:
            self.logger.error("story_not_found", story_id=story_id)
            return

        user_prompt = (
            f"Edit this {story.prompt.genre if story.prompt else ''} short story for line-level quality:\n\n"
            f"{story.current_draft}\n"
        )

        t0 = time.monotonic()
        result = generate(user_prompt, self.system_prompt)
        elapsed = time.monotonic() - t0

        feedback_text = result.text
        approved = "APPROVED: YES" in feedback_text.upper()

        feedback_item = FeedbackItem(
            agent="editor",
            round_number=round_number,
            feedback=feedback_text,
            approved=approved,
        )
        story.feedback.append(feedback_item)
        self.record_metrics(story, "edit", elapsed, result.usage, round_number)
        save_story(self.es, story)

        self.log_activity(
            "edit_complete",
            f"Round {round_number} - {'Approved' if approved else 'Changes requested'}",
            story_id,
        )

        enqueue_message(
            self.redis,
            constants.QUEUE_ORCHESTRATOR,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_EDIT_COMPLETE,
                payload={
                    "round_number": round_number,
                    "approved": approved,
                    "feedback": feedback_text,
                },
                source=self.agent_name,
                target="orchestrator",
            ),
        )


def main():
    agent = EditorAgent()
    agent.run()


if __name__ == "__main__":
    main()
