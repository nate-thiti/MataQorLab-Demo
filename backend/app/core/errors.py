"""Stable operational error taxonomy for logs and customer incident responses."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDescriptor:
    code: str
    retryable: bool
    customer_message: str


ERRORS = {
    "dependency_unavailable": ErrorDescriptor(
        "dependency_unavailable", True, "A required service is temporarily unavailable."
    ),
    "source_operation_failed": ErrorDescriptor(
        "source_operation_failed", True, "The data source operation failed."
    ),
    "persistence_failed": ErrorDescriptor(
        "persistence_failed", True, "The result could not be saved."
    ),
    "scheduler_failed": ErrorDescriptor(
        "scheduler_failed", True, "The scheduled job failed."
    ),
    "billing_operation_failed": ErrorDescriptor(
        "billing_operation_failed", False, "The billing operation could not be completed."
    ),
    "internal_error": ErrorDescriptor(
        "internal_error", False, "An unexpected error occurred."
    ),
}


def incident_response(code: str, incident_id: str) -> dict[str, object]:
    descriptor = ERRORS.get(code, ERRORS["internal_error"])
    return {
        "detail": descriptor.customer_message,
        "error_code": descriptor.code,
        "incident_id": incident_id,
        "retryable": descriptor.retryable,
    }

