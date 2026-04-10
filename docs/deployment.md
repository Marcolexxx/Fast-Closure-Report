# 部署与配置指南 (Deployment Guide)

本项目深度依赖微服务架构和多模态大模型的接入，并非开箱即用的纯粹单体脚本。为达到最佳运行效果，请严格遵循以下拓扑要求。

## 0. 物理部署拓扑 (Deployment Topology)

```mermaid
graph TD
    subgraph Client
        A[Vite/React SPA] 
    end
    
    subgraph Gateway
        B[Nginx / API Gateway]
    end
    
    subgraph Application
        C[FastAPI Uvicorn Node 1..N]
        D[WS Manager State Hydration]
        E[Celery Worker Cluster IO LLM]
        F[Celery Beat Cron Jobs]
    end
    
    subgraph Infrastructure
        G[(PostgreSQL 14)]
        H[(Redis 7)]
    end
    
    A -->|Static Resources| B
    A -->|REST API| B
    A -->|WebSocket w/ reconnect| B
    B -->|WebSocket| A
    
    B --> C
    B --> D
    
    C -->|R/W| G
    C -->|Task Publish| H
    D -->|PubSub| H
    H -->|PubSub| D
    
    E -->|Task Consume & PubSub| H
    H -->|Task Dispatch| E
    E -->|Write Back| G
    
    F -->|Trigger Nightly| H
```

## 1. 硬件预估与前置装备

- **操作系统**：Ubuntu 22.04+ (生产) / Windows 11 WSL2 (开发)。
- **持久层底座**：
  - **PostgreSQL 14+ (必须)**：系统重度依赖 `JSONB` 结构保存带有层级特征的面相对象结构，且必须使用其强大的 `TSVECTOR` 完成 Librarian 模块中经验词切分反查。**【警告】严禁降级使用 MySQL**。
  - **Redis 7.0+**：用于承担 Celery Broker 序列化通道以及 Websocket 的断点进度广播 (`TaskProgress`)。
- **配置规格边界**：推理 Worker 会加载高频 HTTP / Python PIL 等模块处理几十 MB 的发票长卷。单台 Worker 实例建议不少于 **2核 / 4GB RAM**。

## 2. 工程化环境变量设定

在根目录和 `backend/` 下应维护 `.env` 配置文件。除标准的秘钥与安全签发外，这三个必须着重关切：

```ini
# --- 数据库配置池 ---
PG_DATABASE=aicopilot
PG_USER=aicopilot
PG_PASSWORD=aicopilot
DATABASE_URL=postgresql+asyncpg://${PG_USER}:${PG_PASSWORD}@postgres:5432/${PG_DATABASE}

# --- Redis 高可用通道 ---
REDIS_URL=redis://redis:6379/0

# --- 外部视觉大模型适配层 (Ext Vision LLM) ---
# 系统中 `ExternalLLMAdapter` 高度依赖此项。必须指向完整的 OpenAI 兼容 / V1 路由结构。
# 国内合规推荐：Qwen-VL-Max / GLM-4V。
VISION_API_KEY=sk-xxxxxx-xxxx-xxxx
VISION_BASE_URL=https://api.openai.com/v1
VISION_MODEL_NAME=gpt-4o
```
*提示：所有高清传图在发送至此 Token 网关前，均会被 `vision_adapter.py` 使用 Pillow 进行 2048px 安全缩减和 10MB 限流保护操作。*

## 3. 手动启停流向 (非 Docker Compose)

如果您没有在生产环境应用容器调度的习惯，您可以借由下列原始指令驱动系统引擎。

### 3.1 启动核心通讯中枢 (Gateway API)
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# [可选] 初始化权限拦截表并触发 Alembic 或原生 CreateAll
python scripts/db_init.py

# 启动异步高并发容器
uvicorn app.main:app --port 8000 --host 0.0.0.0 --log-level info
```

### 3.2 启动计算底垫 (Celery Worker/Beat)
所有“长周期大开销工作”（例如分析一本多页的 PPT、向大模型扔图索要 OCR）将自动派发到这里。
```bash
# 面板 A：接客 Worker 
# (负责执行 AgentTask 并发布 PubSub)
celery -A app.celery_app worker --loglevel=info --concurrency=4 -O fair

# 面板 B：巡更防线 
# (负责清理僵尸任务的 DLQ 及深夜执行 Librarian 提纯重构)
celery -A app.celery_app beat --loglevel=info
```

### 3.3 前端构建态
```bash
cd frontend_vite
npm install
npm run build 
# 将打包后的 /dist 交由 Nginx 挂载，并向 /api 反向代理至 Uvicorn 8000
```
