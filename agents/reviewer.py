from __future__ import annotations

import time

from shared import constants
from shared.config_loader import load_prompt
from shared.elasticsearch_client import get_story, save_story
from shared.models import AgentMessage, FeedbackItem
from shared.ollama_client import generate
from shared.redis_client import enqueue_message

from agents.base_agent import BaseAgent


class ReviewerAgent(BaseAgent):
    def __init__(self):
        super().__init__("reviewer", constants.QUEUE_REVIEWER)
        self.system_prompt = load_prompt("reviewer")

    def handle_message(self, message: AgentMessage) -> None:
        if message.action != constants.ACTION_REVIEW:
            self.logger.warning("unknown_action", action=message.action)
            return

        story_id = message.story_id
        round_number = message.payload.get("round_number", 1)
        self.log_activity("reviewing", f"Review round {round_number}", story_id)

        story = get_story(self.es, story_id)
        if not story:
            self.logger.error("story_not_found", story_id=story_id)
            return

        user_prompt = (
            f"Review this {story.prompt.genre if story.prompt else ''} short story:\n\n"
            f"{story.current_draft}\n\n"
            f"Original prompt:\n{story.prompt.setting if story.prompt else 'N/A'}\n"
        )

        t0 = time.monotonic()
        result = generate(user_prompt, self.system_prompt, model=story.model)
        elapsed = time.monotonic() - t0

        feedback_text = result.text
        approved = "APPROVED: YES" in feedback_text.upper()

        feedback_item = FeedbackItem(
            agent="reviewer",
            round_number=round_number,
            feedback=feedback_text,
            approved=approved,
        )
        story.feedback.append(feedback_item)
        self.record_metrics(story, "review", elapsed, result.usage, round_number)
        save_story(self.es, story)

        self.log_activity(
            "review_complete",
            f"Round {round_number} - {'Approved' if approved else 'Changes requested'}",
            story_id,
        )

        enqueue_message(
            self.redis,
            constants.QUEUE_ORCHESTRATOR,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_REVIEW_COMPLETE,
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
    agent = ReviewerAgent()
    agent.run()


if __name__ == "__main__":
    main()
