import inspect

from app.main import lifespan
from app.worker import run_worker


def test_web_lifespan_does_not_start_background_schedulers():
    source = inspect.getsource(lifespan)
    assert "scheduler_loop" not in source
    assert "smart_alert_scheduler_loop" not in source


def test_dedicated_worker_owns_both_scheduler_loops():
    source = inspect.getsource(run_worker)
    assert "scheduler_loop(stop_event)" in source
    assert "smart_alert_scheduler_loop(stop_event)" in source
    assert "WORKER_HEARTBEAT_SECONDS" not in source  # heartbeat is isolated and testable
