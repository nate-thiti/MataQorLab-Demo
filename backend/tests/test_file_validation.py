"""Tests for upload file validation."""
import pytest

from app.core.config import settings
from app.services.file_validation import FileValidationError, validate_excel_bytes, validate_upload_bytes


def test_excel_within_limit():
    validate_excel_bytes("report.xlsx", 1_000_000)


def test_excel_over_limit_rejected():
    with pytest.raises(FileValidationError, match="Parquet or CSV"):
        validate_excel_bytes("big.xlsx", int(settings.MAX_EXCEL_FILE_BYTES) + 1)


def test_upload_rejects_oversized_file():
    with pytest.raises(FileValidationError, match="maximum upload size"):
        validate_upload_bytes("data.csv", int(settings.MAX_UPLOAD_FILE_BYTES) + 1)
