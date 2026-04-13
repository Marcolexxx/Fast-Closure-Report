## 一、安全缺陷（严重级，5项）

### 🔴 S-1：默认密码硬编码 + 自动播种，且不可配置

 **出处** ：`backend/app/main.py` 第 startup 事件，`seed_admin.py`

python

```python
# main.py startup
admin.hashed_password = hash_password("admin123")
```

管理员账号 `admin/admin123` 在每次服务冷启动时 **自动创建** ，密码完全硬编码在源代码中，既不读取环境变量，也没有"仅开发环境"的保护开关。任何部署了这套代码的人，只要开放 8000 端口，都可以直接以 admin 登录，获取全部接口权限。这是生产环境中最常见的高危漏洞来源之一。

 **修复方向** ：通过 `ADMIN_BOOTSTRAP_PASSWORD` 环境变量注入；若未设置则拒绝启动。

---

### 🔴 S-2：JWT Token 通过 URL Query Parameter 明文传递

 **出处** ：`frontend_vite/src/api.js` + `routes/ws_task.py`

js

```js
// api.js
const ws =newWebSocket(`${wsBase}/ws/task/${taskId}?token=${encodeURIComponent(token)}`)
```

python

```python
# ws_task.py
token = websocket.query_params.get("token","")
```

WebSocket 握手时 JWT access token 以 query string 形式出现在 URL 中。这意味着：Nginx 访问日志、浏览器历史记录、CDN 边缘节点日志，全都会明文记录这个 token。即使连接是 HTTPS，URL 参数在服务器端日志中是可见的。标准做法是在 WS 连接建立后发送第一条消息进行认证，或使用短生命周期的专用 WS ticket。

---

### 🔴 S-3：`/auth/register` 接口完全开放，任意人可注册任意角色

 **出处** ：`routes/auth.py`

python

```python
@router.post("/register")
asyncdefregister(body: RegisterRequest)->dict[str, Any]:
    user = User(
        role=body.role if body.role in[r.value for r in UserRole]else UserRole.EXECUTOR.value,
...
)
```

任何人可以不经认证，调用 `POST /auth/register`，并在请求体中指定 `role: "admin"`。代码虽然做了枚举校验，但 `admin` 是有效枚举值，会被直接写入。这意味着匿名攻击者可以自助注册一个 admin 账号，绕过 S-1 的播种机制也能完全控制系统。

 **修复方向** ：注册接口应要求管理员 token 或完全关闭，用 admin 面板创建用户。

---

### 🔴 S-4：JWT Secret Key 默认值为弱密钥，代码直接暴露

 **出处** ：`backend/app/config.py`

python

```python
secret_key:str="dev-secret-change-me"
```

Pydantic Settings 会在环境变量 `SECRET_KEY` 未设置时，静默地使用这个默认值。`docker-compose.yml` 中也没有将 `SECRET_KEY` 作为必填环境变量声明。任何拿到源代码的人都知道这个 key，可以伪造任意用户的 JWT token，完全绕过认证体系。

---

### 🔴 S-5：`passlib` + `bcrypt` 双重引入，存在版本冲突隐患

 **出处** ：`requirements.txt` + `security/auth.py`

python

```python
# requirements.txt
passlib[bcrypt]>=1.7.4
# auth.py
import bcrypt  # 直接引入原生 bcrypt
from passlib.context import CryptContext  # 引入了但实际未使用
```

`passlib` 被引入到 `requirements.txt` 但在 `auth.py` 中实际未使用（`CryptContext` 被导入但所有 hash/verify 操作都直接调用 `bcrypt`）。这制造了一个幽灵依赖：`passlib` 引入了自己的 `bcrypt` 适配层，与直接 `import bcrypt` 可能调用不同的底层版本，在某些 Python 环境下会触发 `AttributeError: module 'bcrypt' has no attribute '__about__'` 的已知 passlib/bcrypt 版本兼容 bug。这个 bug 在生产环境中会导致 **所有登录接口 500 报错** 。

---

## 二、架构缺陷（严重级，4项）

### 🔴 A-1：`_skillA_inputs()` 硬编码映射，完全违反开闭原则

 **出处** ：`orchestrator/runner.py`

python

