# Backend — Multi-Agent Astronomy & Learning System

## Tổng quan

Backend cho hệ thống đa tác nhân hỗ trợ học tập và phân tích dữ liệu thiên văn.
Cung cấp các API cho: Multi-Agent orchestration, NotebookLM (Q&A, Summarize, Quiz, Flashcard), và Astronomy data analysis.

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Framework | FastAPI |
| Agent Framework | **Không dùng** — tự code chay (BaseAgent + Orchestrator + Tool + Workflow) |
| LLM Gateway | LiteLLM (proxy thống nhất cho mọi LLM provider) |
| LLM (development) | Groq API (llama-3.x, mixtral) — nhanh & rẻ khi dev/test |
| LLM (production) | Claude (Anthropic) hoặc GPT (OpenAI) — switch qua config, không sửa code |
| Vector DB | Qdrant hoặc ChromaDB |
| Database | PostgreSQL + SQLAlchemy (async) |
| Cache / Session | Redis |
| Task Queue | Celery + Redis |
| Astronomy | Astropy, Astroquery |
| Package Manager | pip (chuẩn, qua `pyproject.toml` — PEP 517) |
| Python version | 3.11+ |

### Lý do không dùng agent framework có sẵn

- **Kiểm soát hoàn toàn** luồng điều phối, retry, logging, streaming — không bị giới hạn API của framework.
- **Học sâu** cách multi-agent system hoạt động (đây cũng là mục tiêu của project).
- **Ít dependency** — tránh breaking change từ LangGraph / CrewAI.
- Trade-off: phải tự viết base classes (`BaseAgent`, `BaseTool`, `BaseWorkflow`), registry, message passing, state machine cho orchestrator.

### Lý do dùng LiteLLM

- Một interface duy nhất cho Groq / Claude / GPT / Gemini / Ollama.
- Switch provider chỉ qua biến môi trường, không sửa code agent.
- Built-in: retry, fallback, cost tracking, rate limiting, caching.
- Dev local có thể chạy LiteLLM proxy (`litellm --config config.yaml`) hoặc gọi trực tiếp qua `litellm.completion()`.

## Cấu trúc thư mục

