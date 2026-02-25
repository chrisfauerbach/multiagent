from __future__ import annotations

import random
import time

from shared import constants
from shared.config_loader import load_genres, load_prompt
from shared.elasticsearch_client import save_story
from shared.models import AgentMessage, Story, StoryStatus, WritingPrompt
from shared.ollama_client import generate
from shared.redis_client import enqueue_message

from agents.base_agent import BaseAgent


class PromptGeneratorAgent(BaseAgent):
    def __init__(self):
        super().__init__("prompt_generator", constants.QUEUE_PROMPT_GENERATOR)
        self.system_prompt = load_prompt("prompt_generator")
        self.genres_config = load_genres()

    def handle_message(self, message: AgentMessage) -> None:
        if message.action != constants.ACTION_GENERATE_PROMPT:
            self.logger.warning("unknown_action", action=message.action)
            return

        story_id = message.story_id
        user_idea = message.payload.get("user_prompt", "")
        self.log_activity("generating_prompt", f"Creating prompt for story {story_id}", story_id)

        genre = random.choice(self.genres_config["genres"])
        theme = random.choice(genre["themes"])
        target_word_count = random.randint(genre["word_count_min"], genre["word_count_max"])

        if user_idea:
            user_prompt = (
                f"A user has requested a story with this idea:\n\n"
                f'"{user_idea}"\n\n'
                f"Target word count: {target_word_count}\n\n"
                f"Build a detailed writing prompt around the user's idea. "
                f"Pick the most fitting genre and tone from the idea."
            )
        else:
            user_prompt = (
                f"Genre: {genre['name']}\n"
                f"Genre description: {genre['description']}\n"
                f"Theme: {theme}\n"
                f"Target word count: {target_word_count}\n\n"
                f"Generate a detailed writing prompt for a short story."
            )

        t0 = time.monotonic()
        result = generate(user_prompt, self.system_prompt)
        elapsed = time.monotonic() - t0

        writing_prompt = WritingPrompt(
            genre=genre["name"],
            theme=theme,
            setting=result.text,
            characters="",
            target_word_count=target_word_count,
            additional_instructions="",
        )

        story = Story(
            story_id=story_id,
            status=StoryStatus.PROMPT_CREATED,
            prompt=writing_prompt,
            max_revisions=self.config["pipeline"]["max_revisions"],
        )
        self.record_metrics(story, "generate_prompt", elapsed, result.usage)
        save_story(self.es, story)

        self.log_activity("prompt_generated", f"Prompt created for genre={genre['name']}", story_id)

        enqueue_message(
            self.redis,
            constants.QUEUE_ORCHESTRATOR,
            AgentMessage(
                story_id=story_id,
                action=constants.ACTION_PROMPT_READY,
                payload={"genre": genre["name"], "theme": theme},
                source=self.agent_name,
                target="orchestrator",
            ),
        )


def main():
    agent = PromptGeneratorAgent()
    agent.run()


if __name__ == "__main__":
    main()
