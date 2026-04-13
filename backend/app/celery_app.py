import os

from celery import Celery


def _get_redis_url() -> str:
    # Default matches `.env.example`; actual value is injected by docker-compose.
    return os.environ.get("REDIS_URL", "redis://redis:6379/0")


celery_app = Celery(
    "aicopilot_worker",
    broker=_get_redis_url(),
    backend=_get_redis_url(),
)

# M0: no tasks yet; later phases will register tool tasks.
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"

celery_app.conf.task_routes = {
    'resource_gc_task': {'queue': 'beat_tasks'},
    'pattern_miner_task': {'queue': 'beat_tasks'},
    'librarian_nightly_patrol': {'queue': 'beat_tasks'},
    'task_guardian_patrol': {'queue': 'beat_tasks'},
}

from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "resource-gc-hourly": {
        "task": "resource_gc_task",
        "schedule": crontab(minute=0),
    },
    "pattern-miner-every-10min": {
        "task": "pattern_miner_task",
        "schedule": crontab(minute="*/10"),
    },
    "librarian-nightly-patrol": {
        "task": "librarian_nightly_patrol",
        # Runs at 03:00 UTC every night — after daily traffic dies down
        "schedule": crontab(hour=3, minute=0),
    },
    "task-guardian-patrol": {
        "task": "task_guardian_patrol",
        # Runs every 30 minutes to clean up zombie RUNNING tasks
        "schedule": crontab(minute="*/30"),
    },
}

# Import task modules so Celery registers them on worker startup.
import app.celery_tasks  # noqa: E402,F401

from celery.signals import worker_process_init

@worker_process_init.connect
def init_worker(**kwargs):
    import asyncio
    from app.skills.registry import get_skill_registry_service
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    service = get_skill_registry_service()
    loop.run_until_complete(service.load_all())