```
backend/
├── main.py                        # Entrypoint FastAPI app
├── pyproject.toml                 # Dependencies
├── .env                           # Biến môi trường (không commit)
├── .env.example                   # Mẫu biến môi trường
│
├── core/                          # Cấu hình & shared utilities
│   ├── config.py                  # Settings dùng Pydantic BaseSettings
│   ├── security.py                # JWT, password hashing
│   ├── exceptions.py              # Custom exception classes
│   ├── logging.py                 # Logger setup (structlog)
│   ├── dependencies.py            # FastAPI Dependency Injection container
│   └── llm/
│       ├── llm_client.py          # Wrapper quanh LiteLLM (completion, stream, embed)
│       ├── llm_router.py          # Chọn model theo env: dev=groq, prod=claude/gpt
│       └── prompt_templates.py    # System prompts dùng chung cho các agent
│
├── api/
│   └── v1/
│       ├── router.py              # Gộp tất cả routes vào 1 router
│       └── routes/
│           ├── agent_routes.py    # /agents/*
│           ├── notebook_routes.py # /notebooks/*
│           ├── astronomy_routes.py# /astronomy/*
│           ├── session_routes.py  # /sessions/*
│           └── user_routes.py     # /users/*
│
├── agents/                        # Multi-Agent Layer (TỰ CODE, không dùng framework)
│   ├── base/
│   │   ├── base_agent.py          # Abstract BaseAgent (ABC) — định nghĩa run(), stream()
│   │   ├── agent_registry.py      # Registry pattern: đăng ký & lookup agent theo tên
│   │   ├── agent_state.py         # Dataclass state: messages, scratchpad, tool_calls
│   │   └── agent_message.py       # Schema message chuẩn giữa các agent (role, content, metadata)
│   │
│   ├── orchestrator/
│   │   ├── orchestrator_agent.py  # Agent điều phối chính, nhận task → chọn agent
│   │   ├── task_planner.py        # Phân tích task, tạo execution plan (gọi LLM)
│   │   └── router.py              # Logic routing: task → agent phù hợp (rule-based + LLM)
│   │
│   ├── astronomy/
│   │   ├── data_analyst_agent.py  # Phân tích dữ liệu thiên văn (FITS, catalog)
│   │   ├── image_processor_agent.py # Xử lý ảnh thiên văn
│   │   └── catalog_agent.py       # Tra cứu Simbad, NED, VizieR
│   │
│   ├── notebook/
│   │   ├── qa_agent.py            # Q&A từ tài liệu đã upload
│   │   ├── summarizer_agent.py    # Tóm tắt tài liệu
│   │   ├── quiz_agent.py          # Tạo bộ câu hỏi trắc nghiệm
│   │   └── flashcard_agent.py     # Tạo flashcard học thuật
│   │
│   └── support/
│       ├── retriever_agent.py     # RAG: tìm kiếm vector DB
│       └── validator_agent.py     # Kiểm tra & format output của agent khác
│
├── services/                      # Business Logic Layer (không động trực tiếp vào DB)
│   ├── agent_service.py           # Khởi chạy, quản lý lifecycle agent
│   ├── session_service.py         # Quản lý session hội thoại
│   ├── notebook_service.py        # CRUD notebook, xử lý tài liệu
│   ├── astronomy_service.py       # Logic phân tích dữ liệu thiên văn
│   └── user_service.py            # Auth, profile
│
├── tools/                         # Tools cho Agent sử dụng (Strategy pattern)
│   ├── base_tool.py               # Abstract BaseTool
│   ├── astronomy/
│   │   ├── simbad_tool.py         # Query Simbad database qua Astroquery
│   │   ├── nasa_api_tool.py       # NASA APIs (APOD, Exoplanet Archive...)
│   │   ├── fits_reader_tool.py    # Đọc & parse file FITS bằng Astropy
│   │   └── astropy_tool.py        # Tính toán thiên văn (tọa độ, phổ...)
│   │
│   └── knowledge/
│       ├── vector_search_tool.py  # Tìm kiếm semantic trong vector DB
│       ├── web_search_tool.py     # Tìm kiếm web (Tavily / SerpAPI)
│       └── pdf_parser_tool.py     # Parse PDF, extract text & metadata
│
├── workflows/                     # Orchestration: kết hợp nhiều agent thành pipeline
│   ├── base_workflow.py           # Abstract BaseWorkflow — define steps, state, error handling
│   ├── workflow_engine.py         # Engine chạy workflow: tuần tự / song song / conditional
│   ├── notebook_workflow.py       # Upload → Index → Q&A / Summary / Quiz
│   ├── astronomy_workflow.py      # Upload FITS → Analyze → Generate report
│   └── learning_workflow.py       # Học có hướng dẫn: đọc → quiz → flashcard
│
├── memory/
│   ├── short_term/
│   │   └── conversation_memory.py # Lưu lịch sử hội thoại trong session (Redis)
│   └── long_term/
│       └── vector_store.py        # Interface với Qdrant / ChromaDB
│
├── repositories/                  # DB Access Layer (Repository pattern)
│   ├── base_repository.py         # Generic CRUD abstract class
│   ├── agent_repository.py
│   ├── notebook_repository.py
│   ├── session_repository.py
│   └── user_repository.py
│
├── models/                        # SQLAlchemy ORM Models
│   ├── base_model.py              # Base với id, created_at, updated_at
│   ├── agent_model.py
│   ├── notebook_model.py
│   ├── session_model.py
│   ├── message_model.py
│   └── user_model.py
│
├── schemas/                       # Pydantic Schemas (request / response)
│   ├── agent_schema.py            # AgentRunRequest, AgentResponse
│   ├── notebook_schema.py         # NotebookCreateRequest, QARequest, QuizResponse...
│   ├── astronomy_schema.py        # FitsUploadResponse, CatalogSearchRequest...
│   ├── session_schema.py
│   └── user_schema.py
│
└── workers/                       # Celery background tasks
    ├── celery_app.py              # Celery instance & config
    ├── notebook_worker.py         # Xử lý index tài liệu nền (nặng, async)
    └── astronomy_worker.py        # Ingest & phân tích FITS nền
```

## API Endpoints

