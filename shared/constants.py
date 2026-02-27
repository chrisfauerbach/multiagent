# Redis queue names
QUEUE_ORCHESTRATOR = "queue:orchestrator"
QUEUE_PROMPT_GENERATOR = "queue:prompt_generator"
QUEUE_WRITER = "queue:writer"
QUEUE_REVIEWER = "queue:reviewer"
QUEUE_EDITOR = "queue:editor"
QUEUE_COVER_DESIGNER = "queue:cover_designer"

# Redis activity
ACTIVITY_LOG_KEY = "activity:log"
ACTIVITY_CHANNEL = "agent:activity"

# Elasticsearch index names
STORIES_INDEX = "stories"
ACTIVITY_LOGS_INDEX = "activity_logs"

# Story statuses
STATUS_QUEUED = "QUEUED"
STATUS_PROMPT_CREATED = "PROMPT_CREATED"
STATUS_DRAFT_WRITTEN = "DRAFT_WRITTEN"
STATUS_IN_REVIEW = "IN_REVIEW"
STATUS_REVISION_NEEDED = "REVISION_NEEDED"
STATUS_REVISED = "REVISED"
STATUS_APPROVED = "APPROVED"
STATUS_DESIGNING_COVER = "DESIGNING_COVER"
STATUS_PUBLISHED = "PUBLISHED"

# Agent message actions
ACTION_START_NEW_STORY = "start_new_story"
ACTION_GENERATE_PROMPT = "generate_prompt"
ACTION_PROMPT_READY = "prompt_ready"
ACTION_WRITE_DRAFT = "write_draft"
ACTION_DRAFT_READY = "draft_ready"
ACTION_REVIEW = "review"
ACTION_REVIEW_COMPLETE = "review_complete"
ACTION_EDIT = "edit"
ACTION_EDIT_COMPLETE = "edit_complete"
ACTION_REVISE = "revise"
ACTION_REVISION_READY = "revision_ready"
ACTION_DESIGN_COVER = "design_cover"
ACTION_COVER_READY = "cover_ready"
