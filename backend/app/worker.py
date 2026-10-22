"""Dedicated MataQorLab automation worker process.

Run with: ``python -m app.worker``. Database leases keep multiple replicas safe.
"""
from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import settings
from app.core.observability import configure_logging
from app.services.etl_scheduler import scheduler_loop
from app.services.smart_alert_scheduler import smart_alert_scheduler_loop
from app.services.data_setup_worker import data_setup_worker_loop

logger = logging.getLogger("mataqorlab.worker")


async def _python_sandbox_loop(stop_event: asyncio.Event) -> None:
    from app.services.python_sandbox import run_next_python_job

    interval = max(1, int(settings.PYTHON_SANDBOX_POLL_SECONDS))
    while not stop_event.is_set():
        result = await run_next_python_job()
        if result is not None:
            logger.info(
                "python_sandbox_job_finished",
                extra={"job_id": result.get("id"), "status": result.get("status")},
            )
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def _heartbeat(stop_event: asyncio.Event, workers: list[asyncio.Task]) -> None:
    interval = max(5, int(settings.WORKER_HEARTBEAT_SECONDS))
    while not stop_event.is_set():
        dlq_depth = 0
        try:
            from app.core.supabase import get_supabase_client
            from app.services.job_dlq import dead_letter_depth

            dlq_depth = await asyncio.to_thread(
                dead_letter_depth, get_supabase_client()
            )
        except Exception as exc:
            logger.warning(
                "worker_dlq_depth_unavailable",
                extra={"error": str(exc)},
            )
        logger.info(
            "worker_heartbeat",
            extra={
                "worker_count": len(workers),
                "healthy_workers": sum(not task.done() for task in workers),
                "etl_enabled": settings.ETL_SCHEDULER_ENABLED,
                "smart_alert_enabled": settings.SMART_ALERT_SCHEDULER_ENABLED,
                "python_sandbox_enabled": settings.PYTHON_SANDBOX_ENABLED,
                "dlq_depth": dlq_depth,
            },
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def run_worker() -> None:
    configure_logging()
    try:
        from app.core.supabase import get_supabase_client
        from app.services.workflow.capability import ensure_workflow_persistence_ready

        await asyncio.to_thread(
            ensure_workflow_persistence_ready, get_supabase_client()
        )
    except Exception as exc:
        logger.error(
            "workflow_capability_check_failed",
            extra={"error": str(exc)[:300]},
        )
        from app.services.workflow.capability import is_production_env

        if is_production_env():
            raise

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover - Windows event loop
            pass

    workers: list[asyncio.Task] = []
    if settings.ETL_SCHEDULER_ENABLED:
        workers.append(asyncio.create_task(scheduler_loop(stop_event), name="etl-scheduler"))
        workers.append(
            asyncio.create_task(data_setup_worker_loop(stop_event), name="data-setup-worker")
        )
    if settings.SMART_ALERT_SCHEDULER_ENABLED:
        workers.append(
            asyncio.create_task(smart_alert_scheduler_loop(stop_event), name="smart-alert-scheduler")
        )
    if settings.PYTHON_SANDBOX_ENABLED:
        workers.append(
            asyncio.create_task(_python_sandbox_loop(stop_event), name="python-sandbox")
        )
    if not workers:
        raise RuntimeError(
            "No worker is enabled; enable ETL, smart alerts, or the Python sandbox worker"
        )

    heartbeat = asyncio.create_task(_heartbeat(stop_event, workers), name="worker-heartbeat")
    logger.info("worker_started", extra={"worker_count": len(workers)})
    stop_waiter = asyncio.create_task(stop_event.wait(), name="worker-stop-waiter")
    done, _ = await asyncio.wait([stop_waiter, *workers], return_when=asyncio.FIRST_COMPLETED)
    failed_tasks = [task for task in done if task is not stop_waiter and task.exception()]
    if failed_tasks:
        stop_event.set()
        for task in failed_tasks:
            logger.error(
                "worker_task_failed",
                extra={"task_name": task.get_name(), "error": str(task.exception())},
            )
    logger.info("worker_stopping")
    await asyncio.gather(*workers, return_exceptions=True)
    stop_waiter.cancel()
    heartbeat.cancel()
    await asyncio.gather(stop_waiter, heartbeat, return_exceptions=True)
    logger.info("worker_stopped")
    if failed_tasks:
        raise RuntimeError(f"Worker task failed: {failed_tasks[0].get_name()}") from failed_tasks[0].exception()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
