# 异步全双工推流与 API 规范 (Websocket & REST API)

这不仅是一套简单的后端 REST API 集合，整个数字生命循环深度依赖了流式控制。以下介绍核心网络连接生命周期。

## 1. WebSocket 事件通道 (`/ws/task/{task_id}`)

为了保证前端 UI（尤其是 Canvas 渲染、加载条）平滑顺畅，中间夹杂极多运算过程通过 WS 来驱动。

### 1.1 鉴权与装载态建立 (Hydration)
前端利用附带 `?token=` 发起连接。
连接建立后，**由于存在单体节点重连可能遗漏断点的缺陷**，服务器不仅会建立流，且在第一时间主动下推一次 `hydration`（断点记忆重放）：

**↓ 服务器 -> 客户端:**
```json
{
  "type": "hydration",
  "task_id": "uuid",
  "status": "WAITING_HUMAN",
  "current_step": 2,
  "max_steps": 5,
  "ui_component": "InvoiceReviewModal",
  "reasoning_summary": "系统在金额核算方面出现疑点，请核实原始发票金额。"
}
```

### 1.2 Redis 分布式订阅广播 (`task:{id}:progress`)
随后，WS Handler 保持对 Redis 的通道监听。在深居内网底层的 Celery Worker 执行完每个 Tool 时会做推送响应：

**↓ Worker -> Redis -> 客户端:**
```json
{
  "type": "progress",
  "task_id": "uuid",
  "payload": {
    "msg": "正在对冲本季度企业流水...",
    "tool_name": "reconcile_tool",
    "percentage": 45
  }
}
```

## 2. API 兜底备用机制

即使极端情况引发 WS 持久掉线（比如代理层 Nginx 等待超时被杀断），依靠以下 REST 接口，业务层仍然是健壮并且可长轮询恢复的。

### `GET /api/v1/tasks/{task_id}/status`
轮询平替方案。提供类似 `hydration` 的全量装载体信息，应对客户端无法接收 WS 的窘境。

### `POST /api/v1/tasks/{task_id}/resume`
如果终端发来 `WAITING_HUMAN` 状态的数据修补（拦截操作完成）：
前端通过 `PUT /api/v1/tasks/{task_id}` 发送完毕人工接管后的最终 Corrected Data，直接发一次该请求。

系统将使用带过期时间（TTL=60s的基于 Redis 的分布式锁），保证只有一个 Request 进入到 `run_task` （FSM引擎再度苏醒，跳过已经记录快照的那 2 步，直接进入第 3 步向下冲刷！）。
```python
# 防重放雪崩底层核心锁
lock_ok = await acquire_lock(key=f"task:{task_id}:resume_lock", value="1", ttl_s=60)
if not lock_ok:
    raise HTTPException(status_code=409, detail="Resume already in progress")
```
