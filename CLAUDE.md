# CLAUDE.md - Project Guide for AI Agents

## Project Overview

Multi-agent AI publishing house. Five Python agents in Docker containers communicate via Redis queues (BRPOP/LPUSH), use Ollama for LLM inference, store data in Elasticsearch, and are monitored via a FastAPI dashboard.

## Build & Run

```bash
docker compose up --build -d          # start everything
docker compose down                    # stop everything
docker compose logs -f orchestrator    # follow specific agent
docker compose exec ollama ollama pull deepseek-r1:8b  # pull model (first time)
```

Dashboard: http://localhost:8000

## Key Architecture Decisions

- **Centralized orchestrator**: All agents report back to editor-in-chief only. Agents never talk directly to each other.
- **Redis Lists (BRPOP/LPUSH)**: Simple job queues. Each agent is sole consumer of its queue.
- **Shared Dockerfile**: `Dockerfile.agent` is used by all 5 agents + init-services. `AGENT_MODULE` env var selects the entrypoint (e.g. `agents.writer`).
- **Pydantic everywhere**: `AgentMessage` is the universal envelope. All data validated at boundaries.
- **Sequential review**: Reviewer runs first, then editor. Orchestrator collects both before deciding.
- **`GenerateResult`**: `ollama_client.generate()` returns `GenerateResult` (not a raw string). Always access `.text` for the content and `.usage` for token stats.

## Code Layout

| Directory | Purpose |
|---|---|
| `shared/` | Shared library: models, clients (redis, ES, ollama), config, constants |
| `agents/` | Agent implementations. All inherit from `BaseAgent` |
| `config/` | YAML configs (`genres.yml`, `pipeline.yml`) and system prompts (`prompts/`) |
| `dashboard/` | FastAPI app with Jinja2 templates |
| `scripts/` | One-shot utilities (ES init, seed prompt) |

## Important Files

- `shared/models.py` — All Pydantic models: `Story`, `AgentMessage`, `AgentMetrics`, `GenerateResult`, etc.
- `shared/constants.py` — Queue names (`QUEUE_ORCHESTRATOR`, etc.) and action constants (`ACTION_WRITE_DRAFT`, etc.)
- `shared/ollama_client.py` — `generate()` function returns `GenerateResult` with `.text` and `.usage`
- `agents/base_agent.py` — `BaseAgent` abstract class with main loop, `record_metrics()`, `log_activity()`
- `agents/editor_in_chief.py` — Orchestrator state machine. Most complex agent.
- `config/pipeline.yml` — Runtime config (max revisions, ollama model, redis/ES hosts)

## Message Flow

All inter-agent communication goes through Redis queues as JSON `AgentMessage` envelopes:
- `queue:orchestrator` — consumed by editor-in-chief
- `queue:prompt_generator` — consumed by prompt generator
- `queue:writer` — consumed by writer
- `queue:reviewer` — consumed by reviewer
- `queue:editor` — consumed by editor

## Conventions

- **Config paths**: Inside containers, config lives at `/app/config/` (set via `CONFIG_DIR` env var). Locally it's `./config/`.
- **Elasticsearch indices**: `stories` and `activity_logs`. Mappings defined in `scripts/init_elasticsearch.py`. If you change `shared/models.py` fields that are stored in ES, update the mappings too and recreate the index.
- **Agent pattern**: Inherit `BaseAgent`, implement `handle_message()`. Call `self.record_metrics()` after every `generate()` call. Call `self.log_activity()` for dashboard visibility.
- **Ollama generate()**: Always returns `GenerateResult`. Use `result.text` for content, `result.usage` for `OllamaUsage` (prompt_tokens, completion_tokens, total_tokens). Deepseek-r1 `<think>` tags are stripped automatically.
- **Metrics**: Every `generate()` call should be wrapped with `time.monotonic()` and the result passed to `self.record_metrics(story, action, elapsed, result.usage, round_number)`.
- **No direct agent-to-agent communication**: Always route through the orchestrator queue.
- **System prompts**: Stored as plain text in `config/prompts/{agent_name}.txt`. Loaded via `load_prompt("agent_name")`.

## Testing Locally

```bash
# Trigger a story from CLI
docker compose exec orchestrator python -m scripts.seed_prompt "a haunted lighthouse"

# Check agent logs
docker compose logs -f writer

# Query ES directly
curl http://localhost:9200/stories/_search?pretty

# Check Redis queues
docker compose exec redis redis-cli LLEN queue:orchestrator
```

## Common Changes

**Add a new genre**: Edit `config/genres.yml`, add entry with `name`, `description`, `themes[]`, `word_count_min/max`.

**Change the LLM model**: Edit `config/pipeline.yml` under `ollama.model`, then pull the new model in the ollama container.

**Change max revision rounds**: Edit `config/pipeline.yml` under `pipeline.max_revisions`.

**Add a field to Story**: Update `shared/models.py`, update ES mapping in `scripts/init_elasticsearch.py`, delete and recreate the ES index.

**Add a new agent**: Create `agents/new_agent.py` inheriting `BaseAgent`, add a queue constant in `shared/constants.py`, add a service in `docker-compose.yml` with `AGENT_MODULE=agents.new_agent`, wire it into the orchestrator's dispatch.