```python
def_skillA_inputs(tool_name:str, ctx:dict[str, Any])->dict[str, Any]:
if tool_name =="parse_excel":
return ctx.get("parse_excel_input",{})
if tool_name =="classify_assets":
return{"assets": ctx.get("assets",[])}
# ... 12个 if 分支，硬编码每个工具的输入
```

函数名叫 `_skillA_inputs`，已经自承这是针对单一 Skill 的专用实现，写死在通用 Orchestrator 核心代码里。当需要第二个 Skill 时，这里没有任何扩展点——要么复制这个函数写 `_skillB_inputs`，要么给这个函数加更多 `if` 分支。两种方向都是反模式。

 **本质矛盾** ：Skill Registry 和 ToolRegistry 的设计是完全插件化的，但 Orchestrator 的输入映射层把这个插件化完全架空了。

 **修复方向** ：工具函数应接受 `(ctx: dict) -> dict` 的 `extract_inputs` 入参，或在 `skill.json` 中声明输入映射 schema。

---

### 🔴 A-2：Celery Worker 中 `asyncio.run()` 嵌套调用，架构上错误

 **出处** ：`celery_tasks.py`

python

```python
@celery_app.task(name="run_ai_detection_async")
defrun_ai_detection_async(task_id:str, input_data: Dict[str, Any]):
asyncdef_run()-> Dict[str, Any]:
# ... 调用 async ORM、execute_tool、run_task
await run_task(task_id)# ← 在 Celery task 里又调用了完整的 Orchestrator
return asyncio.run(_run())
```

三重问题叠加：①Celery worker 是同步进程，每次调用 `asyncio.run()` 都会新建一个事件循环，然后销毁，数据库连接池等异步资源无法复用；②worker 结束后调用 `await run_task(task_id)`，这让 Celery worker 变成了一个同步包装的 Orchestrator 递归调用者，如果任务链很长，worker 进程会长时间被占用；③`asyncio.run()` 在某些 Python 3.10+ 环境下若当前线程已有事件循环（比如某些 Celery Gevent 模式）会抛出 `RuntimeError: This event loop is already running`。

---

### 🔴 A-3：多个模块重复定义 `get_session_maker()`，单例行为不一致

 **出处** ：`orchestrator/runner.py`、`orchestrator/context_store.py`、`routes/hil.py`、`routes/projects.py`、`routes/auth.py`、`celery_tasks.py`……共 **8+ 个文件**各自定义：

python

```python
@lru_cache(maxsize=1)
defget_session_maker()-> async_sessionmaker[AsyncSession]:
    engine = get_engine()
return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
```

`lru_cache` 的单例作用域是**模块级**的。8 个不同模块各自有各自的 `lru_cache`，意味着每个模块都有自己的 `async_sessionmaker` 实例，底层可能创建多个连接池，而开发者可能误以为整个进程共享同一个连接池。在高并发场景下，数据库连接数会超出预期，导致 `asyncpg: too many connections` 错误。

---

### 🔴 A-4：`idempotency_key` 的幂等机制存在逻辑空洞

 **出处** ：`tools/runner.py`

python

```python
existing = session.execute(
    select(ToolCallLog)
.where(ToolCallLog.task_id == context.task_id,
           ToolCallLog.tool_name == tool_name,
           ToolCallLog.input_digest == input_digest)
).scalars().first()
if existing and existing.status == ToolCallLogStatus.SUCCESS.value:
return ToolResult(success=True, data={}, summary=...)# ← data 是空字典！
```

幂等命中时返回的 `data={}` 是一个 **空字典** ，而不是原始执行的真实 `data`。这意味着如果某个工具在 retry 场景下触发了幂等路径，后续步骤从 `result.data` 里取数据（如 `ctx["items"] = result.data.get("items", [])`）将永远拿到空列表，导致整个后续工具链用错误数据静默执行。

---

## 三、并发与状态管理缺陷（高危，5项）

### 🟠 C-1：Redis 分布式锁只有 `acquire`，没有 `release`

 **出处** ：`redis_lock.py` + `routes/hil.py`

python

```python
asyncdefacquire_lock(key:str, value:str, ttl_s:int=60)->bool:
    result =await client.set(name=key, value=value, nx=True, ex=ttl_s)
returnbool(result)
# ← 没有 release_lock 函数，整个文件只有 acquire
```

