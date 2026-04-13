# AI Copilot Platform Remediation Plan

This implementation plan focuses on patching all the security, architecture, performance, concurrency, and application-level issues identified in the Review Report.

## User Review Required

WARNING

Please review the security changes and testing environment improvements carefully, as some default passwords and tokens handling are strictly overridden. Also note we'll implement adaptive heuristic-based Header Row Detection for Excel, and Template-Driven slide construction for PPTX files mapping.

## Proposed Changes

---

### 1. Security & Auth (S-1 to S-5, P-1)

#### [MODIFY] `backend/app/main.py` & `backend/app/config.py`

* S-1: Remove hardcoded `admin123` password. Use the `ADMIN_BOOTSTRAP_PASSWORD` environment variable. If not set, error out on startup unless admin already exists.
* S-4: Remove `dev-secret-change-me` from config. Require `SECRET_KEY` if running in a non-test environment or generate a strong fallback dynamically.
* D-4: Tighten CORS settings in `main.py` based on `cors_origins`.

#### [MODIFY] `frontend_vite/src/api.js` & `backend/app/routes/ws_task.py`

* S-2: Do not append JWT Token to WebSocket query params. Use an initial Auth message over WebSocket for connection initialization or short-lived auth tickets instead.

#### [MODIFY] `backend/app/routes/auth.py`

* S-3: Restrict `POST /auth/register` so that anonymous users CANNOT register as `admin`. Registration to `admin` will require an existing Admin's token.

#### [MODIFY] `backend/requirements.txt`

* S-5 & D-5: Explicitly remove duplicate `passlib[bcrypt]` and `bcrypt` references, use unified `bcrypt` explicitly without passlib.
* Pin open bounds for `openai`.

#### [MODIFY] `backend/app/security/deps.py`

* P-1: Cache `User` objects inside Redis or use the JWT token role claim directly unless full validation is forced, preventing database roundtrips on every request.

---

### 2. Concurrency & Workers (C-1 to C-5, A-2, P-3, P-4)

#### [MODIFY] `backend/app/redis_lock.py`

* C-1: Add `release_lock` logic, potentially via a reliable Lua script for deleting only if the lock value matches.

#### [MODIFY] `backend/app/celery_tasks.py` & `backend/app/celery_app.py`

* A-2 & C-5: Remove nested `asyncio.run()` pattern in workers. Refactor `run_ai_detection_async` to correctly dispatch async tasks without deadlocking. Update Beat scheduler configuration to separate resource intensive cron jobs.
* C-3: Remove the `_SKILL_REGISTRY_LOADED` global flag in celery to a safer, worker process-based startup (`worker_process_init` signal in celery).
* P-3 & P-4: Optimize `pattern_miner_task` and `librarian_nightly_patrol` loops. For P-4, replace O(N²) clustering loops.

---

### 3. State & Core Architecture (A-1, A-3, A-4, C-2, P-2)

#### [MODIFY] `backend/app/orchestrator/runner.py` & others

* A-1: Remove hardcoded `_skillA_inputs` switch branches. Shift toward dynamic input parsing configured in `skill.json`.
* A-3: Extract `get_session_maker` into a single, centralized `backend/app/db.py` to prevent LRU Cache multiple instantiations.
* A-4: Fix tool idempotency bugs where an empty `data={}` dictionary was mistakenly returned upon success cache hit.

#### [MODIFY] `backend/app/orchestrator/context_store.py`

* C-2: Implement Optimistic Locking utilizing SQLAlchemy's capabilities (using `updated_at` or a `version_id`) on updates to `TaskContext`.
* P-2: Rather than appending infinitely to `context_json`, externalize lists (e.g. `assets`, `detections`) directly to discrete tables/NoSQL or just persist references.

---

### 4. Excel & PPTX Generators (SS-1, SS-2)

#### [MODIFY] `backend/app/shared/excel.py`

* SS-1: Implement dynamic header row discovery. Instead of purely using `next(data)`, scan the top 10 rows and use heuristics to identify the header row (the one most matching candidate strings like "名称", "数量") and subsequently treat below lines as data.

#### [MODIFY] `backend/app/shared/pptx_generator.py`

* SS-2: Stop using `Presentation()` (blank template). Change to `Presentation(template_path)` corresponding to the passed `template_id`. Iterate over specific placeholder objects, filling objects without strict bounds depending on shape placeholders to match custom formatting dynamically rather than hardcoding sizes.

---

### 5. Frontend Enhancements (F-1 to F-4)

#### [MODIFY] `frontend_vite/src/App.jsx` & `frontend_vite/src/main.jsx`

* F-1: Connect React Router to the root `App.jsx`, linking to `Dashboard`, `TaskExecutor`, etc.

#### [MODIFY] `frontend_vite/src/api.js` & `frontend_vite/src/AuthContext.jsx`

* F-2: Refactor `localStorage` token storage.
* F-3 & F-4: Implement WebSocket reconnect mechanisms; fix the mismatch method `getHilState()` -> `getHil()`.

---

## Open Questions

* Do you have a preferred method to store the refresh token instead of localStorage (e.g., HTTPOnly Cookies handled heavily by backend)?
  * 可以使用http only
* Are we allowed to update the db schema freely with Alembic in the fix for D-1?
  * 允许，但请预留admin账号的登录权限（不写死

## Verification Plan

### Automated Tests

* We will remove the SQLite E2E DB configuration `test_e2e.db` and migrate to Postgres for tests (T-2) utilizing Pytest fixtures. Add test coverage for core paths (T-1, T-4).

### Manual Verification

* We will build the modified code, login through frontend `TaskExecutor`, parse Excel `开学季报价.xlsx`, and verify PPT is written nicely from template `开学季结案报告.pptx`!
