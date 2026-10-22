import asyncio
import pytest

from app.services.python_sandbox import (
    FakeSandboxRunner, PythonSandboxError, UnavailableSandboxRunner,
    approval_id_for, validate_python_code, validate_result_manifest,
)


def test_static_validator_allows_pinned_analysis_packages():
    result = validate_python_code(
        "import pandas as pd\nimport numpy as np\nresult = pd.Series([1, 2]).mean()",
        ["pandas", "numpy"],
    )
    assert result["valid"] is True
    assert result["packages"]["pandas"]
    assert len(result["code_hash"]) == 64


@pytest.mark.parametrize("code,error", [
    ("open('/etc/passwd').read()", "PYTHON_CALL_NOT_ALLOWED:open"),
    ("import os\nos.getenv('SECRET')", "PYTHON_IMPORT_NOT_ALLOWED:os"),
    ("import subprocess", "PYTHON_IMPORT_NOT_ALLOWED:subprocess"),
    ("import socket", "PYTHON_IMPORT_NOT_ALLOWED:socket"),
    ("eval('1+1')", "PYTHON_CALL_NOT_ALLOWED:eval"),
    ("x.__class__", "PYTHON_DUNDER_ACCESS_NOT_ALLOWED"),
    ("__import__('math')", "PYTHON_CALL_NOT_ALLOWED:__import__"),
])
def test_static_validator_blocks_escape_surfaces(code, error):
    with pytest.raises(PythonSandboxError, match=error):
        validate_python_code(code, [])


def test_confirmation_is_bound_to_all_three_hashes():
    first = approval_id_for(code_hash="a" * 64, dataset_version_hash="b" * 64, package_manifest_hash="c" * 64)
    changed = approval_id_for(code_hash="d" * 64, dataset_version_hash="b" * 64, package_manifest_hash="c" * 64)
    assert first.startswith("pyapprove_")
    assert first != changed


def test_result_manifest_rejects_html_and_oversized_tables():
    with pytest.raises(PythonSandboxError, match="OUTPUT_TYPE_NOT_ALLOWED"):
        validate_result_manifest({"outputs": [{"kind": "html", "content_type": "text/html"}]})
    with pytest.raises(PythonSandboxError, match="TABLE_ROW_LIMIT"):
        validate_result_manifest({"outputs": [{"kind": "table_json", "rows": [{}] * 101}]})


def test_unavailable_runner_has_no_local_fallback_and_fake_never_executes():
    async def scenario():
        with pytest.raises(PythonSandboxError, match="PYTHON_SANDBOX_UNAVAILABLE"):
            await UnavailableSandboxRunner().run({"code": "result = 1"})
        fake = FakeSandboxRunner({"outputs": [], "findings": [{"value": 1}]})
        result = await fake.run({"code": "raise RuntimeError('must not execute')"})
        assert result["findings"] == [{"value": 1}]
        assert len(fake.manifests) == 1
    asyncio.run(scenario())
