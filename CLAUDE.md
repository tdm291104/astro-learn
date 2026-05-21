# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repo is currently **design-only** — no source code, build files, or dependency manifests exist yet. The only content is two design documents written in Vietnamese:

- [backend/README.md](backend/README.md) — backend architecture spec
- [frontend/README.md](frontend/README.md) — frontend architecture spec

When the user asks you to implement something, you will likely be scaffolding from scratch against these specs. Read the relevant README before generating files so the structure, naming, and tech stack match the design.

## Project: AstroLearn

A multi-agent system for astronomy data analysis + NotebookLM-style learning (Q&A, summarize, quiz, flashcards). Two top-level apps:

- `backend/` — FastAPI multi-agent service. **No agent framework** (LangGraph/CrewAI/AutoGen/LangChain agents are explicitly rejected) — base classes, registry, orchestrator, and workflow engine are hand-written. LLM access goes through **LiteLLM** as a unified gateway (Groq for dev, Claude/GPT for production — switched via env, not code). Postgres + Redis + Qdrant/ChromaDB, Celery workers, Astropy/Astroquery.
- `frontend/` — Next.js 15 (App Router) + TypeScript + Tailwind v4 + shadcn/ui + Zustand + TanStack Query + Framer Motion, pnpm.

## Backend architecture (planned)

Layered request flow — keep this ordering when adding features:

```
API Route → Service → Orchestrator → Agent → Tool / Memory
                                          ↓
                                    Repository → DB
```

Key boundaries:
- **`agents/`** subclass a hand-written `BaseAgent` (ABC with `run()` + `stream()`) and are looked up via `AgentRegistry`. Orchestrator picks the agent — routes/services don't instantiate agents directly. Agent state lives in an `AgentState` dataclass persisted to Redis, NOT in instance variables.
- **`tools/`** subclass `BaseTool` (strategy pattern). Agents call tools; tools wrap external APIs (Simbad, NASA, FITS, vector search, web search).
- **`workflows/`** compose multiple agents into pipelines via a hand-written `workflow_engine.py` (sequential / parallel / conditional). E.g. `notebook_workflow.py`: upload → index → Q&A.
- **`services/`** hold business logic — they must NOT touch the DB directly. DB access goes through **`repositories/`**.
- **`memory/short_term/`** uses Redis for conversation memory; **`memory/long_term/`** wraps the vector store and knowledge base.
- **`workers/`** (Celery) is for heavy async work — document indexing, FITS ingest. Don't do this synchronously in routes.
- **`core/llm/`** is the ONLY place that touches LiteLLM. `LLMClient` exposes `complete()` / `stream()` / `embed()`. Agents/services call `LLMClient`, never `litellm.completion()` directly, and NEVER import `groq`, `anthropic`, or `openai` SDKs.

LLM provider switching:
- Dev default is `LLM_MODEL=groq/llama-3.3-70b-versatile` (cheap, fast).
- Prod swaps to `anthropic/claude-sonnet-4-6` or `openai/gpt-4o` via env only.
- LiteLLM proxy mode is optional (`litellm --config configs/litellm.yaml --port 4000` + `LLM_BASE_URL`) — useful for cost dashboards or sharing keys across services.

Naming conventions (enforced — match these when generating files):
- Classes: `QAAgent`, `FitsReaderTool`, `NotebookService`, `NotebookRepository`, `NotebookModel`, `QARequest` / `QuizResponse`
- Files: snake_case (`qa_agent.py`, `fits_reader_tool.py`)
- Methods: snake_case verbs (`run_agent`, `fetch_catalog`)

Tech: Python 3.11+, FastAPI, SQLAlchemy async, Pydantic BaseSettings for config, structlog. Package manager is **pip** (deps declared in `pyproject.toml`, installed via PEP 517).

Dev commands (run from `backend/` after `python -m venv .venv` + activate):