HIL submit 时加锁（TTL=10秒），但没有提供 `release_lock`，锁只能靠 TTL 自然过期。如果 HIL submit 处理时间超过 10 秒（比如数据库慢查询），锁会在处理中途过期，造成并发双重提交。反之，如果处理在 1 秒内完成，用户在接下来 9 秒内发起的重试都会被误判为 "already in progress"，返回 409 但操作实际已完成。

---

### 🟠 C-2：`TaskContext` 存储没有乐观锁，并发写入会丢失更新

 **出处** ：`orchestrator/context_store.py`

python

```python
asyncdefsave_task_context(task_id, data, schema_version=1):
# load → modify → save，无版本校验
    row.context_json = json.dumps(data).encode("utf-8")
await session.commit()
```

Orchestrator 主流程和 Celery Worker 均会调用 `save_task_context`。在 Celery 任务完成后调用 `run_task` 的场景下，两个异步执行路径可能同时 load → modify → save，后写入的会覆盖前写入的，造成 context 数据丢失（例如 `detections` 被清除）。`TaskContext` 模型有 `updated_at` 字段但没有被用于乐观锁校验。

---

### 🟠 C-3：`_SKILL_REGISTRY_LOADED` 全局变量在多 Worker 进程中是竞态的

 **出处** ：`celery_tasks.py`

python

```python
_SKILL_REGISTRY_LOADED =False

def_ensure_skill_registry_loaded()->None:
global _SKILL_REGISTRY_LOADED
if _SKILL_REGISTRY_LOADED:
return
    asyncio.run(service.load_all())
    _SKILL_REGISTRY_LOADED =True
```

Celery worker 配置 `--concurrency=4`，在预fork 模式下，4 个子进程各自有独立的 `_SKILL_REGISTRY_LOADED`，均为 `False`，启动时会各自重复执行 `load_all()`，这不是主要问题；真正的问题是：若使用 `gevent` 或 `eventlet` 并发模式，多个协程共享进程内存，`_SKILL_REGISTRY_LOADED = True` 的赋值与 `asyncio.run()` 之间没有锁，可能导致 `load_all()` 被并发执行多次，`tool_registry.delete_prefix` 和 `tool_registry.upsert` 之间出现竞态，导致工具注册中途被清空。

---

### 🟠 C-4：WebSocket 连接没有心跳超时清理机制

 **出处** ：`routes/ws_task.py`

python

```python
asyncfor message in pubsub.listen():
# 无超时控制，永远等待 Redis 消息
```

前端实现了 30 秒 ping，但后端 WebSocket handler 只监听 Redis Pub/Sub 消息， **完全没有处理客户端 ping 帧** ，也没有设置连接超时。如果客户端断开但 TCP 连接未正常关闭（例如手机切换网络），服务端的 `pubsub.listen()` 会永远阻塞等待，泄漏 asyncio 协程和 Redis 连接，直到 Redis 服务端超时。在大量并发用户场景下，这会导致 Redis 连接池耗尽。

---

### 🟠 C-5：Celery Beat 定时任务与 Worker 竞争同一个 `asyncio.run()` 资源池

 **出处** ：`celery_app.py` beat_schedule + `celery_tasks.py`

`pattern_miner_task`（每10分钟）、`resource_gc_task`（每小时）、`librarian_nightly_patrol`（每天3点）、`task_guardian_patrol`（每30分钟），这四个任务都是 `asyncio.run()` 包装的同步 Celery task。若恰好同时触发（例如 3:00 AM 同时有 nightly_patrol 和 pattern_miner），它们会占用 Worker 的所有 4 个 concurrency slot，此时用户发起的 `run_ai_detection_async` 任务会在队列中等待，从用户感知上任务卡住不动。Beat 任务应该独立队列或配置更低的优先级。

---

## 四、测试覆盖缺陷（高危，4项）

### 🟠 T-1：测试套件仅 2 个文件，覆盖率极低

 **出处** ：`backend/tests/`

```
test_security_path_validator_unittest.py  ← 只测 PathValidator 2 个case
test_skillA_tool_chain_unittest.py        ← 只测工具链顺序调用成功
```

