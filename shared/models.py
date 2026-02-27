from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StoryStatus(str, Enum):
    QUEUED = "QUEUED"
    PROMPT_CREATED = "PROMPT_CREATED"
    DRAFT_WRITTEN = "DRAFT_WRITTEN"
    IN_REVIEW = "IN_REVIEW"
    REVISION_NEEDED = "REVISION_NEEDED"
    REVISED = "REVISED"
    APPROVED = "APPROVED"
    DESIGNING_COVER = "DESIGNING_COVER"
    PUBLISHED = "PUBLISHED"


class OllamaUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class GenerateResult(BaseModel):
    text: str
    usage: OllamaUsage = Field(default_factory=OllamaUsage)


class AgentMetrics(BaseModel):
    agent: str
    action: str
    round_number: int = 0
    duration_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WritingPrompt(BaseModel):
    genre: str
    theme: str
    setting: str
    characters: str
    target_word_count: int
    additional_instructions: str = ""


class FeedbackItem(BaseModel):
    agent: str
    round_number: int
    feedback: str
    approved: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Revision(BaseModel):
    round_number: int
    content: str
    feedback_addressed: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Story(BaseModel):
    story_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    model: str = ""
    status: StoryStatus = StoryStatus.PROMPT_CREATED
    prompt: WritingPrompt | None = None
    current_draft: str = ""
    revisions: list[Revision] = Field(default_factory=list)
    feedback: list[FeedbackItem] = Field(default_factory=list)
    revision_count: int = 0
    max_revisions: int = 3
    cover_svg: str = ""
    metrics: list[AgentMetrics] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    trigger_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    story_id: str = ""
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    target: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActivityLog(BaseModel):
    agent_name: str
    story_id: str = ""
    action: str
    detail: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Anthology(BaseModel):
    anthology_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    story_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
