# 数据库实体建模规范 (Database Schema & Indexing)

本项目数据层基于 SQLAlchemy 异步与 PostgreSQL 的底层组合。为了高效驱动 Librarian 等特殊机制，请了解以下核心数据模型及索引建立缘由。

## 1. 核心表结构透视

### `AgentTask` (业务执行主干表)
保存任何被触发的 SOP 实例，无论其目前处于自动执行、崩溃还是等待人类处理的状态。

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `id` | VARCHAR(36) | 通用 UUID v4 |
| `user_id` | VARCHAR(36) | 触发本任务的用户标识（用于外键连表鉴权）|
| `skill` | VARCHAR(255) | 该任务执行的是哪套 SOP，例如 `financial-reconcile` |
| `status` | VARCHAR(50) | `CREATED` / `RUNNING` / `WAITING_HUMAN` / `COMPLETED` / `ERROR` |
| `current_step`| INTEGER | 标记 FSM 游标，异常后可以直接 Resume 跳过已执行逻辑 |

### `TaskCheckpoint` (状态幂等快照)
避免重复执行 Tool 引发灾难的重放防护，记录 FSM 每一步状态。通过 `(task_id, step_index)` 保证全局唯一。

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `task_id` | VARCHAR(36) | 关联至 AgentTask |
| `step_index` | INTEGER | 步序索引 |
| `tool_name` | VARCHAR(255) | 原子函数的命名空间入口记录 |
| `output_summary`| TEXT | 模型或函数的内部成功日志 |
| `next_step` | VARCHAR(50) | Action 指针指向下游流向 |

### `TaskHilState` (挂起快照)
专门开辟的一张用于解耦 Web 侧页面的状态恢复表。

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `task_id` | VARCHAR(36) | [UNIQUE] 一条挂起任务只能活跃一个拦截 |
| `ui_component`| VARCHAR(255)| 通知前端应该渲染哪一块表单面板 |
| `prefill_data`| JSONB | 人工填表前系统大模型已经计算出来的草稿 |
| `reasoning_summary` | TEXT | 面向使用者的告警或挂起动机展示语 |

### `LibrarianKnowledge` (夜间萃取知识库)
最高附加值所在。保存已清洗的历史错误防抖策略库。

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `skill_id` | VARCHAR(255) | 只有同一业务流才会交叉唤起引用 |
| `summary` | TEXT | 精简处理的大模型文字推导步骤 |
| `keywords` | VARCHAR(500) | 特意被提取出的分词集合，用于 TSVECTOR |
| `intent_tags` | JSONB | 基于夜间聚类 AST 树生成的扁平标签树 |

## 2. Psql 级别的全文倒排索引
我们没有在代码层直接用 `.like()` 模糊查找，相反我们在表结构初始化时对 Postgres 表附加了深层索引块结构（GIN Index）：

```sql
-- 在部署阶段数据库产生的隐式加速结构
CREATE INDEX idx_librarian_fts ON "LibrarianKnowledge" 
USING GIN (to_tsvector('simple', keywords || ' ' || summary));
```
如此操作，能保证数十万条历史经验积累以后，Bypass Agent 的拦截响应也是毫秒级的，不会拖垮业务 API 接口耗时。