整个测试目录只有 2 个文件，约 80 行有效测试代码。没有任何测试覆盖：Orchestrator 状态机、HIL 暂停/恢复流、Librarian 经验蒸馏、认证/授权边界、并发写入冲突、Redis Pub/Sub 发布……等核心逻辑。这意味着任何重构都是在没有安全网的情况下进行的。

---

### 🟠 T-2：E2E 测试使用 SQLite，但生产使用 PostgreSQL，测试无效

 **出处** ：`tests/test_skillA_tool_chain_unittest.py`

python

```python
os.environ["DATABASE_URL"]="sqlite+aiosqlite:///./test_e2e.db"
```

Librarian Agent 的核心能力依赖 PostgreSQL 特有的 `TSVECTOR @@ to_tsquery` 全文检索语法。这段 SQL 在 SQLite 上根本无法运行——但测试没有覆盖 Librarian 路径，所以这个矛盾被掩盖了。一旦测试真的覆盖 Librarian，就会因为 SQLite 不支持 `to_tsvector` 而直接报错。库存里还有个 `test_e2e.db` 文件被提交到 Git 仓库（96KB），这不应该出现在版本控制中。

---

### 🟠 T-3：所有工具实现均为 Mock/Stub，没有一个真实测试

 **出处** ：`skills/skill-event-report/tools/*.py`（通过 `.pyc` 文件间接确认全部存在，但未有真实实现的测试）

E2E 测试调用 `execute_tool("skill-event-report::parse_excel", {}, ctx)` 但 input 是空 `{}`，没有提供真实的 Excel 文件路径，工具内部必然走的是 Mock 分支。测试断言的是 `r1.success == True`，但这个 `True` 是 Mock 返回的，并不能证明 Excel 解析逻辑正确。本质上测试的是"能调用到工具函数不报错"，而不是"工具函数的业务逻辑正确"。

---

### 🟠 T-4：关键安全路径没有任何测试

没有测试覆盖：

* `DataClassifier` 是否真的阻止了图片外泄
* HIL submit 并发双重提交是否被正确拦截
* Role-based access control（reviewer 是否能访问不属于自己部门的项目）
* JWT 过期、篡改场景
* 文件上传的 magic bytes 校验是否可被 bypass

---

## 五、性能缺陷（中危，5项）

### 🟡 P-1：每个 HTTP 请求都单独查询用户表做认证

 **出处** ：`security/deps.py`

python

```python
asyncdefget_current_user(credentials)-> User:
    payload = decode_token(token)
    user =await session.get(User, user_id)# ← 每次都查数据库
return user
```

JWT 本身是无状态的，token 中已经包含 `user_id` 和 `role`，但每次认证还是要额外查询一次数据库验证用户是否存在/是否激活。在高并发场景下，这为每个 API 请求增加了一次数据库 round-trip。正确做法：role 信息已在 token payload 中，仅在需要完整 User 对象时才查库，或使用 Redis 缓存用户状态。

---

### 🟡 P-2：`TaskContext` 序列化随任务推进无限膨胀

 **出处** ：`orchestrator/context_store.py` + `orchestrator/runner.py`

python

```python
ctx["assets"]= result.data.get("assets",[])# 可能几百张图片路径
ctx["detections"]= tool_result.data["detections"]# 每张图片N个检测框
ctx["receipts"]= result.data.get("receipts",[])
# 每步都把所有数据追加到同一个 ctx dict
payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
row.context_json = payload  # 全量覆盖写入
```

到第 10 步时，`ctx` 可能包含数百个 asset 路径 + 数千个 detection 结果 + receipt 列表，整个 JSON 序列化后可能达到数 MB，每步都完整写入 `TaskContext.context_json`（`LargeBinary`）。PostgreSQL 对大行的写入会触发 TOAST 机制，性能显著下降，且每步读取都要反序列化整个大 JSON。

---

### 🟡 P-3：`pattern_miner_task` 每10分钟全表扫描

 **出处** ：`celery_tasks.py`

python

```python
count_q =(
    select(FeedbackEvent.skill_id, func.count(FeedbackEvent.id).label("cnt"))
.where(FeedbackEvent.skill_id.isnot(None))
.group_by(FeedbackEvent.skill_id)
)
```

