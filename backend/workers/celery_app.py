"""Celery app: broker config + task autodiscovery. Use --pool=threads on Windows."""

from __future__ import annotations

from celery import Celery

from core.config import get_settings
from core.logging import configure_logging

_settings = get_settings()


celery_app = Celery(
    "astrolearn",
    broker=_settings.REDIS_URL,
    backend=_settings.REDIS_URL,
    include=[
        "workers.notebook_worker",
        "workers.astronomy_worker",
    ],
)


celery_app.conf.update(
    task_acks_late=True,                      # re-queue on crash
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,             # fairness for long tasks
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.on_after_configure.connect
def _on_configure(sender, **_: object) -> None:
    """Configure logging + register agents at worker boot."""
    configure_logging(log_level=_settings.LOG_LEVEL, json_logs=True)

    # Side-effect import: registers concrete agents.
    import agents  # noqa: F401