```
# Agents
POST   /api/v1/agents/run                   # Chạy agent với task bất kỳ
GET    /api/v1/agents/                      # Danh sách agents có sẵn
GET    /api/v1/agents/{agent_id}/status     # Trạng thái agent đang chạy

# Notebook
POST   /api/v1/notebooks/                   # Tạo notebook mới
GET    /api/v1/notebooks/                   # Danh sách notebooks
GET    /api/v1/notebooks/{id}               # Chi tiết notebook
POST   /api/v1/notebooks/{id}/upload        # Upload tài liệu (PDF, txt...)
POST   /api/v1/notebooks/{id}/qa            # Hỏi đáp từ tài liệu
POST   /api/v1/notebooks/{id}/summarize     # Tóm tắt tài liệu
POST   /api/v1/notebooks/{id}/quiz          # Tạo bộ câu hỏi quiz
POST   /api/v1/notebooks/{id}/flashcards    # Tạo flashcard

# Astronomy
POST   /api/v1/astronomy/upload-fits        # Upload file FITS
POST   /api/v1/astronomy/analyze            # Phân tích dữ liệu
GET    /api/v1/astronomy/catalog/search     # Tìm kiếm Simbad / NED
POST   /api/v1/astronomy/report             # Tạo báo cáo phân tích

# Sessions
GET    /api/v1/sessions/                    # Lịch sử session
GET    /api/v1/sessions/{id}/messages       # Lịch sử chat trong session
DELETE /api/v1/sessions/{id}                # Xóa session

# Users
POST   /api/v1/users/register
POST   /api/v1/users/login
GET    /api/v1/users/me
```

## Quy tắc đặt tên

| Thành phần | Convention | Ví dụ |
|---|---|---|
| Class Agent | PascalCase + `Agent` | `QAAgent`, `OrchestratorAgent` |
| Class Tool | PascalCase + `Tool` | `FitsReaderTool`, `VectorSearchTool` |
| Class Service | PascalCase + `Service` | `NotebookService` |
| Class Repository | PascalCase + `Repository` | `NotebookRepository` |
| ORM Model | PascalCase + `Model` | `NotebookModel` |
| Pydantic Schema | PascalCase + `Request`/`Response` | `QARequest`, `QuizResponse` |
| File module | snake_case | `qa_agent.py`, `fits_reader_tool.py` |
| Method | snake_case động từ | `run_agent()`, `fetch_catalog()` |
| Hằng số | UPPER_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |

## Luồng data

```
Request
  → API Route        (validate schema)
    → Service        (business logic)
      → Orchestrator (chọn agent & tool)
        → Agent      (thực thi task)
          → Tool     (gọi external API / DB)
          → Memory   (đọc/ghi context)
        ← Agent result
      ← Orchestrator tổng hợp
    → Repository     (lưu kết quả vào DB)
  ← Response schema
```

## Biến môi trường (.env.example)

```env
# App
APP_ENV=development
SECRET_KEY=your-secret-key

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/astro_db

# Redis
REDIS_URL=redis://localhost:6379

# Vector DB
QDRANT_URL=http://localhost:6333

# LLM Gateway (LiteLLM)
# Format model: "<provider>/<model_name>" — LiteLLM tự route đến đúng provider
LLM_MODEL=groq/llama-3.3-70b-versatile        # dev mặc định
# LLM_MODEL=anthropic/claude-sonnet-4-6       # production (Claude)
# LLM_MODEL=openai/gpt-4o                     # production (GPT)

LLM_FALLBACK_MODELS=groq/llama-3.1-8b-instant # fallback khi model chính lỗi
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=4096
LLM_TIMEOUT=60

# Provider API keys (chỉ cần key cho provider đang dùng)
GROQ_API_KEY=your-groq-key
ANTHROPIC_API_KEY=                            # optional, dùng khi prod
OPENAI_API_KEY=                               # optional, dùng khi prod

# Embedding model (cho vector DB)
EMBEDDING_MODEL=groq/...                      # hoặc openai/text-embedding-3-small khi prod

# Astronomy APIs
NASA_API_KEY=your-nasa-key
```

## LLM usage pattern