每 10 分钟对 `FeedbackEvent` 全表做 `GROUP BY skill_id` 聚合，没有增量处理（没有 "只处理上次运行后新增的数据" 的 watermark 机制）。随着 FeedbackEvent 积累，这个查询成本线性增长，且频率为每10分钟一次，会持续占用数据库 CPU。

---

### 🟡 P-4：`librarian_nightly_patrol` 聚类算法是 O(N²) 的

 **出处** ：`celery_tasks.py`

python

```python
for skill_id, skill_leaves in by_skill.items():
for cluster_key, cluster_leaves in cluster_map.items():
        parent_q = select(LibrarianKnowledge).where(
            LibrarianKnowledge.keywords.contains(cluster_key)
)# ← 每个 cluster_key 一次 LIKE 查询
```

对每个 cluster_key 执行一次 `LIKE '%cluster_key%'` 查询，没有索引支持（`keywords` 是 `Text` 类型，没有全文索引）。如果某个 skill 有 50 个聚类，就是 50 次全表扫描。这在数据量较大时会让 nightly job 运行数分钟甚至超时。

---

### 🟡 P-5：推理服务是单 Worker、无并发能力的占位符

 **出处** ：`inference_server/app/main.py`

python

```python
@app.post("/detect")
asyncdefdetect(body: DetectRequest)->dict:
# 返回硬编码 mock 数据，置信度 0.75 和 0.45
    detections.append({"image_id": img_id,"item_name": name,
"candidates":[{"box":...,"confidence":0.75}]})
return{"detections": detections}
```

整个推理服务只有一个 FastAPI 文件，`/detect` 接口返回的是 **固定的 mock 数据** （confidence 永远是 0.75 和 0.45），根本没有调用任何真实的 CV 模型（没有 torch、没有 GroundingDINO、没有 ONNX Runtime 的依赖）。`requirements.txt` 也证实了这一点——只有基础 FastAPI，没有任何 ML 依赖。这意味着核心的视觉 AI 能力 **完全未实现** ，系统输出的 PPT 报告里的"AI检测结果"全是假数据。

---

## 六、技术债（中危，6项）

### 🟡 D-1：没有数据库 Migration 系统，`create_all()` 用于生产

 **出处** ：`app/db_init.py` + `main.py`

python

```python
# db_init.py
await conn.run_sync(Base.metadata.create_all)
# main.py 注释
# M1: still using `create_all`; later will switch to Alembic
```

`create_all()` 只负责创建不存在的表，完全不处理表结构变更。一旦生产环境运行后需要加字段、改类型，只能手工 ALTER TABLE 或删库重建。代码注释承认这是临时方案，但 Alembic 始终没有接入。这让持续交付变得极其危险。

---

### 🟡 D-2：MySQL 与 PostgreSQL 混用遗留，数据类型不统一

 **出处** ：`models.py`

python

```python
# 部分字段使用 JSONB（PostgreSQL 专用）
intent_tags: Mapped[Optional[dict]]= mapped_column(JSONB, nullable=True)
knowledge_json: Mapped[Optional[dict]]= mapped_column(JSONB, nullable=True)
# 但 FeedbackEvent 使用 LargeBinary（MySQL 兼容）
payload_json: Mapped[bytes]= mapped_column(LargeBinary, default=b"{}")
# 代码注释 "FIX B2: payload_json is bytes in MySQL"
```

同一个项目中，部分表用 `JSONB`（PostgreSQL 专有），部分表用 `LargeBinary` 做 JSON 存储（MySQL 兼容遗留）。这使得代码在这两类字段上有完全不同的处理逻辑：JSONB 字段可以直接当 `dict` 读写，`LargeBinary` 字段必须手动 `.encode()`/`.decode()`，到处是容易忘记的隐式约定。

---

### 🟡 D-3：`AgentBranch`、`PromptTuningHistory` 是死代码模型

 **出处** ：`models.py`

python

```python
classAgentBranch(AsyncAttrs, Base):
# prompt_overrides, tool_param_overrides, usage_count, last_used_at
...

classPromptTuningHistory(AsyncAttrs, Base):
# suggestion_summary, action, applied_diff, decided_by
...
```

