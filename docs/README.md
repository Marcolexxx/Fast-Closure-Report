# AI Copilot Platform

> **专为严苛企业级业务场景设计的复合型 Agent 调度引擎与创意生产总线。**

AI Copilot Platform 结合了现代大模型（Vision/OCR/LLM）的创造力、逻辑执行引擎的确定性、以及 HIL (Human-In-The-Loop) 的强干预能力，拒绝脆弱的”全自主“幻觉，通过精细化状态机管控，打造让企业放心的下一代 AI 数字员工。

---

## 🌟 核心特性 (Key Features)

- **🧩 确定性状态机架构 (Deterministic Workflow Engine)**
  基于工程化控制论理念，在不可预测的 LLM 上层包裹精密 DAG 操作。AI 负责拆解原子难题，业务框架保证执行流永不脱轨。
- **⏸️ HIL 随时打断与卡口拦截 (Human-In-The-Loop)**
  面对财务数据和对公审计，再好的大模型也不能完全信赖。系统遇到低置信度（Low Confidence）或者关键生成节点，会自动挂起任务、持久化状态上下文，并将决策权抛回至前端 UI，让人工复核后再恢复自动化流。
- **🛠️ 跨维度的技能与工具库 (Scalable Skill & Tools Registry)**
  包含发票交叉 OCR 工具（通过 PDF 原生提取与本地 Vision 视觉提取比对纠偏），及各种 Excel 原生化解析工具、自动化排版渲染 PPT 的全端工作。
- **🌐 异步解耦的心跳通信 (Celery + Redis + WS)**
  底层长耗时的推理（多图片处理、Vision 洞悉等任务）全部路由至长驻的 Async Worker 处理，通过 Redis 毫秒级总线将运行进度条平滑推给用户端。

---

## 🧱 架构透视图 (Architecture Overview)

本项目构建于经典的 **三层架构设计体系**，各司其职，保证弹性稳定：

1. **交互展示层 (Vite / React Reactivity层)**
   提供实时的 WebSocket 响应追踪能力以及深度定制化的业务审批流画布（例如圈占识别标注框的画布、财务报表对冲界面）。
2. **编排引擎与管控层 (Orchestrator)**
   基于 FastAPI。系统的灵魂所在：`runner.py`，在这里负责组装 `skill.json`，挂载和分发并执行具体的原子工具（Tools），并协调 `ContextStore` 读取数据库上下文保证幂等性。
3. **计算与认知底层 (Computing & LLM Core)**
   涵盖外部的 OpenAI/Gemini/Claude 服务或本地布署的 VLLM 以及通过 Celery 建立起来的队列集群，专职做文本结构化提取、图片识别和财务交叉运算验证。

---

## 🚀 极简上手指南 (Quick Start)

### 环境依赖
- Python 3.10+
- Node.js 18+ (用于 Frontend)
- PostgreSQL 13+ 与 Redis 6+ (必需组件，否则无法运行 Celery 与状态流)

### 1. 服务端部署配置 (Backend Setup)

```bash
# 1. 拷贝环境变量并按需修改
cp ./backend/.env.example ./backend/.env

# 2. 推荐使用 Docker Compose 提供基础中间件运行环境
docker-compose up -d redis postgres

# 3. 安装依赖兵并迁移数据库
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python scripts/db_init.py

# 4. 启动主调度后台
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 异步队列激活 (Async Workers)
长时运算（如图像分析）以及定期经验自我归纳，由 Celery 保障运转：
```bash
# 另起一个终端面板
cd backend
celery -A app.celery_app worker -l info -c 4
celery -A app.celery_app beat -l info
```

---

## 💡 高阶玩法 / 插件扩展 (Advanced Usage)

得益于本平台的松耦合特性，开发者可以极低成本在 `backend/skills/` 下开辟具有全新技能专长（例如人事自动筛选简历、舆情自动化播报分析）的 Digital Copilot 员工。

你只需要建立一个新目录并配置 `skill.json`，在定义好对应的 `tools` 和 `type: "human_in_loop"`，系统便会自动热重载（Registry 热更新），将你所写的 Python 原子脚本与 LLM 连接进大流程生命周期并自动匹配对应的卡口管理机制。

> *一切设计皆为赋予 AI 真正的现实价值，释放人类的创造时光。*
