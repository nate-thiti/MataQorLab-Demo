"""Upload and ingest file size guards."""
from __future__ import annotations

from app.core.config import settings


class FileValidationError(Exception):
    """Raised when an uploaded or ingested file exceeds policy limits."""


def validate_upload_bytes(file_name: str, size_bytes: int) -> None:
    max_upload = int(settings.MAX_UPLOAD_FILE_BYTES)
    if size_bytes > max_upload:
        mb = max_upload // (1024 * 1024)
        raise FileValidationError(
            f"File exceeds maximum upload size ({mb} MB). "
            f"Use Parquet or CSV, or split the dataset."
        )

    ext = file_name.rsplit(".", 1)[-1].lower()
    if ext in ("xlsx", "xls"):
        validate_excel_bytes(file_name, size_bytes)


def validate_excel_bytes(file_name: str, size_bytes: int) -> None:
    max_excel = int(settings.MAX_EXCEL_FILE_BYTES)
    if size_bytes <= max_excel:
        return
    mb = max_excel // (1024 * 1024)
    raise FileValidationError(
        f"Excel file '{file_name}' is too large ({size_bytes // (1024 * 1024)} MB). "
        f"Maximum for .xlsx/.xls is {mb} MB. "
        "Export to Parquet or CSV for large datasets."
    )
