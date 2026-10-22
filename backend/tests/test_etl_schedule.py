from datetime import datetime, timezone

import pytest

from app.services.etl_schedule import (
    CronExpressionError,
    calculate_next_run,
    next_cron_run,
    parse_cron,
)


def test_standard_cron_next_run_in_bangkok_timezone():
    after = datetime(2026, 7, 24, 16, 30, tzinfo=timezone.utc)  # 23:30 Bangkok
    result = next_cron_run("0 8 * * *", "Asia/Bangkok", after=after)
    assert result == datetime(2026, 7, 25, 1, 0, tzinfo=timezone.utc)


def test_weekday_schedule_skips_weekend():
    after = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)  # Friday
    result = next_cron_run("0 8 * * 1-5", "Asia/Bangkok", after=after)
    assert result == datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)


def test_step_and_list_fields_are_supported():
    minute, hour, *_ = parse_cron("*/15 8,9 * * *")
    assert minute.values == frozenset({0, 15, 30, 45})
    assert hour.values == frozenset({8, 9})


@pytest.mark.parametrize(
    "expression",
    ["", "* * * *", "60 * * * *", "* 24 * * *", "* * * * MON", "*/0 * * * *"],
)
def test_invalid_cron_is_rejected(expression):
    with pytest.raises(CronExpressionError):
        parse_cron(expression)


def test_disabled_or_non_cron_schedule_has_no_next_run():
    assert calculate_next_run("manual", None, "UTC", enabled=True) is None
    assert calculate_next_run("cron", "0 * * * *", "UTC", enabled=False) is None
