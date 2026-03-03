# Integrate Deep Research Agent Into Root Framework

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

The ExecPlan requirements live in `.agent/PLANS.md` at the repository root and this plan must be maintained in accordance with that file.

## Purpose / Big Picture

Integrate the new `deep_research` agent into the existing root-level agent framework so there is a single source of truth for graph registration and dependency management. After this change, users can run LangGraph from the repository root and directly select the deep research graph without maintaining a separate `pyproject.toml`, `uv.lock`, or `langgraph.json` inside the subfolder.

## Progress

- [x] (2026-02-28 10:00Z) Compared root and subfolder configuration files (`pyproject.toml`, `langgraph.json`, `uv.lock`) and identified merge targets.
- [x] (2026-02-28 10:05Z) Merged deep research graph registration into root `langgraph.json`.
- [x] (2026-02-28 10:08Z) Merged deep research dependencies and override constraints into root `pyproject.toml` and refreshed `requirements-langgraph.txt`.
- [x] (2026-02-28 10:11Z) Removed redundant subfolder config files (`app/core/agent/deep_research/pyproject.toml`, `app/core/agent/deep_research/langgraph.json`, `app/core/agent/deep_research/uv.lock`).
- [x] (2026-02-28 10:13Z) Regenerated root `uv.lock` with merged dependencies.
- [x] (2026-02-28 10:16Z) Updated deep research runtime imports and docs to support root-level execution.
- [x] (2026-02-28 10:19Z) Validated JSON/TOML syntax and deep research graph load path.

## Surprises & Discoveries

- Observation: Importing `app.core...` triggers `app/core/__init__.py` side effects and can fail due unrelated environment validation (`DEBUG=release` in existing `.env`).
  Evidence: `uv run python -c "import importlib; importlib.import_module('app.core.agent.deep_research.agent')"` failed with `pydantic_core.ValidationError` from `PostgresConfig`.

- Observation: `tavily.TavilyClient()` at module import time can hard-fail when `TAVILY_API_KEY` is not set.
  Evidence: Existing tool module instantiated client globally before any tool call.

## Decision Log

- Decision: Keep deep research module load path independent from `app.core` package initialization by using local sibling-path imports in `app/core/agent/deep_research/agent.py`.
  Rationale: Root package init side effects are unrelated to LangGraph graph loading and can block startup.
  Date/Author: 2026-02-28 / Codex

- Decision: Move security override constraints (`nbconvert`, `protobuf`) into root `[tool.uv]`.
  Rationale: Subfolder lock/override settings are no longer authoritative after consolidation.
  Date/Author: 2026-02-28 / Codex

- Decision: Lazily initialize Tavily client inside tool execution instead of import time.
  Rationale: Prevent startup failures when credentials are missing; fail only when tool is actually invoked.
  Date/Author: 2026-02-28 / Codex

## Outcomes & Retrospective

Deep research is now wired into the root framework through root `langgraph.json` and root dependency management. Redundant subfolder config files were removed, and the root lockfile now contains the merged dependency set. Residual runtime requirements remain environment-based credentials (`OPENAI_API_KEY`/`LLM_API_KEY`, `TAVILY_API_KEY`) which must be present for end-to-end execution.

## Context and Orientation

Before this change, `app/core/agent/deep_research` was a mostly standalone unit with its own `pyproject.toml`, `uv.lock`, and `langgraph.json`. The root project already had equivalent files. This split caused version drift and unclear startup behavior.

The root graph registry lives in `langgraph.json`. Python dependencies and lock state are managed by `pyproject.toml` and `uv.lock` at repository root. The deep research runtime entry is `app/core/agent/deep_research/agent.py`, and its custom tools/prompts are under `app/core/agent/deep_research/research_agent/`.

## Plan of Work

First, merge graph registration so root LangGraph knows about `deep_research_agent`. Next, merge runtime dependencies and vulnerability overrides from subfolder config into root dependency files. Then remove subfolder duplicate config files to avoid split-brain config ownership. Finally, make deep research imports resilient for path-based graph loading and validate all updated root configs.

## Concrete Steps

From repository root:

    cd /Users/apple/PycharmProjects/Cascade-RAG
    uv lock
    python -m json.tool langgraph.json
    python -c "import tomllib, pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text())"
    OPENAI_API_KEY=dummy uv run python -c "import runpy; ns=runpy.run_path('app/core/agent/deep_research/agent.py'); print('deep_research run_path ok:', 'agent' in ns)"

## Validation and Acceptance

Acceptance criteria:

1. `langgraph.json` includes `"deep_research_agent": "./app/core/agent/deep_research/agent.py:agent"`.
2. Root `pyproject.toml` includes deep research runtime dependencies and `[tool.uv].override-dependencies`.
3. Redundant config files are absent from `app/core/agent/deep_research` (`pyproject.toml`, `langgraph.json`, `uv.lock`).
4. `uv lock` completes successfully from root.
5. Path-based execution of `app/core/agent/deep_research/agent.py` succeeds when `OPENAI_API_KEY` is present.

## Idempotence and Recovery

All edits are idempotent: rerunning `uv lock` and validation commands is safe. If lock resolution fails due transient network/index issues, rerun `uv lock` after connectivity recovers. If runtime checks fail due missing credentials, set `OPENAI_API_KEY` (or `LLM_API_KEY`) and `TAVILY_API_KEY` and retry.

## Artifacts and Notes

Key outcome snippet from lock refresh:

    Added deepagents v0.4.4
    Added langchain-anthropic v1.3.4
    Updated langgraph v1.0.3 -> v1.0.10
    Updated langgraph-api v0.5.24 -> v0.7.60
    Updated nbconvert v7.16.6 -> v7.17.0
    Updated protobuf v6.33.1 -> v7.34.0

## Interfaces and Dependencies

Updated root dependency interfaces include:

- `deepagents` for `create_deep_agent` / `SubAgent`.
- `tavily-python` and `markdownify` for deep research web retrieval tooling.
- Newer `langchain*` and `langgraph*` constraints compatible with deep research stack.

The deep research graph remains exported as:

    agent = create_deep_agent(...)

from `app/core/agent/deep_research/agent.py`.

Plan Update Notes: Initial and implementation-complete version created after merging subfolder configuration into root and validating runtime load path.
