English | [中文](./README-zh.MD)


# ⚡ Fast Closure Report

**AI-Powered Event Closure Report Automation Platform**

*From an Excel materials list to a fully-packaged closure PPT — one AI pipeline, three human checkpoints, end-to-end auditable.*

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![License](https://img.shields.io/badge/License-MIT-green)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)

---

## 📖 Overview

**The problem:** After every large-scale marketing event, execution teams spend 4–8 hours manually cross-checking materials lists, sorting on-site photos, reconciling payment vouchers, and hammering everything into a closure report deck. The process is multi-person, multi-format, and painfully error-prone — mismatched quantities and unreconciled invoices are the norm, not the exception.

**The solution:** Fast Closure Report ships a 12-step agentic pipeline. The system auto-parses Excel BOMs, pulls photos from cloud albums, runs visual AI detection, and pauses at three structured human decision points — an annotation canvas, a design-binding UI, and a receipt reconciliation panel — before auto-resuming and producing a reviewer-ready PPTX closure report.

**What it gives you:**
- **Skill-as-Plugin architecture** — new business workflows ship as `skill.json` + `tools/*.py`. Zero changes to platform core.
- **Step-level checkpointing** — tasks resume from their last checkpoint after any interruption.
- **Experience Layer** — every HIL correction is distilled into searchable `LibrarianKnowledge`, continuously improving AI accuracy over time.
- **Full observability** — Trace-IDs flow from HTTP → Celery → WebSocket; every tool invocation is logged and auditable.

---

## ✨ Killer Features

- 🤖 **12-step automated pipeline** — `parse_excel → AI detection → OCR → receipt matching → PPT generation` — triggered with a single API call
- 🧑‍💻 **Human-in-the-Loop (HIL)** — structured human intervention at annotation, design binding, and receipt confirmation — with pre-filled AI suggestions
- 🔌 **Skill-as-Plugin** — each business domain is an isolated Skill: JSON declaration + Python tools, hot-reloadable at runtime
- 🎓 **Experience Layer** — HIL corrections → `FeedbackEvent` → `LibrarianKnowledge` (PostgreSQL TSVECTOR full-text search) — the system gets smarter with every run
- 🔍 **PatternMiner** — Celery Beat scans ≥50 correction records on a schedule and generates high-frequency error reports with Prompt-tuning recommendations
- ⚡ **Async AI detection** — heavy vision inference is offloaded to a Celery Worker + a dedicated inference service; the ASGI worker thread is never blocked
- 🔴 **Real-time WebSocket progress** — Redis Pub/Sub drives millisecond-level step and HIL state updates to the frontend
- 🛡️ **DLQ Guardian** — `task_guardian_patrol` auto-fails tasks stuck in `RUNNING` for over an hour, preventing pipeline deadlocks
- 🗑️ **Soft-delete + 7-day recycle bin** — `AssetImage` and `ProjectFile` support logical deletion; a GC Beat task handles physical cleanup
- 🔐 **RBAC with 4 roles** — `executor / reviewer / finance / admin`; WebSocket layer enforces IDOR protection

---

## 🏗️ Architecture Design

```mermaid
C4Context
    title Fast Closure Report — System Context (C4 L1)

    Person(executor, "Executor", "Uploads files, completes HIL annotations")
    Person(reviewer, "Reviewer", "Approves or rejects closure reports")
    Person(admin, "Admin", "Configures LLM, manages Skills and users")

    System_Boundary(platform, "Fast Closure Report Platform") {
        Container(nginx, "Nginx", "Reverse Proxy / Static Files", "Routes /api/ → API, /ws/ → WS upgrade, / → React SPA")
        Container(api, "FastAPI API Server", "Python 3.11 / uvicorn", "HTTP REST + WebSocket, Orchestrator entry point")
        Container(worker, "Celery Worker", "Python / Celery", "Async AI detection, concurrency=4")
        Container(beat, "Celery Beat", "Python / Celery", "PatternMiner / LibrarianNightly / GC / Guardian")
        Container(inference, "Inference Server", "FastAPI / port 8001", "AI object detection (independently replaceable)")
        ContainerDb(postgres, "PostgreSQL 14", "Database", "AgentTask / Project / LibrarianKnowledge / JSONB")
        ContainerDb(redis, "Redis 7", "Broker + Pub/Sub", "Celery task queue + task:{id}:progress channel")
        Container(storage, "File Storage", "Local Disk / NFS", "/data/aicopilot, SHA256 content-addressed")
    }

    Rel(executor, nginx, "HTTP/WS", "HTTPS")
    Rel(reviewer, nginx, "HTTP", "HTTPS")
    Rel(admin, nginx, "HTTP", "HTTPS")
    Rel(nginx, api, "proxy_pass", "HTTP/WS upgrade")
    Rel(api, postgres, "asyncpg", "async SQLAlchemy")
    Rel(api, redis, "aioredis", "Pub/Sub + task dispatch")
    Rel(worker, redis, "celery broker", "AMQP over Redis")
    Rel(worker, postgres, "asyncio bridge", "async SQLAlchemy")
    Rel(worker, inference, "HTTP POST /detect", "aiohttp")
    Rel(beat, redis, "celery beat", "scheduled triggers")
    Rel(api, storage, "file I/O", "local disk")
```

```mermaid
graph TB
    subgraph "Skill Runtime Layer"
        SR[SkillRegistryService<br/>lru_cache singleton] -->|importlib hot-load| TF[Tool Functions<br/>skills/*/tools/*.py]
        SR -->|parses| SJ[skill.json<br/>declarative pipeline definition]
        TR[ToolRegistry<br/>namespace: skill_id::tool_name] -->|execute| TF
    end

    subgraph "Orchestrator Layer"
        ORC[runner.run_task] -->|step loop| TR
        ORC -->|optimistic lock| CS[context_store<br/>TaskContext BLOB + schema_version]
        ORC -->|HIL pause| HS[TaskHilState<br/>ui_component + prefill_json]
        ORC -->|checkpoint| CKP[TaskCheckpoint]
    end

    subgraph "Experience Layer"
        FE[FeedbackEvent] -->|Celery task| LK[LibrarianKnowledge<br/>TSVECTOR keywords]
        LK -->|nightly patrol| LT[Knowledge Tree<br/>parent/leaf hierarchy]
        FE -->|PatternMiner| PR[PatternReport<br/>Top-N error types]
        LK -->|rescue query| LA[Librarian Agent<br/>run_librarian_rescue]
        LA -->|prompt injection| ORC
    end
```

---

## ⚙️ Core Workflows

```mermaid
sequenceDiagram
    autonumber
    actor User as Executor
    participant FE as React Frontend
    participant API as FastAPI API
    participant ORC as Orchestrator
    participant CEL as Celery Worker
    participant INF as Inference Server
    participant DB as PostgreSQL
    participant WS as WebSocket/Redis

    User->>FE: Create project + upload Excel/images
    FE->>API: POST /api/tasks/create
    API->>DB: INSERT AgentTask(status=CREATED)
    API->>CEL: send_task("run_task_async")
    API-->>FE: {task_id}
    FE->>API: WS /ws/task/{id} + JWT Auth
    API-->>FE: hydration frame (status, step)

    rect rgb(240,248,255)
        Note over ORC,DB: AUTO steps — run unattended
        CEL->>ORC: run_task(task_id)
        ORC->>DB: load_task_context
        ORC->>ORC: parse_excel → classify_assets → fetch_cloud_album
        ORC->>DB: write_checkpoint (per step)
    end

    rect rgb(255,248,220)
        Note over ORC,CEL: Async AI detection (ASGI worker released immediately)
        ORC->>CEL: send_task("run_ai_detection_async")
        ORC-->>API: return
        CEL->>INF: POST /detect {assets, item_names}
        INF-->>CEL: {detections}
        CEL->>DB: save detections → TaskContext
        CEL->>WS: PUBLISH task:{id}:progress (state_change)
        WS-->>FE: task_update (step++)
    end

    rect rgb(255,240,245)
        Note over API,User: HIL #1 — AnnotationCanvas (Fabric.js)
        ORC->>DB: TaskStatus → WAITING_HUMAN
        ORC->>DB: TaskHilState {ui_component, prefill_json}
        WS-->>FE: task_update {status: WAITING_HUMAN, ui_component: "AnnotationCanvas"}
        FE->>User: Render annotation canvas with AI pre-fills
        User->>FE: Confirm / correct annotations
        FE->>API: POST /api/hil/{task_id}/submit
        API->>DB: FeedbackEvent persisted
        API->>CEL: send_task("extract_librarian_experience_task")
        API->>ORC: run_task(task_id) resume
    end

    rect rgb(240,255,240)
        Note over ORC,DB: Receipt OCR + matching
        ORC->>ORC: ocr_receipt → match_receipts
        ORC->>DB: Receipt + ReceiptMatch persisted
    end

    rect rgb(255,240,245)
        Note over API,User: HIL #2 — ReceiptMatcher
        FE->>User: Render receipt reconciliation UI
        User->>FE: Confirm matches
        FE->>API: POST /api/hil/{task_id}/submit
        API->>ORC: run_task(task_id) resume
    end

    rect rgb(240,248,255)
        Note over ORC,DB: Generate PPT + submit for review
        ORC->>ORC: generate_ppt (python-pptx)
        ORC->>DB: Project.pptx_path, status=PENDING_REVIEW
        ORC->>DB: TaskStatus → COMPLETED
        WS-->>FE: task_update {status: COMPLETED}
        FE-->>User: Closure report ready — pending reviewer approval
    end
```

---

## 📂 Project Structure

```
Fast-Closure-Report/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app entry, router mounts, CORS
│   │   ├── models.py               # All SQLAlchemy ORM models (23 tables)
│   │   ├── config.py               # pydantic-settings configuration hub
│   │   ├── celery_app.py           # Celery instance + Beat schedule registration
│   │   ├── celery_tasks.py         # All Celery tasks (AI detection / PatternMiner / GC / Guardian)
│   │   ├── orchestrator/
│   │   │   ├── runner.py           # ⭐ Core: Skill step-executor + HIL state machine
│   │   │   └── context_store.py    # TaskContext optimistic-lock read/write (schema_version)
│   │   ├── routes/                 # FastAPI route layer
│   │   │   ├── ws_task.py          # WebSocket + Redis Pub/Sub progress delivery
│   │   │   ├── hil.py              # HIL submit + FeedbackEvent write
│   │   │   ├── tasks_create.py     # Task creation entry point
│   │   │   ├── auth.py             # JWT login / refresh
│   │   │   ├── projects.py         # Project CRUD + review workflow
│   │   │   └── admin_*.py          # Admin panel (users / skills / tools / perms / config)
│   │   ├── llm/
│   │   │   ├── adapter_factory.py  # LLM adapter factory (runtime SystemConfig-driven)
│   │   │   └── adapters/           # openai_compat / configured / mock
│   │   ├── skills/
│   │   │   ├── registry.py         # Hot-reload skill registry (importlib)
│   │   │   └── skill_models.py     # SkillJson Pydantic model
│   │   ├── tools/
│   │   │   ├── runner.py           # Tool executor (timeout + error wrapping)
│   │   │   ├── registry.py         # Tool registry (namespace: skill::tool)
│   │   │   └── base.py             # ToolResult / TaskContext base types
│   │   ├── shared/
│   │   │   ├── librarian_agent.py  # Librarian RAG rescue (TSVECTOR retrieval)
│   │   │   ├── pptx_generator.py   # python-pptx PPTX builder
│   │   │   ├── excel.py            # pandas/openpyxl Excel parser
│   │   │   ├── ocr.py              # pytesseract OCR wrapper
│   │   │   ├── vision_adapter.py   # Vision model HTTP adapter
│   │   │   └── cloud_album.py      # Cloud album aiohttp puller
│   │   └── security/               # JWT / path traversal / file type validation
│   ├── skills/
│   │   └── skill-event-report/     # ⭐ The bundled event closure Skill
│   │       ├── skill.json          # 12-step pipeline declaration (HIL + async markers)
│   │       ├── agent_prompt.md     # LLM system prompt
│   │       └── tools/              # 12 Python tool implementation files
│   ├── alembic/                    # DB migrations
│   ├── tests/                      # Integration tests
│   └── Dockerfile
├── frontend_vite/                  # React 19 + Vite frontend
│   ├── src/
│   │   ├── pages/                  # Login / Dashboard / TaskExecutor / Admin / Experience
│   │   ├── components/             # HIL widgets: AnnotationCanvas (Fabric.js) / ReceiptMatcher
│   │   ├── api.js                  # Axios API client
│   │   └── AuthContext.jsx         # JWT context + auto-refresh
│   └── package.json
├── inference_server/               # Standalone AI inference service (swappable)
├── nginx/                          # Reverse proxy config
├── docker-compose.yml              # Full 6-service orchestration
└── docs/                           # Architecture / DB schema / WebSocket protocol
```

---

## 🛠️ Prerequisites

| Dependency | Required Version | Purpose |
|---|---|---|
| Docker | ≥ 24.0 | Container orchestration |
| Docker Compose | ≥ 2.20 | Multi-service startup |
| Python | 3.11 (in-container) | Backend runtime |
| Node.js | ≥ 18 (local dev only) | Frontend build |
| PostgreSQL | 14 (in-container) | Primary database |
| Redis | 7 Alpine (in-container) | Queue + Pub/Sub |
| Tesseract OCR | ≥ 4.1 (in-container) | Receipt OCR |
| OS | Linux / macOS / WSL2 | Host machine |

---

## 🚀 Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/Marcolexxx/Fast-Closure-Report.git
cd Fast-Closure-Report
```

### 2. Configure environment

```bash
cp .env.example .env
# Required: SECRET_KEY, PG_PASSWORD, ADMIN_BOOTSTRAP_PASSWORD
```

Minimal working `.env`:

```dotenv
PG_DATABASE=aicopilot
PG_USER=aicopilot
PG_PASSWORD=your_strong_password_here
DATABASE_URL=postgresql+asyncpg://aicopilot:your_strong_password_here@postgres:5432/aicopilot

REDIS_URL=redis://redis:6379/0

# Must be a fixed value — random default invalidates all JWTs on restart
SECRET_KEY=replace_with_a_64_char_hex_string_here

ADMIN_BOOTSTRAP_PASSWORD=Admin@2024!
FILE_STORAGE_ROOT=/data/aicopilot
TZ=Asia/Shanghai
```

### 3. Spin up all services

```bash
docker compose up --build -d
```

### 4. Run DB migrations & seed admin

```bash
docker compose exec api alembic upgrade head
docker compose exec api python seed_admin.py
```

### 5. Open the app

| URL | Purpose |
|---|---|
| http://localhost | React SPA |
| http://localhost/api/docs | FastAPI Swagger UI |
| http://localhost:8001/docs | Inference Server API |

### Local frontend dev (hot reload)

```bash
cd frontend_vite && npm install && npm run dev   # Vite dev server on :5173
```

---

## ⚙️ Advanced Configuration

### Key environment variables

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `""` | asyncpg DSN: `postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker + Pub/Sub |
| `SECRET_KEY` | random (**dangerous**) | JWT signing key — **must be fixed in production** |
| `ACCESS_TOKEN_EXPIRE_HOURS` | `8` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token TTL |
| `FILE_STORAGE_ROOT` | `/data/aicopilot` | File storage root (mount a persistent volume) |
| `LLM_ADAPTER` | `mock` | LLM adapter (`mock` / `openai_compat`) |
| `TZ` | `UTC` | Timezone |
| `SKILLS_DIR` | `skills` | Skill directory, relative to `/app/` |

### Wiring up a real LLM (runtime, via Admin UI)

```
Admin Panel → System Config → namespace: llm
  llm.provider  = openai | azure | custom
  llm.model     = gpt-4o
  llm.api_key   = sk-...       (marked is_secret)
  llm.base_url  = https://...  (OpenAI-compatible endpoint)
```

### Shipping a new Skill

```bash
mkdir -p backend/skills/skill-my-usecase/tools
# 1. Write skill.json (declare pipeline steps)
# 2. Implement each step as tools/<step_name>.py
# 3. Hot-reload via Admin API — no restart required:
curl -X POST http://localhost/api/admin/skills/skill-my-usecase/reload \
  -H "Authorization: Bearer <admin_token>"
```

---

## 🚧 Troubleshooting

### ❌ Issue 1: Frontend gets 401 Unauthorized after API restart

**Root cause:** `SECRET_KEY` is not set to a fixed value in `.env`. On every container start, `config.py:16` calls `secrets.token_hex(32)`, generating a new random key and instantly invalidating all issued JWTs.

**Fix:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Paste the output into .env: SECRET_KEY=<output>
docker compose restart api worker
```

---

### ❌ Issue 2: `docker compose up --build` fails — pip install timeout

**Root cause:** `backend/Dockerfile` hardcodes Tsinghua University's PyPI mirror (`pypi.tuna.tsinghua.edu.cn`). This mirror is unreachable outside mainland China.

**Fix:** Edit `backend/Dockerfile` lines 5–6 and remove the mirror configuration:
```dockerfile
RUN pip install --no-cache-dir --default-timeout=120 --retries=10 -r requirements.txt
```
Alternatively, set `PIP_INDEX_URL` to a mirror that works in your region.

---

### ❌ Issue 3: AI detection tasks get stuck in RUNNING, then flip to ERROR

**Root cause A:** `run_async()` in `celery_tasks.py` spawns one thread per Celery task to bridge async SQLAlchemy into the sync worker process. Under high concurrency (>8 simultaneous tasks) the thread pool exhausts, tasks stall for >1 hour, and `task_guardian_patrol` marks them as `ERROR`.

**Root cause B:** The Inference Server (`:8001`) is down or unhealthy.

**Diagnosis:**
```bash
# Check worker logs
docker compose logs worker --tail=100

# Verify inference server health
curl http://localhost:8001/health

# Inspect zombie tasks marked by the Guardian
docker compose exec postgres psql -U aicopilot -c \
  "SELECT id, status, current_step, updated_at FROM \"AgentTask\" \
   WHERE status='ERROR' ORDER BY updated_at DESC LIMIT 10;"
```
---

### 📚 Documentation & Advanced Usage

This README illustrates the core mechanisms. For deployment, deep customization, and tool development, see the docs:

- [Deployment &amp; Env Setup](./docs/deployment.md)
- [Custom Skills &amp; Tools Plugin Guide](./docs/plugins.md)
- [Librarian Agent Engine Architecture](./docs/architecture.md)
- [Database Schema &amp; PostgreSQL Indexing](./docs/database_schema.md)
- [Websocket PubSub &amp; REST API Fallback](./docs/websocket_protocol.md)

---

## 🗺️ Roadmap & License

### Roadmap

| Milestone | Target |
|---|---|
| v1.3 | Wire real YOLO / GroundingDINO into Inference Server |
| v1.4 | Add PG GIN index on LibrarianKnowledge; add vector similarity search |
| v2.0 | Parallel Skill execution; DAG dependency declarations in skill.json |
| v2.1 | Dynamic CORS config; multi-tenant isolation |
| v3.0 | LLM auto Prompt-tuning closed-loop (PatternReport → Prompt diff → PromptTuningHistory) |

### License

MIT License © 2024 Fast Closure Report Contributors