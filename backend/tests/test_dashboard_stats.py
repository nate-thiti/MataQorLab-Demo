from unittest.mock import MagicMock

import pytest

from app.services import dashboard_stats


def test_dashboard_stats_returns_recent_cache_on_transient_failure(monkeypatch):
    dashboard_stats._CACHE.clear()
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = {
        "files": 2,
        "totalSize": 100,
    }

    assert dashboard_stats.get_dashboard_stats("user-1", client=client)["files"] == 2

    client.rpc.return_value.execute.side_effect = OSError("network unreachable")
    result = dashboard_stats.get_dashboard_stats("user-1", client=client)

    assert result["files"] == 2
    assert result["stale"] is True


def test_dashboard_stats_returns_service_error_without_cache():
    dashboard_stats._CACHE.clear()
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = OSError("dns unavailable")

    with pytest.raises(dashboard_stats.DashboardStatsUnavailable):
        dashboard_stats.get_dashboard_stats("user-1", client=client)