Tất cả agent **không gọi trực tiếp** SDK của Groq / Anthropic / OpenAI.
Thay vào đó dùng `core/llm/llm_client.py` — một wrapper mỏng quanh LiteLLM:

```python
# core/llm/llm_client.py (sketch)
from litellm import acompletion
from core.config import settings

class LLMClient:
    async def complete(self, messages, *, model=None, **kwargs):
        return await acompletion(
            model=model or settings.LLM_MODEL,
            messages=messages,
            fallbacks=settings.LLM_FALLBACK_MODELS,
            timeout=settings.LLM_TIMEOUT,
            **kwargs,
        )

    async def stream(self, messages, **kwargs):
        # async generator yield từng chunk
        ...
```

Lợi ích:
- Đổi `LLM_MODEL` trong `.env` là chuyển toàn bộ hệ thống từ Groq → Claude/GPT, không sửa code.
- Một chỗ duy nhất để thêm: retry, logging cost, prompt caching, rate limit.
- Test dễ — mock `LLMClient` thay vì mock từng provider SDK.

## Khởi chạy (development)

```bash
# Tạo virtual env (lần đầu)
python -m venv .venv

# Activate venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# Cài dependencies (production + dev tools) từ pyproject.toml
pip install -e ".[dev]"
# Chỉ production (không pytest, ruff, mypy):
# pip install -e .

# Chạy server
uvicorn main:app --reload --port 8000

# Chạy Celery worker (terminal riêng)
# Trên Windows BẮT BUỘC dùng --pool=threads (hoặc --pool=solo) vì pool prefork
# mặc định (billiard) bị WinError 5 do cách Windows xử lý semaphore.
# Task của AstroLearn là I/O-bound (DB, LLM, FITS) nên threads phù hợp nhất.
celery -A workers.celery_app worker --pool=threads --concurrency=4 --loglevel=info

# (Tùy chọn) Chạy LiteLLM proxy server thay vì gọi qua SDK
# Hữu ích khi muốn dashboard, cost tracking, hoặc share key giữa nhiều service
litellm --config configs/litellm.yaml --port 4000
# Khi đó set LLM_BASE_URL=http://localhost:4000 trong .env
```

## Ghi chú quan trọng

- **Không import trực tiếp** `groq`, `anthropic`, `openai` SDK trong agent / service. Luôn đi qua `core/llm/llm_client.py`.
- **Không dùng** LangGraph, CrewAI, AutoGen, LangChain agents. Mọi pattern (ReAct, plan-execute, supervisor) tự implement trong `agents/` và `workflows/`.
- **Streaming**: agent expose method `stream()` trả về async generator — FastAPI route convert sang SSE cho frontend `useAgentStream`.
- **State của agent** lưu trong `AgentState` dataclass, persist qua Redis (short-term) — không lưu state ngầm trong instance variable.

### Memory

- **KnowledgeBase was removed** and replaced by `CatalogCache` (Postgres, `memory/long_term/catalog_cache.py`) — a focused cache for SIMBAD / NED / VizieR name-form lookups consulted by `CatalogAgent`. TTL via `CATALOG_CACHE_TTL_DAYS` (default 7). Coordinate (RA/Dec) queries deliberately bypass the cache. A future cross-domain knowledge layer would be a separate table.
- **ConversationMemory** (Redis, `memory/short_term/`) is wired into `OrchestratorAgent` — see §"Chat / Orchestrator" below.

### Chat / Orchestrator

- **LLM history is managed server-side** via `ConversationMemory` (Redis), keyed by `session_id`. `OrchestratorAgent` reads the last 8 turns at the start of every `run()` / `stream()` and persists the user + assistant turn at the end of each terminal branch (chat, off-topic decline, NASA-direct, task plan).
- Feature flag: **`ENABLE_CHAT_HISTORY_MEMORY`** (default: `true`). Flip to `false` to disable server-side memory at runtime without redeploying — the orchestrator falls back to whatever `task["history"]` the request inlines (legacy path).
- Frontend sends only `query` + `session_id` (+ optional `notebook_id`) — **no inline history**. See `frontend/src/hooks/useChat.ts`.
- The visual chat scrollback (`chatStore.messages`, capped at 50) is independent of the server-side LLM window — that mismatch is intentional and the two numbers answer different questions.