这两个表在整个代码库中除了模型定义外，没有任何 route、task 或 service 读写它们。它们是"设计了但没有实现"的功能，会在数据库中创建两张空表，给维护者造成困惑——不知道是已废弃还是待实现。

---

### 🟡 D-4：`CORS` 配置允许所有方法和 Header，开发配置混入生产

 **出处** ：`main.py` + `config.py`

python

```python
cors_origins:list[str]=[
"http://localhost:3000",
"http://localhost:5173",
"http://127.0.0.1:5173",
"http://localhost:8000"
]

app.add_middleware(CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],# 所有 HTTP 方法
    allow_headers=["*"],# 所有 Header
)
```

`allow_methods=["*"]` 和 `allow_headers=["*"]` 是开发便利设置，在生产环境应收紧为实际需要的 GET/POST/PATCH/DELETE 和指定 Header。默认的 `cors_origins` 全是本地地址，生产部署后若不覆盖，要么功能不可用（前端被 CORS 阻止），要么为了让前端能工作而改成 `["*"]`（完全开放）。

---

### 🟡 D-5：`bcrypt` 出现在 `requirements.txt` 中，但没有固定版本

 **出处** ：`requirements.txt`

```
passlib[bcrypt]>=1.7.4
openai>=1.12.0
```

关键安全依赖（passlib、PyJWT）和 API 客户端（openai）都只有下界版本约束，没有上界。`openai` SDK 在 v1.x 有多次破坏性变更（函数签名改动），`>=1.12.0` 可能在未来某次 pip install 时拉取到不兼容版本导致运行时崩溃。生产项目应使用 `pip freeze` 锁文件或 Poetry lock。

---

### 🟡 D-6：`test_e2e.db` SQLite 数据库文件被提交到 Git

 **出处** ：项目根目录 + `backend/` 目录

```
/repo/test_e2e.db      (96K)
/repo/backend/test_e2e.db  (100K 另一份)
```

两份测试数据库文件被提交到版本控制。这些文件：① 会随时间与代码中的 schema 不同步；② 可能包含测试过程中生成的敏感数据；③ 在不同开发者机器上状态不同，导致测试结果不可重现。应通过 `.gitignore` 排除，并在测试 setup 中动态初始化。

---

## 七、前端缺陷（中危，5项）

### 🟡 F-1：`App.jsx` 是 Vite 脚手架默认页面，主路由未接入

 **出处** ：`frontend_vite/src/App.jsx`

jsx

```jsx
importreactLogofrom'./assets/react.svg'
// "Get started — Edit src/App.jsx and save to test HMR"
```

`App.jsx` 还是脚手架初始模板，`main.jsx` 所渲染的根组件是这个没有任何业务逻辑的 placeholder。业务页面（`Dashboard`、`TaskExecutor`、`Login` 等）在 `pages/` 目录下，但从 `App.jsx` → `main.jsx` 的路由挂载完全不存在。这意味着打包出的 `dist/` 只能看到一个 Vite 欢迎页，所有业务页面根本无法通过正常路由访问——用户必须手动跳转到具体路径才行，且刷新后 Nginx 如果没有配置 `try_files` 会 404。

---

### 🟡 F-2：Token 存储在 `localStorage`，存在 XSS 攻击面

 **出处** ：`api.js` + `AuthContext.jsx`

js

```js
localStorage.setItem('access_token', data.access_token)
localStorage.setItem('refresh_token', data.refresh_token)
```

JWT token（包括 refresh token）存储在 `localStorage`，可被同域 XSS 脚本直接读取。行业标准做法是将 refresh token 存储在 `HttpOnly Cookie`（JS 无法读取），access token 仅存内存。当前实现一旦页面存在任何 XSS 漏洞，攻击者就能永久接管用户会话（refresh token 有效期 30 天）。

---

### 🟡 F-3：WebSocket 断线没有重连机制

 **出处** ：`api.js`

js

```js
exportfunctionconnectTaskWs(taskId, onMessage){
const ws =newWebSocket(...)
    ws.onmessage=(e)=>{...}
    ws.onclose=()=>clearInterval(ping)// ← 关闭了就没了，没有重连
return ws
}
```

WebSocket 断开时只清理了 ping interval，没有任何重连逻辑。在任务执行期间（可能长达数分钟），用户网络抖动一次，`TaskExecutor` 页面就永久失去状态推送，用户看到的页面会永远停在最后一个状态（比如 `RUNNING`），即使任务已完成也不会更新，除非手动刷新页面。