```bash
pip install -e ".[dev]"                                    # install deps + dev tools
uvicorn main:app --reload --port 8000                      # API server
celery -A workers.celery_app worker --pool=threads --concurrency=4 --loglevel=info  # background worker (threads pool required on Windows; fine on Linux for I/O-bound tasks)
```

## Frontend architecture (planned)

Data flow — preserve this layering:

```
Page → Custom Hook → Service (TanStack Query + Axios) → /api/proxy/[...path] → FastAPI
                                                              ↑
                                              Next.js route handler hides backend URL & avoids CORS
```

State split (don't mix these):
- **Server state** → TanStack Query (API data, cache, loading/error)
- **Global UI state** → Zustand stores in `src/stores/` (theme, sidebar, modal, session)
- **Local UI state** → `useState`

App Router uses route groups for layout separation:
- `app/(auth)/` — no dashboard chrome
- `app/(dashboard)/` — shared sidebar + navbar layout

Important rules from frontend/README.md:
- **No `localStorage` / `sessionStorage` directly** — use Zustand `persist` middleware.
- **Agent streaming** must use `EventSource` (SSE) in `useAgentStream.ts`, not plain fetch.
- **shadcn/ui** components are copied into `src/components/ui/` (not a dep) — edit freely.
- **Framer Motion variants** live in `src/animations/` (`fade.ts`, `slide.ts`, `stagger.ts`, `page-transition.ts`) — don't inline variants in components.
- **All backend calls go through `/api/proxy/[...path]/route.ts`** — don't hit the FastAPI URL from the browser.

Naming conventions:
- Components: PascalCase (`AgentChatWindow.tsx`)
- Hooks: `use*` camelCase
- Stores: `*Store` (e.g. `agentStore.ts`)
- Services: `*Service` (e.g. `notebookService.ts`)

Tech: Next.js 15 App Router, TypeScript, Tailwind v4, pnpm, Node 20+.

Planned dev commands (per frontend/README.md):

```bash
pnpm install
pnpm dev          # http://localhost:3000
pnpm build && pnpm start
```

## Cross-cutting

- The two READMEs are written in Vietnamese; the user is comfortable reading either Vietnamese or English. Code, identifiers, and commit messages should be English unless asked otherwise.
- API surface lives under `/api/v1/...` on the backend (see backend/README.md §"API Endpoints"). The frontend reaches it through the Next.js proxy route, so route paths in `services/*Service.ts` should be relative to `/api/proxy/`.
- Required env vars (see each README's `.env.example`):
  - Backend: `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `SECRET_KEY`, `NASA_API_KEY`, plus LLM config: `LLM_MODEL` (e.g. `groq/llama-3.3-70b-versatile`), `LLM_FALLBACK_MODELS`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT`, and the provider key for whichever model is selected (`GROQ_API_KEY` for dev; `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` for prod). `EMBEDDING_MODEL` controls vector embeddings separately.
  - Frontend: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_APP_NAME`.

## Development rules

- NEVER commit secrets or API keys
- NEVER skip writing Pydantic schemas for request/response
- NEVER call DB directly from services — always go through repositories
- NEVER instantiate agents directly in routes/services — use AgentRegistry
- NEVER use localStorage directly — use Zustand persist middleware
- NEVER import `groq`, `anthropic`, `openai` SDKs in agents/services/tools — go through `core/llm/llm_client.py` (LiteLLM)
- NEVER add LangGraph, CrewAI, AutoGen, or LangChain agent abstractions — agent orchestration is hand-written by design (see backend/README.md §"Lý do không dùng agent framework có sẵn")
- NEVER hardcode an LLM model name in agent code — read from `settings.LLM_MODEL` so dev/prod swap works via env alone

## Workflow

When implementing a new feature:
1. Read the relevant README section first
2. Propose a plan and file list before writing code
3. Follow the layered architecture strictly (API Route → Service → Orchestrator → Agent)
4. Write types/schemas first, then implementation
5. Ask before creating files outside the planned structure
