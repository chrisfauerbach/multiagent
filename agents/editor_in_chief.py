from __future__ import annotations

import time
import uuid

from shared import constants
from shared.config_loader import load_prompt
from shared.elasticsearch_client import get_story, save_story
from shared.models import AgentMessage, StoryStatus
from shared.ollama_client import generate
from shared.redis_client import enqueue_message

from agents.base_agent import BaseAgent


class EditorInChiefAgent(BaseAgent):
    def __init__(self):
        super().__init__("orchestrator", constants.QUEUE_ORCHESTRATOR)
        self.system_prompt = load_prompt("editor_in_chief")
        # Track pending reviews per story: {story_id: {"reviewer": ..., "editor": ...}}
        self._pending_feedback: dict[str, dict] = {}

    def handle_message(self, message: AgentMessage) -> None:
        handlers = {
            constants.ACTION_START_NEW_STORY: self._handle_start_new_story,
            constants.ACTION_PROMPT_READY: self._handle_prompt_ready,
            constants.ACTION_DRAFT_READY: self._handle_draft_ready,
            constants.ACTION_REVIEW_COMPLETE: self._handle_review_complete,
            constants.ACTION_EDIT_COMPLETE: self._handle_edit_complete,
            constants.ACTION_REVISION_READY: self._handle_revision_ready,
            constants.ACTION_COVER_READY: self._handle_cover_ready,
        }
        handler = handlers.get(message.action)
        if handler is None:
            self.logger.warning("unknown_action", action=message.action)
            return
        handler(message)

    # --- Handlers ---

    def _handle_start_new_story(self, message: AgentMessage) -> None:
        story_id = message.story_id or uuid.uuid4().hex[:12]
        user_prompt = message.payload.get("user_prompt", "")
        model = message.payload.get("model", "")
        self.log_activity("starting_story", f"Initiating new story {story_id}" + (f" (model={model})" if model else ""), story_id)

        payload = {}
        if user_prompt:
            payload["user_prompt"] = user_prompt
        if model:
            payload["model"] = model

        enqueue_message(
            self.redis,
            constants.QUEUE_PROMPT_GENERATOR,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_GENERATE_PROMPT,
                payload=payload,
                source=self.agent_name,
                target="prompt_generator",
            ),
        )

    def _handle_prompt_ready(self, message: AgentMessage) -> None:
        story_id = message.story_id
        self.log_activity("prompt_received", f"Sending to writer", story_id)

        enqueue_message(
            self.redis,
            constants.QUEUE_WRITER,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_WRITE_DRAFT,
                source=self.agent_name,
                target="writer",
            ),
        )

    def _handle_draft_ready(self, message: AgentMessage) -> None:
        story_id = message.story_id
        story = get_story(self.es, story_id)
        if not story:
            self.logger.error("story_not_found", story_id=story_id)
            return

        story.status = StoryStatus.IN_REVIEW
        save_story(self.es, story)

        round_number = story.revision_count + 1
        self._send_for_review(story_id, round_number)

    def _handle_revision_ready(self, message: AgentMessage) -> None:
        story_id = message.story_id
        story = get_story(self.es, story_id)
        if not story:
            self.logger.error("story_not_found", story_id=story_id)
            return

        story.status = StoryStatus.IN_REVIEW
        save_story(self.es, story)

        round_number = message.payload.get("round_number", story.revision_count) + 1
        self._send_for_review(story_id, round_number)

    def _handle_review_complete(self, message: AgentMessage) -> None:
        story_id = message.story_id
        review_mode = self.config["pipeline"].get("review_mode", "sequential")

        if review_mode == "parallel":
            self._handle_parallel_feedback(message, "reviewer")
        else:
            # Sequential: after reviewer, send to editor
            self.log_activity("review_received", "Sending to editor", story_id)
            round_number = message.payload.get("round_number", 1)
            enqueue_message(
                self.redis,
                constants.QUEUE_EDITOR,
                AgentMessage(
                    story_id=story_id,
                    action=constants.ACTION_EDIT,
                    payload={"round_number": round_number},
                    source=self.agent_name,
                    target="editor",
                ),
            )

    def _handle_edit_complete(self, message: AgentMessage) -> None:
        story_id = message.story_id
        review_mode = self.config["pipeline"].get("review_mode", "sequential")

        if review_mode == "parallel":
            self._handle_parallel_feedback(message, "editor")
        else:
            # Sequential: both review and edit are done, evaluate
            story = get_story(self.es, story_id)
            if not story:
                return

            round_number = message.payload.get("round_number", 1)
            # Collect feedback from this round
            round_feedback = [f for f in story.feedback if f.round_number == round_number]
            reviewer_fb = next((f for f in round_feedback if f.agent == "reviewer"), None)
            editor_fb = next((f for f in round_feedback if f.agent == "editor"), None)

            self._evaluate_and_decide(
                story,
                reviewer_approved=reviewer_fb.approved if reviewer_fb else False,
                editor_approved=editor_fb.approved if editor_fb else False,
                reviewer_feedback=reviewer_fb.feedback if reviewer_fb else "",
                editor_feedback=editor_fb.feedback if editor_fb else "",
                round_number=round_number,
            )

    # --- Helper methods ---

    def _send_for_review(self, story_id: str, round_number: int) -> None:
        review_mode = self.config["pipeline"].get("review_mode", "sequential")
        self.log_activity("sending_for_review", f"Round {round_number} ({review_mode})", story_id)

        if review_mode == "parallel":
            self._pending_feedback[story_id] = {}
            enqueue_message(
                self.redis,
                constants.QUEUE_REVIEWER,
                AgentMessage(
                    story_id=story_id,
                    action=constants.ACTION_REVIEW,
                    payload={"round_number": round_number},
                    source=self.agent_name,
                    target="reviewer",
                ),
            )
            enqueue_message(
                self.redis,
                constants.QUEUE_EDITOR,
                AgentMessage(
                    story_id=story_id,
                    action=constants.ACTION_EDIT,
                    payload={"round_number": round_number},
                    source=self.agent_name,
                    target="editor",
                ),
            )
        else:
            # Sequential: reviewer first
            enqueue_message(
                self.redis,
                constants.QUEUE_REVIEWER,
                AgentMessage(
                    story_id=story_id,
                    action=constants.ACTION_REVIEW,
                    payload={"round_number": round_number},
                    source=self.agent_name,
                    target="reviewer",
                ),
            )

    def _handle_parallel_feedback(self, message: AgentMessage, agent_type: str) -> None:
        story_id = message.story_id
        if story_id not in self._pending_feedback:
            self._pending_feedback[story_id] = {}

        self._pending_feedback[story_id][agent_type] = message.payload

        # Check if both are in
        fb = self._pending_feedback[story_id]
        if "reviewer" not in fb or "editor" not in fb:
            self.log_activity("waiting_for_feedback", f"Got {agent_type}, waiting for other", story_id)
            return

        # Both done
        story = get_story(self.es, story_id)
        if not story:
            return

        round_number = message.payload.get("round_number", 1)
        self._evaluate_and_decide(
            story,
            reviewer_approved=fb["reviewer"].get("approved", False),
            editor_approved=fb["editor"].get("approved", False),
            reviewer_feedback=fb["reviewer"].get("feedback", ""),
            editor_feedback=fb["editor"].get("feedback", ""),
            round_number=round_number,
        )
        del self._pending_feedback[story_id]

    def _evaluate_and_decide(
        self,
        story,
        reviewer_approved: bool,
        editor_approved: bool,
        reviewer_feedback: str,
        editor_feedback: str,
        round_number: int,
    ) -> None:
        story_id = story.story_id

        # Both approve -> send for cover design
        if reviewer_approved and editor_approved:
            self.log_activity("story_approved", "Both reviewer and editor approved", story_id)
            story.status = StoryStatus.APPROVED
            save_story(self.es, story)
            self._send_for_cover_design(story)
            return

        # Max revisions reached -> send for cover design anyway
        if round_number >= story.max_revisions:
            self.log_activity(
                "max_revisions_reached",
                f"Approved after {round_number} rounds, sending for cover design",
                story_id,
            )
            story.status = StoryStatus.APPROVED
            save_story(self.es, story)
            self._send_for_cover_design(story)
            return

        # Use LLM to summarize feedback for the writer
        eval_prompt = (
            f"Reviewer feedback:\n{reviewer_feedback}\n\n"
            f"Editor feedback:\n{editor_feedback}\n\n"
            f"Reviewer approved: {reviewer_approved}\n"
            f"Editor approved: {editor_approved}\n\n"
            f"Summarize the top priority fixes for the writer. Be concise."
        )
        t0 = time.monotonic()
        result = generate(eval_prompt, self.system_prompt, model=story.model)
        elapsed = time.monotonic() - t0
        self.record_metrics(story, "evaluate_feedback", elapsed, result.usage, round_number)

        self.log_activity("revision_needed", f"Round {round_number} - requesting revision", story_id)

        story.status = StoryStatus.REVISION_NEEDED
        save_story(self.es, story)

        enqueue_message(
            self.redis,
            constants.QUEUE_WRITER,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_REVISE,
                payload={
                    "round_number": round_number,
                    "feedback_summary": result.text,
                },
                source=self.agent_name,
                target="writer",
            ),
        )

    def _send_for_cover_design(self, story) -> None:
        story_id = story.story_id
        self.log_activity("sending_for_cover", "Sending to cover designer", story_id)

        story.status = StoryStatus.DESIGNING_COVER
        save_story(self.es, story)

        enqueue_message(
            self.redis,
            constants.QUEUE_COVER_DESIGNER,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_DESIGN_COVER,
                source=self.agent_name,
                target="cover_designer",
            ),
        )

    def _handle_cover_ready(self, message: AgentMessage) -> None:
        story_id = message.story_id
        story = get_story(self.es, story_id)
        if not story:
            self.logger.error("story_not_found", story_id=story_id)
            return
        self.log_activity("cover_received", "Cover design received, publishing", story_id)
        self._publish_story(story)

    def _publish_story(self, story) -> None:
        story.status = StoryStatus.PUBLISHED
        save_story(self.es, story)
        self.log_activity(
            "story_published",
            f"'{story.title}' published after {story.revision_count} revision(s)",
            story.story_id,
        )


def main():
    agent = EditorInChiefAgent()
    agent.run()


if __name__ == "__main__":
    main()