---

### 🟡 F-4：前端 `tasks.getHilState()` API 方法名与后端 `getHil` 不一致

 **出处** ：`api.js` vs `TaskExecutor.jsx`

js

```js
// api.js 导出
exportconst tasks ={
getHil:(id)=>request('GET',`/tasks/${id}/hil/current`),
// ...
}

// TaskExecutor.jsx 使用
tasks.getHilState(id).then(...)// ← getHilState 不存在！
```

`TaskExecutor.jsx` 调用的是 `tasks.getHilState(id)`，但 `api.js` 导出的方法名是 `tasks.getHil(id)`。这会导致运行时 `TypeError: tasks.getHilState is not a function`，HIL 状态的 prefill 数据永远无法加载，用户看到 HIL 组件时会一直显示"加载上下文中..."的 spinner，无法操作，任务永远卡在 `WAITING_HUMAN` 状态。**这是一个直接导致核心功能不可用的 Bug。**

---

### 🟡 F-5：`frontend/dist` 目录被提交到版本控制

 **出处** ：项目根目录

```
/repo/frontend/dist/   ← 44KB 编译产物
```

编译后的静态文件（`dist/`）被提交到 Git。这违反了基本的版本控制原则：① 二进制/编译产物膨胀仓库体积；② 产物可能与源码不同步（代码改了但没重新编译）；③ 在 CI/CD 流程中会引发歧义（用 Git 里的 dist 还是重新编译？）。应通过 `.gitignore` 排除，在 CI/CD pipeline 中构建。



# 八、落地使用性问题

> 附示例EXCEL与PPTX路径：F:\Code\aicopilot-platform\project-example；
>
> 请注意，该路径下的EXCEL文件和PPTX文件仅作为示例，不代表其他项目或文件均使用该格式结构。

## 🔴 SS -1：Excel 多表头解析失真

当前代码在 `parse_spreadsheet()` 中：

python

```python
# excel.py 第 ~70 行
data = sheet.values
cols =next(data)# ← 只读取第一行作为列头，永远是一行
df = pd.DataFrame(data, columns=cols)
```

`_fill_merged_cells()` 确实填充了合并单元格，但随后  **`cols = next(data)` 只取第一行** 。对于双行表头结构：

```
第1行（合并）: | 物料信息（跨3列） | 数量信息（跨2列） |
第2行（真实）: | 名称 | 类别 | 规格  | 目标数量 | 实际数量 |
第3行（数据）: | 桌布 | 布料 | 大    | 10       | 8        |
```

填充后第1行变为 `物料信息, 物料信息, 物料信息, 数量信息, 数量信息`，被当成列名。第2行 `名称, 类别...` 沦为数据行，`pick_col` 拿着 `"物料信息"` 去匹配，`"物料"` 是子串命中触发 `score=0.85`，三列同名导致 pandas 返回 `DataFrame` 而非 `Series`，后续 `row.get(col_name)` 崩溃或拿到错误数据。

请针对该问题调取F:\Code\aicopilot-platform\project-example下的 [开学季报价.xlxs] 进行解析后适配，但请注意，该EXCEL文件仅作为示例，不代表其他项目或EXCEL均使用该格式结构。

## 🔴 SS -1：PPTX 模板填充失真

python

```python
# pptx_generator.py 第 ~60 行
prs = Presentation()# ← 永远创建空白演示文稿，template_id 只用于命名输出文件
```

`template_id` 完全没有被用于加载模板文件。此外：

* 占位符类型只搜索 `PP_PLACEHOLDER.PICTURE`，跳过了 `OBJECT`/`CONTENT` 类型
* 图片回退定位硬编码 `Inches(4.5)` 假定标准16:9尺寸，A4/自定义模板直接溢出
* 文字字体 `Pt(14)` 硬编码覆盖模板主题字体
* 母版 Logo、背景、配色全部丢失

请针对该问题调取F:\Code\aicopilot-platform\project-example下的 [开学季结案报告.pptx] 进行解析后适配，但请注意，该PPTX文件仅作为示例，不代表其他项目或PPTX均使用该格式结构。
