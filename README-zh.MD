中文 | [English](./README-en.MD)

# ⚡ Fast Closure Report

**AI 驱动的活动结案报告自动化平台**

*从 Excel 物料表到完整结案 PPT，一条 AI 流水线，三次人工确认，全程可审计。*

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![License](https://img.shields.io/badge/License-MIT-green)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)

---

## 📖 Overview · 项目宏图

**痛点**：每次大型活动结束后，执行团队需要手动核对物料清单、整理现场照片、匹配付款凭证、汇总成结案报告 PPT。这个流程涉及多人协作、多格式文件，平均耗费 4-8 小时，且极易出现数量错漏、发票未匹配等问题。

**解决方案**：Fast Closure Report 构建了一条 12 步 AI 智能体流水线。系统自动解析 Excel 物料表、从云相册拉取照片、调用视觉模型做目标检测，在三个关键决策节点暂停并向人类呈现结构化 UI（标注画布、设计图绑定、收据匹配器），人工确认后自动续跑，最终输出可提交审核的 PPTX 结案报告。

**工程价值**：
- Skill-as-Plugin 架构：新增业务场景只需编写 `skill.json` + `tools/*.py`，无需修改平台核心代码
- 每步 Checkpoint：任务中断后从断点续跑，不重做已完成步骤
- Experience Layer：HIL 每次修正自动蒸馏为 LibrarianKnowledge，逐步提升 AI 准确率
- 全链路可观测：Trace-ID 贯穿 HTTP → Celery → WebSocket，每步工具调用均落库审计

---

## ✨ Killer Features · 核心竞争力

- 🤖 **12 步自动化流水线** — `parse_excel → AI检测 → OCR → 匹配 → 生成PPT`，一键触发
- 🧑‍💻 **Human-in-the-Loop (HIL)** — 在标注、设计绑定、收据确认三个节点注入结构化人工决策
- 🔌 **Skill-as-Plugin** — 每个业务场景是一个独立 Skill，JSON 声明 + Python 实现，热加载
- 🎓 **Experience Layer** — 每次 HIL 修正 → `FeedbackEvent` → `LibrarianKnowledge`（TSVECTOR 全文检索），AI 自我进化
- 🔍 **PatternMiner** — Celery Beat 定时分析 ≥50 条修正记录，生成高频错误报告和 Prompt 调优建议
- ⚡ **异步 AI 检测** — 重型视觉推理任务 offload 到 Celery Worker + 独立推理服务，ASGI 主线程不阻塞
- 🔴 **WebSocket 实时进度** — Redis Pub/Sub 驱动，前端毫秒级感知步骤切换和 HIL 请求
- 🛡️ **DLQ 守护进程** — `task_guardian_patrol` 自动清理超 1 小时未更新的僵尸任务
- 🗑️ **软删除 + 7 天回收站** — `AssetImage` / `ProjectFile` 均支持逻辑删除，GC 任务定期清理磁盘
- 🔐 **RBAC 四角色** — `executor / reviewer / finance / admin`，WebSocket 层实现 IDOR 防护

---

## 🏗️ Architecture Design · 核心架构设计

```mermaid
C4Context
    title Fast Closure Report — System Context (C4 L1)

    Person(executor, "执行人员", "上传文件、完成 HIL 标注")
    Person(reviewer, "审核人员", "审批/驳回结案报告")
    Person(admin, "管理员", "配置 LLM、管理 Skill/用户")

    System_Boundary(platform, "Fast Closure Report Platform") {
        Container(nginx, "Nginx", "反向代理 / 静态文件", "路由 /api/ → API, /ws/ → WS, / → React SPA")
        Container(api, "FastAPI API Server", "Python 3.11 / uvicorn", "HTTP REST + WebSocket，Orchestrator 入口")
        Container(worker, "Celery Worker", "Python / Celery", "异步执行 run_ai_detection，并发=4")
        Container(beat, "Celery Beat", "Python / Celery", "PatternMiner / LibrarianNightly / GC / Guardian")
        Container(inference, "Inference Server", "FastAPI / port 8001", "AI 目标检测推理（独立可替换）")
        ContainerDb(postgres, "PostgreSQL 14", "数据库", "AgentTask / Project / LibrarianKnowledge / JSONB")
        ContainerDb(redis, "Redis 7", "Broker + Pub/Sub", "Celery 任务队列 + task:{id}:progress 频道")
        Container(storage, "File Storage", "本地磁盘 / NFS", "/data/aicopilot，SHA256 内容寻址")
    }

    Rel(executor, nginx, "HTTP/WS", "HTTPS")
    Rel(reviewer, nginx, "HTTP", "HTTPS")
    Rel(admin, nginx, "HTTP", "HTTPS")
    Rel(nginx, api, "proxy_pass", "HTTP/WS upgrade")
    Rel(api, postgres, "asyncpg", "async SQLAlchemy")
    Rel(api, redis, "aioredis", "Pub/Sub + 任务分发")
    Rel(worker, redis, "celery broker", "AMQP over Redis")
    Rel(worker, postgres, "asyncio bridge", "async SQLAlchemy")
    Rel(worker, inference, "HTTP POST /detect", "aiohttp")
    Rel(beat, redis, "celery beat", "定时触发")
    Rel(api, storage, "文件读写", "本地 I/O")
```

```mermaid
graph TB
    subgraph "Skill Runtime Layer"
        SR[SkillRegistryService<br/>lru_cache singleton] -->|importlib 动态加载| TF[Tool Functions<br/>skills/*/tools/*.py]
        SR -->|读取| SJ[skill.json<br/>声明式管道定义]
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
        LK -->|nightly patrol| LT[知识树<br/>parent/leaf hierarchy]
        FE -->|PatternMiner| PR[PatternReport<br/>Top-N error types]
        LK -->|rescue query| LA[Librarian Agent<br/>run_librarian_rescue]
        LA -->|prompt注入| ORC
    end
```

---

## ⚙️ Core Workflows · 引擎运转机制

```mermaid
sequenceDiagram
    autonumber
    actor User as 执行人员
    participant FE as React Frontend
    participant API as FastAPI API
    participant ORC as Orchestrator
    participant CEL as Celery Worker
    participant INF as Inference Server
    participant DB as PostgreSQL
    participant WS as WebSocket/Redis

    User->>FE: 创建项目 + 上传 Excel/图片
    FE->>API: POST /api/tasks/create
    API->>DB: INSERT AgentTask(status=CREATED)
    API->>CEL: send_task("run_task_async")
    API-->>FE: {task_id}
    FE->>API: WS /ws/task/{id} + JWT Auth
    API-->>FE: hydration帧 (status, step)

    rect rgb(240,248,255)
        Note over ORC,DB: AUTO 步骤自动执行
        CEL->>ORC: run_task(task_id)
        ORC->>DB: load_task_context
        ORC->>ORC: parse_excel → classify_assets → fetch_cloud_album
        ORC->>DB: write_checkpoint (每步)
    end

    rect rgb(255,248,220)
        Note over ORC,CEL: 异步 AI 检测 (释放 ASGI worker)
        ORC->>CEL: send_task("run_ai_detection_async")
        ORC-->>API: return (立即释放)
        CEL->>INF: POST /detect {assets, item_names}
        INF-->>CEL: {detections}
        CEL->>DB: save detections to TaskContext
        CEL->>WS: PUBLISH task:{id}:progress (state_change)
        WS-->>FE: task_update (step++)
    end

    rect rgb(255,240,245)
        Note over API,User: HIL #1 — AnnotationCanvas
        ORC->>DB: TaskStatus → WAITING_HUMAN
        ORC->>DB: TaskHilState {ui_component, prefill_json}
        WS-->>FE: task_update {status: WAITING_HUMAN, ui_component: "AnnotationCanvas"}
        FE->>User: 渲染 Fabric.js 标注画布 (AI 框 + 预填)
        User->>FE: 确认/修正标注
        FE->>API: POST /api/hil/{task_id}/submit
        API->>DB: FeedbackEvent 落库
        API->>CEL: send_task("extract_librarian_experience_task")
        API->>ORC: run_task(task_id) 续跑
    end

    rect rgb(240,255,240)
        Note over ORC,DB: 收据 OCR + 匹配
        ORC->>ORC: ocr_receipt → match_receipts
        ORC->>DB: Receipt + ReceiptMatch 落库
    end

    rect rgb(255,240,245)
        Note over API,User: HIL #2 — ReceiptMatcher
        FE->>User: 渲染收据匹配确认 UI
        User->>FE: 确认匹配
        FE->>API: POST /api/hil/{task_id}/submit
        API->>ORC: run_task(task_id) 续跑
    end

    rect rgb(240,248,255)
        Note over ORC,DB: 生成 PPT + 提交审核
        ORC->>ORC: generate_ppt (python-pptx)
        ORC->>DB: Project.pptx_path, status=PENDING_REVIEW
        ORC->>DB: TaskStatus → COMPLETED
        WS-->>FE: task_update {status: COMPLETED}
        FE-->>User: 结案报告就绪，等待审核
    end
```

---

## 📂 Project Structure · 工程骨架

```
Fast-Closure-Report/
├── backend/                        # Python 后端
│   ├── app/
│   │   ├── main.py                 # FastAPI 应用入口，路由挂载，CORS
│   │   ├── models.py               # 所有 SQLAlchemy ORM 模型（23 张表）
│   │   ├── config.py               # pydantic-settings 配置中心
│   │   ├── celery_app.py           # Celery 实例 + Beat 定时任务注册
│   │   ├── celery_tasks.py         # 所有 Celery 任务（AI检测/PatternMiner/GC/Guardian）
│   │   ├── orchestrator/
│   │   │   ├── runner.py           # ⭐ 核心：Skill 步进执行器 + HIL 状态机
│   │   │   └── context_store.py    # TaskContext 乐观锁读写（schema_version）
│   │   ├── routes/                 # FastAPI 路由层
│   │   │   ├── ws_task.py          # WebSocket + Redis Pub/Sub 进度推送
│   │   │   ├── hil.py              # HIL 提交 + FeedbackEvent 写入
│   │   │   ├── tasks_create.py     # 任务创建入口
│   │   │   ├── auth.py             # JWT 登录/刷新
│   │   │   ├── projects.py         # 项目 CRUD + 审核流
│   │   │   ├── admin_*.py          # 管理后台（用户/Skill/工具/权限/配置）
│   │   │   └── experience.py       # Experience Layer 查询接口
│   │   ├── llm/
│   │   │   ├── adapter_factory.py  # LLM 适配器工厂（runtime SystemConfig 驱动）
│   │   │   └── adapters/           # openai_compat.py / configured.py / mock.py
│   │   ├── skills/
│   │   │   ├── registry.py         # Skill 热加载注册中心（importlib）
│   │   │   └── skill_models.py     # SkillJson Pydantic 模型
│   │   ├── tools/
│   │   │   ├── runner.py           # Tool 执行器（超时/错误封装）
│   │   │   ├── registry.py         # Tool 注册表（namespace: skill::tool）
│   │   │   └── base.py             # ToolResult / TaskContext 基类
│   │   ├── shared/
│   │   │   ├── librarian_agent.py  # Librarian RAG 救援（TSVECTOR 检索）
│   │   │   ├── pptx_generator.py   # python-pptx PPTX 生成器
│   │   │   ├── excel.py            # pandas/openpyxl Excel 解析
│   │   │   ├── ocr.py              # pytesseract OCR 封装
│   │   │   ├── vision_adapter.py   # 视觉模型 HTTP 适配器
│   │   │   └── cloud_album.py      # 云相册 aiohttp 拉取
│   │   └── security/
│   │       ├── auth.py             # PyJWT 签发/验证
│   │       ├── deps.py             # FastAPI 依赖注入（get_current_user）
│   │       ├── path_validator.py   # 路径遍历攻击防护
│   │       └── file_validation.py  # 上传文件类型校验
│   ├── skills/
│   │   └── skill-event-report/     # ⭐ 活动结案报告 Skill
│   │       ├── skill.json          # 12步管道声明（含 HIL/async 标记）
│   │       ├── agent_prompt.md     # LLM 系统提示词
│   │       └── tools/              # 12 个 Python 工具实现文件
│   ├── alembic/                    # 数据库迁移
│   ├── tests/                      # 集成测试
│   ├── requirements.txt            # 生产依赖
│   └── Dockerfile
├── frontend_vite/                  # React 19 + Vite 前端
│   ├── src/
│   │   ├── pages/                  # Login / Dashboard / TaskExecutor / Admin / Experience
│   │   ├── components/             # HIL 组件：AnnotationCanvas(Fabric.js) / ReceiptMatcher
│   │   ├── api.js                  # Axios API 客户端
│   │   └── AuthContext.jsx         # JWT 上下文 + 自动刷新
│   └── package.json
├── inference_server/               # AI 推理服务（独立可替换）
│   ├── app/main.py                 # POST /detect 端点
│   └── requirements.txt
├── nginx/                          # Nginx 反向代理
│   └── nginx.conf                  # /api/ → 8000, /ws/ → WS upgrade, / → SPA
├── docker-compose.yml              # 6 服务完整编排
└── docs/                           # 架构文档 / DB Schema / WebSocket 协议
```

---

## 🛠️ Prerequisites · 前置硬性依赖

| 依赖 | 版本要求 | 用途 |
|---|---|---|
| Docker | ≥ 24.0 | 容器编排 |
| Docker Compose | ≥ 2.20 | 多服务启动 |
| Python | 3.11（容器内） | 后端运行时 |
| Node.js | ≥ 18（本地开发） | 前端构建 |
| PostgreSQL | 14（容器内） | 主数据库 |
| Redis | 7 Alpine（容器内） | 队列 + Pub/Sub |
| Tesseract OCR | ≥ 4.1（容器内） | 收据 OCR |
| 操作系统 | Linux / macOS / WSL2 | 宿主机 |

---

## 🚀 Quick Start · 极速起航

### 1. 克隆仓库

```bash
git clone https://github.com/Marcolexxx/Fast-Closure-Report.git
cd Fast-Closure-Report
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 必须修改以下字段：
# SECRET_KEY、PG_PASSWORD、ADMIN_BOOTSTRAP_PASSWORD
```

最小可运行 `.env`：

```dotenv
# Database
PG_DATABASE=aicopilot
PG_USER=aicopilot
PG_PASSWORD=your_strong_password_here
DATABASE_URL=postgresql+asyncpg://aicopilot:your_strong_password_here@postgres:5432/aicopilot

# Redis
REDIS_URL=redis://redis:6379/0

# Security — 必须设置固定值，否则重启后所有 JWT 失效
SECRET_KEY=replace_with_a_64_char_hex_string_here

# Bootstrap Admin Account
ADMIN_BOOTSTRAP_PASSWORD=Admin@2024!

# File Storage
FILE_STORAGE_ROOT=/data/aicopilot
TZ=Asia/Shanghai
```

### 3. 启动所有服务

```bash
docker compose up --build -d
```

### 4. 初始化数据库 & 创建管理员

```bash
# 执行 Alembic 迁移
docker compose exec api alembic upgrade head

# 创建初始管理员账户
docker compose exec api python seed_admin.py
```

### 5. 访问

| 地址 | 用途 |
|---|---|
| http://localhost | React 前端 SPA |
| http://localhost/api/docs | FastAPI Swagger UI |
| http://localhost:8001/docs | Inference Server API |

### 本地前端开发（热更新）

```bash
cd frontend_vite
npm install
npm run dev          # 启动 Vite dev server on :5173
```

---

## ⚙️ Advanced Configuration · 高阶配置

### 核心环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `""` | asyncpg 连接串，格式：`postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://redis:6379/0` | Celery Broker + Pub/Sub |
| `SECRET_KEY` | 随机（**危险**） | JWT 签名密钥，**生产环境必须固定** |
| `ACCESS_TOKEN_EXPIRE_HOURS` | `8` | access_token 有效期（小时） |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | refresh_token 有效期（天） |
| `FILE_STORAGE_ROOT` | `/data/aicopilot` | 文件存储根目录（需挂载持久化卷） |
| `LLM_ADAPTER` | `mock` | LLM 适配器（`mock` / `openai_compat`） |
| `TZ` | `UTC` | 时区（建议 `Asia/Shanghai`） |
| `SKILLS_DIR` | `skills` | Skill 目录（相对 `/app/`） |

### LLM 接入（Admin UI 配置）

系统通过 `SystemConfig` 表（namespace: `llm`）在运行时配置 LLM：

```
Admin Panel → System Config → namespace: llm
  - llm.provider   = openai | azure | custom
  - llm.model      = gpt-4o
  - llm.api_key    = sk-...        (is_secret=true)
  - llm.base_url   = https://...   (OpenAI-compat endpoint)
```

### 添加新 Skill

```bash
mkdir -p backend/skills/skill-new-usecase/tools
# 1. 编写 skill.json（声明管道步骤）
# 2. 在 tools/ 目录下实现各步骤的 Python 工具函数
# 3. 调用 Admin API 热加载：
curl -X POST http://localhost/api/admin/skills/skill-new-usecase/reload \
  -H "Authorization: Bearer <admin_token>"
```

### Docker 生产部署调整

```yaml
# docker-compose.override.yml（生产）
services:
  worker:
    command: celery -A app.celery_app worker --loglevel=warning --concurrency=8
  api:
    environment:
      - SECRET_KEY=${SECRET_KEY}        # 从外部 Secret 注入
      - CORS_ORIGINS=https://your.domain.com
```

---

## 🚧 Troubleshooting · 高频排错指南

### ❌ 问题 1：重启 API 后前端无法访问，提示 401 Unauthorized

**根因**：`SECRET_KEY` 未在 `.env` 中设置固定值。每次容器重启时 `config.py:16` 会调用 `secrets.token_hex(32)` 生成随机密钥，导致所有已签发 JWT 立即失效。

**解决**：
```bash
# 生成一个固定密钥并写入 .env
python -c "import secrets; print(secrets.token_hex(32))"
# 将输出结果填入 .env: SECRET_KEY=<output>
docker compose restart api worker
```

---

### ❌ 问题 2：`docker compose up --build` 失败，pip install 超时

**根因**：`backend/Dockerfile` 硬编码了清华大学 PyPI 镜像源，在中国境外网络环境中无法连通。

**解决**：
```dockerfile
# 修改 backend/Dockerfile 第 5-6 行，移除镜像源配置：
RUN pip install --no-cache-dir --default-timeout=120 --retries=10 -r requirements.txt
```
或在 `.env` / 构建参数中通过 `PIP_INDEX_URL` 指定你所在地区的镜像。

---

### ❌ 问题 3：AI 检测任务长时间 RUNNING 后变为 ERROR

**根因 A**：`celery_tasks.py` 中 `run_async()` 函数在 Celery 同步 Worker 内用 Thread 桥接 asyncio，高并发时（>8 并发任务）线程池耗尽，任务 stall 超过 1 小时后被 `task_guardian_patrol` 标记为 ERROR。

**根因 B**：Inference Server（`:8001`）未启动或健康检查失败。

**排查步骤**：
```bash
# 检查 worker 日志
docker compose logs worker --tail=100

# 检查 inference server 健康
curl http://localhost:8001/health

# 查看僵尸任务（被 Guardian 标记）
docker compose exec postgres psql -U aicopilot -c \
  "SELECT id, status, current_step, updated_at FROM \"AgentTask\" WHERE status='ERROR' ORDER BY updated_at DESC LIMIT 10;"

# 降低 Worker 并发避免线程风险
docker compose exec worker celery -A app.celery_app inspect active
```

---

### 📚 Documentation & Advanced Usage

本 README 仅作核心机制展示。部署细节、二次开发、Tool 编写请移步文档库：

- [环境依赖与本地开发/部署指南](./docs/deployment.md)
- [自定义 Skill 与工具 (Tool) 开发手册](./docs/plugins.md)
- [Librarian Agent 记忆引擎原理解析](./docs/architecture.md)
- [数据库实体建模规范 (Database Schema &amp; Indexing)](./docs/database_schema.md)
- [异步全双工推流与 API 规范 (Websocket &amp; REST API)](./docs/websocket_protocol.md)

---

## 🗺️ Roadmap & License

### Roadmap

| 阶段 | 目标 |
|---|---|
| v1.3 | Inference Server 接入真实 YOLO/GroundingDINO 模型 |
| v1.4 | LibrarianKnowledge 添加 PG GIN 索引，支持向量检索 |
| v2.0 | 多 Skill 并行执行；DAG 依赖声明支持 |
| v2.1 | CORS 动态配置；多租户隔离 |
| v3.0 | LLM 自动 Prompt 调优（基于 PatternReport 闭环） |

### License

MIT License © 2024 Fast Closure Report Contributors