import re
from pathlib import Path


CRITICAL_MODULES = [
    "app/api/routes.py",
    "app/api/stripe_routes.py",
    "app/services/visualizations.py",
    "app/services/etl_scheduler.py",
    "app/services/smart_alert_scheduler.py",
]

# Match real print() calls only — substring "print(" false-positives on fingerprint(.
_PRINT_CALL_RE = re.compile(r"(?<![\w.])print\s*\(")


def test_critical_paths_do_not_use_print_for_operational_failures():
    backend_root = Path(__file__).resolve().parents[1]
    offenders = [
        module
        for module in CRITICAL_MODULES
        if _PRINT_CALL_RE.search((backend_root / module).read_text(encoding="utf-8"))
    ]
    assert offenders == []

