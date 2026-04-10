param(
  [string]$TaskId = "uat_t1"
)

$ErrorActionPreference = "Stop"

function Assert-Http200([string]$Url) {
  Write-Host ("[HTTP] " + $Url)
  $res = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 8
  if ($res.StatusCode -ne 200) {
    throw "Expected 200, got $($res.StatusCode) for $Url"
  }
}

function Ensure-Task([string]$Id) {
  # Create task row in MySQL via API container (using SQLAlchemy).
  # Use base64-encoded python snippet to avoid quoting pitfalls.
  $code = @"
import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.db import get_engine
from app.models import AgentTask

task_id = r'''$Id'''

async def main():
    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as s:
        t = await s.get(AgentTask, task_id)
        if not t:
            s.add(AgentTask(id=task_id, status='CREATED', trace_id='uat-trace'))
            await s.commit()
    print('OK')

asyncio.run(main())
"@
  $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code))
  docker exec aicopilot-platform-api-1 python -c "import base64; exec(base64.b64decode('$b64').decode('utf-8'))" | Out-Null
}

Write-Host "[UAT] Starting smoke checks"

Write-Host "[UAT] Checking core endpoints"
Assert-Http200 "http://localhost/health"
Assert-Http200 "http://localhost/api/health"
Assert-Http200 "http://localhost/"
Assert-Http200 "http://localhost/annotation.html"
Assert-Http200 "http://localhost/receipt.html"
Assert-Http200 "http://localhost/design.html"

Write-Host "[UAT] Ensuring task exists in DB"
Ensure-Task $TaskId

Write-Host "[UAT] Setting WAITING_HUMAN state"
$body = @{
  ui_component = "ReceiptMatcher"
  reasoning_summary = "UAT: 请确认凭据配对"
  prefill = @{ matches = @(); unmatched = @() }
} | ConvertTo-Json -Depth 6

$res = Invoke-WebRequest -UseBasicParsing -Method Post -Uri ("http://localhost:8000/tasks/{0}/hil/set" -f $TaskId) -ContentType "application/json" -Body $body -TimeoutSec 8
Write-Host ("[UAT] hil/set => " + $res.Content)

Write-Host "[UAT] Triggering celery run_ai_detection_async and checking redis progress"
  $code2 = @"
import os, time, json
import redis
from app.celery_app import celery_app

task_id = r'''$TaskId'''
input_data = {"assets": [], "item_names": ["物料A", "物料B"]}

r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
pub = r.pubsub()
ch = f"task:{task_id}:progress"
pub.subscribe(ch)

celery_app.send_task("run_ai_detection_async", args=[task_id, input_data])

deadline = time.time() + 20
seen = {"queued": False, "completed": False}
while time.time() < deadline:
    m = pub.get_message(ignore_subscribe_messages=True, timeout=1)
    if m and m.get("data"):
        data = m["data"]
        if isinstance(data, (bytes, bytearray)):
            data = data.decode("utf-8", errors="ignore")
        d = json.loads(data)
        if d.get("step_desc") == "queued":
            seen["queued"] = True
        if d.get("step_desc") == "completed" and d.get("current") == 100:
            seen["completed"] = True
            break
    time.sleep(0.1)

print(json.dumps(seen))
"@
  $b642 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code2))
  $out = docker exec aicopilot-platform-api-1 python -c "import base64; exec(base64.b64decode('$b642').decode('utf-8'))"
  Write-Host ("[UAT] progress => " + ($out | Out-String).Trim())

Write-Host "[UAT] Done"

