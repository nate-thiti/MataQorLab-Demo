from unittest.mock import MagicMock, patch

import pytest

from app.services.scheduled_delivery import (
    ScheduledDeliveryError,
    deterministic_narration,
    send_email_report,
)


def test_deterministic_narration_uses_only_evidence():
    text = deterministic_narration({
        "rows": 120,
        "kpis": {"revenue": 1000.0},
        "kpi_changes": {"revenue": 5.0},
        "quality_alerts": [],
    }, "en")
    assert "120 rows" in text
    assert "1,000.00" in text
    assert "+5.00%" in text


def test_email_delivery_requires_server_smtp_configuration():
    with patch("app.services.scheduled_delivery.settings.SMTP_HOST", ""), patch(
        "app.services.scheduled_delivery.settings.SMTP_FROM_EMAIL", ""
    ):
        with pytest.raises(ScheduledDeliveryError, match="not configured"):
            send_email_report(
                recipient="manager@example.com",
                subject="Report",
                narration="Verified evidence",
            )


def test_email_delivery_uses_tls_and_login():
    server = MagicMock()
    context = MagicMock()
    server.__enter__.return_value = server
    with patch("app.services.scheduled_delivery.settings.SMTP_HOST", "smtp.example.com"), patch(
        "app.services.scheduled_delivery.settings.SMTP_FROM_EMAIL", "reports@example.com"
    ), patch("app.services.scheduled_delivery.settings.SMTP_USERNAME", "user"), patch(
        "app.services.scheduled_delivery.settings.SMTP_PASSWORD", "secret"
    ), patch("app.services.scheduled_delivery.smtplib.SMTP", return_value=server), patch(
        "app.services.scheduled_delivery.ssl.create_default_context", return_value=context
    ):
        result = send_email_report(
            recipient="manager@example.com",
            subject="Report",
            narration="Verified evidence",
        )
    server.starttls.assert_called_once_with(context=context)
    server.login.assert_called_once_with("user", "secret")
    server.send_message.assert_called_once()
    assert result["channel"] == "email"
