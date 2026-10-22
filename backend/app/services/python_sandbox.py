"""Validated Python-analysis jobs executed only by an external sandbox runner.

There is intentionally no local/subprocess fallback. Development and tests may
inject ``FakeSandboxRunner``; production without a configured runner fails with
``PYTHON_SANDBOX_UNAVAILABLE``.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Protocol
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.services.dataset_loader import load_handle_from_storage


class PythonSandboxError(RuntimeError):
    pass


ALLOWED_PACKAGES: Dict[str, str] = {
    "pandas": "2.3.3",
    "numpy": "2.2.6",
    "scipy": "1.15.3",
    "statsmodels": "0.14.5",
    "sklearn": "1.7.2",
    "matplotlib": "3.10.7",
    "seaborn": "0.13.2",
    "duckdb": "1.4.1",
}
ALLOWED_STDLIB = frozenset({
    "collections", "datetime", "decimal", "fractions", "functools", "itertools",
    "json", "math", "operator", "random", "statistics", "typing",
})
BLOCKED_CALLS = frozenset({
    "eval", "exec", "compile", "open", "__import__", "breakpoint", "input",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
})
BLOCKED_ROOTS = frozenset({
    "os", "sys", "subprocess", "socket", "http", "urllib", "requests", "httpx",
    "ctypes", "pickle", "shelve", "marshal", "pathlib", "multiprocessing",
    "threading", "asyncio", "resource", "signal", "importlib", "builtins",
})
OUTPUT_KINDS = frozenset({"findings_json", "table_json", "png", "svg"})


@dataclass(frozen=True)
class SandboxLimits:
    cpu: int = 2
    memory_mb: int = 2_048
    pids: int = 64
    runtime_seconds: int = 60
    input_bytes: int = 524_288_000
    output_bytes: int = 10_485_760

    def to_dict(self) -> Dict[str, int]:
        return {
            "cpu": self.cpu,
            "memory_mb": self.memory_mb,
            "pids": self.pids,
            "runtime_seconds": self.runtime_seconds,
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
        }


class SandboxRunner(Protocol):
    async def run(self, manifest: Dict[str, Any]) -> Dict[str, Any]: ...
    async def cancel(self, job_id: str) -> None: ...


class UnavailableSandboxRunner:
    async def run(self, _manifest: Dict[str, Any]) -> Dict[str, Any]:
        raise PythonSandboxError("PYTHON_SANDBOX_UNAVAILABLE")

    async def cancel(self, _job_id: str) -> None:
        raise PythonSandboxError("PYTHON_SANDBOX_UNAVAILABLE")


class HttpSandboxRunner:
    """Adapter for an internal OCI/gVisor runner service; never runs user code here."""

    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def run(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        timeout = float(manifest.get("limits", {}).get("runtime_seconds", 60)) + 15
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/jobs/run", json=manifest, headers=self._headers()
            )
        if response.status_code >= 400:
            raise PythonSandboxError(f"PYTHON_SANDBOX_RUNNER_ERROR:{response.status_code}")
        return validate_result_manifest(response.json())

    async def cancel(self, job_id: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.base_url}/v1/jobs/{job_id}/cancel", headers=self._headers()
            )
        if response.status_code not in {200, 202, 204, 404}:
            raise PythonSandboxError(f"PYTHON_SANDBOX_CANCEL_ERROR:{response.status_code}")


class FakeSandboxRunner:
    """Contract-test runner. It returns fixtures and never evaluates code."""

    def __init__(self, result: Optional[Dict[str, Any]] = None) -> None:
        self.result = result or {"outputs": [], "findings": [], "warnings": []}
        self.manifests: list[Dict[str, Any]] = []
        self.cancelled: list[str] = []

    async def run(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        self.manifests.append(manifest)
        return validate_result_manifest(self.result)

    async def cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)


def get_sandbox_runner() -> SandboxRunner:
    if not settings.PYTHON_SANDBOX_ENABLED or not settings.PYTHON_SANDBOX_RUNNER_URL:
        return UnavailableSandboxRunner()
    return HttpSandboxRunner(
        settings.PYTHON_SANDBOX_RUNNER_URL,
        settings.PYTHON_SANDBOX_RUNNER_TOKEN,
    )


def _root_name(node: ast.AST) -> Optional[str]:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def validate_python_code(code: str, packages: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    source = str(code or "")
    if not source.strip() or len(source.encode("utf-8")) > 100_000:
        raise PythonSandboxError("PYTHON_CODE_REQUIRED_OR_TOO_LARGE")
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise PythonSandboxError(f"PYTHON_SYNTAX_ERROR:{exc.lineno}:{exc.offset}") from exc

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                root = name.split(".", 1)[0]
                if root in BLOCKED_ROOTS or root not in ALLOWED_STDLIB | set(ALLOWED_PACKAGES):
                    raise PythonSandboxError(f"PYTHON_IMPORT_NOT_ALLOWED:{root}")
                imports.add(root)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                raise PythonSandboxError(f"PYTHON_CALL_NOT_ALLOWED:{node.func.id}")
            root = _root_name(node.func)
            if root in BLOCKED_ROOTS:
                raise PythonSandboxError(f"PYTHON_API_NOT_ALLOWED:{root}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or "__" in node.attr:
                raise PythonSandboxError("PYTHON_DUNDER_ACCESS_NOT_ALLOWED")
            root = _root_name(node)
            if root in BLOCKED_ROOTS:
                raise PythonSandboxError(f"PYTHON_API_NOT_ALLOWED:{root}")
        if isinstance(node, ast.Name) and "__" in node.id:
            raise PythonSandboxError("PYTHON_DUNDER_ACCESS_NOT_ALLOWED")

    requested = sorted(set(packages or imports) - ALLOWED_STDLIB)
    unknown = [package for package in requested if package not in ALLOWED_PACKAGES]
    if unknown:
        raise PythonSandboxError(f"PYTHON_PACKAGE_NOT_ALLOWED:{','.join(unknown)}")
    missing = [package for package in imports if package in ALLOWED_PACKAGES and package not in requested]
    if missing:
        raise PythonSandboxError(f"PYTHON_PACKAGE_MANIFEST_INCOMPLETE:{','.join(sorted(missing))}")
    manifest = {package: ALLOWED_PACKAGES[package] for package in requested}
    code_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    package_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "valid": True,
        "code_hash": code_hash,
        "packages": manifest,
        "package_manifest_hash": package_hash,
        "imports": sorted(imports),
        "blocked_capabilities": ["filesystem", "network", "process", "dynamic_code", "secrets"],
    }


def approval_id_for(*, code_hash: str, dataset_version_hash: str, package_manifest_hash: str) -> str:
    material = f"{code_hash}:{dataset_version_hash}:{package_manifest_hash}"
    return "pyapprove_" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def validate_result_manifest(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        raise PythonSandboxError("PYTHON_INVALID_RESULT_MANIFEST")
    outputs = result.get("outputs") or []
    findings = result.get("findings") or []
    if not isinstance(outputs, list) or not isinstance(findings, list):
        raise PythonSandboxError("PYTHON_INVALID_RESULT_MANIFEST")
    if len(findings) > 100 or len(outputs) > 20:
        raise PythonSandboxError("PYTHON_OUTPUT_LIMIT_EXCEEDED")
    for output in outputs:
        if not isinstance(output, dict) or output.get("kind") not in OUTPUT_KINDS:
            raise PythonSandboxError("PYTHON_OUTPUT_TYPE_NOT_ALLOWED")
        if output.get("kind") == "table_json" and len(output.get("rows") or []) > 100:
            raise PythonSandboxError("PYTHON_TABLE_ROW_LIMIT_EXCEEDED")
        content_type = str(output.get("content_type") or "").lower()
        if "html" in content_type or "javascript" in content_type or "pickle" in content_type:
            raise PythonSandboxError("PYTHON_OUTPUT_TYPE_NOT_ALLOWED")
    return {
        "outputs": outputs,
        "findings": findings,
        "warnings": list(result.get("warnings") or [])[:50],
        "execution_time_ms": int(result.get("execution_time_ms") or 0),
        "package_versions": dict(result.get("package_versions") or {}),
    }


def propose_python_analysis(
    *, user_id: str, conversation_id: Optional[str], dataset_key: str,
    dataset_version_hash: str, code: str, packages: Iterable[str],
    expected_outputs: Iterable[str], limits: Optional[SandboxLimits] = None,
    client: Any = None,
) -> Dict[str, Any]:
    validation = validate_python_code(code, packages)
    limits = limits or SandboxLimits()
    approval_id = approval_id_for(
        code_hash=validation["code_hash"], dataset_version_hash=dataset_version_hash,
        package_manifest_hash=validation["package_manifest_hash"],
    )
    job_id = str(uuid.uuid4())
    row = {
        "id": job_id, "user_id": user_id, "conversation_id": conversation_id,
        "dataset_key": dataset_key, "dataset_version_hash": dataset_version_hash,
        "code": code, "code_hash": validation["code_hash"],
        "package_manifest": validation["packages"],
        "package_manifest_hash": validation["package_manifest_hash"],
        "approval_id": approval_id, "expected_outputs": list(expected_outputs)[:10],
        "resource_limits": limits.to_dict(), "status": "awaiting_confirmation",
    }
    response = (client or get_supabase_client()).table("python_analysis_jobs").insert(row).execute()
    stored = (response.data or [row])[0]
    return {
        "job_id": job_id, "status": "awaiting_confirmation", "approval_id": approval_id,
        "code": code, "code_hash": validation["code_hash"], "packages": validation["packages"],
        "dataset_key": dataset_key, "dataset_version_hash": dataset_version_hash,
        "expected_outputs": row["expected_outputs"], "limits": limits.to_dict(),
        "created_at": stored.get("created_at"),
    }


def get_python_job(user_id: str, job_id: str, *, client: Any = None) -> Dict[str, Any]:
    response = (
        (client or get_supabase_client()).table("python_analysis_jobs")
        .select("id,user_id,conversation_id,dataset_key,dataset_version_hash,code,code_hash,package_manifest,package_manifest_hash,approval_id,expected_outputs,resource_limits,status,result_manifest,error_code,created_at,started_at,completed_at,expires_at")
        .eq("id", job_id).eq("user_id", user_id).limit(1).execute()
    )
    if not response.data:
        raise PythonSandboxError("PYTHON_JOB_NOT_FOUND")
    return response.data[0]


def confirm_python_analysis(user_id: str, job_id: str, approval_id: str, *, client: Any = None) -> Dict[str, Any]:
    db = client or get_supabase_client()
    job = get_python_job(user_id, job_id, client=db)
    expected = approval_id_for(
        code_hash=job["code_hash"], dataset_version_hash=job["dataset_version_hash"],
        package_manifest_hash=job["package_manifest_hash"],
    )
    if approval_id != expected or approval_id != job.get("approval_id"):
        raise PythonSandboxError("PYTHON_CONFIRMATION_HASH_MISMATCH")
    if job["status"] not in {"awaiting_confirmation", "queued"}:
        raise PythonSandboxError(f"PYTHON_JOB_NOT_CONFIRMABLE:{job['status']}")
    if job["status"] == "awaiting_confirmation":
        response = (
            db.table("python_analysis_jobs").update({
                "status": "queued", "confirmed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", job_id).eq("user_id", user_id)
            .eq("status", "awaiting_confirmation").execute()
        )
        if not response.data:
            raise PythonSandboxError("PYTHON_JOB_CONFIRMATION_CONFLICT")
    return {"job_id": job_id, "status": "queued"}


async def cancel_python_analysis(user_id: str, job_id: str, *, client: Any = None, runner: Optional[SandboxRunner] = None) -> Dict[str, Any]:
    db = client or get_supabase_client()
    job = get_python_job(user_id, job_id, client=db)
    if job["status"] in {"completed", "failed", "cancelled"}:
        return {"job_id": job_id, "status": job["status"]}
    if job["status"] == "running":
        await (runner or get_sandbox_runner()).cancel(job_id)
    response = (
        db.table("python_analysis_jobs").update({
            "status": "cancelled", "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", job_id).eq("user_id", user_id)
        .in_("status", ["awaiting_confirmation", "queued", "running"]).execute()
    )
    return {"job_id": job_id, "status": "cancelled" if response.data else job["status"]}


def _stage_dataset(job: Dict[str, Any]) -> tuple[Path, Path]:
    root = Path(settings.PYTHON_SANDBOX_STAGE_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    job_dir = (root / str(job["id"])).resolve()
    if root not in job_dir.parents:
        raise PythonSandboxError("PYTHON_INVALID_STAGE_PATH")
    job_dir.mkdir(mode=0o700)
    input_path = job_dir / "input.parquet"
    output_path = job_dir / "output"
    output_path.mkdir(mode=0o700)
    handle = load_handle_from_storage(str(job["user_id"]), str(job["dataset_key"]))
    if handle is None:
        raise PythonSandboxError("PYTHON_DATASET_NOT_FOUND")
    export = type(handle).for_sql_execution(handle)
    escaped = str(input_path).replace("'", "''")
    export._con.execute(
        f"COPY (SELECT * FROM df) TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    if input_path.stat().st_size > int(settings.PYTHON_SANDBOX_MAX_INPUT_BYTES):
        raise PythonSandboxError("PYTHON_INPUT_LIMIT_EXCEEDED")
    os.chmod(input_path, 0o400)
    return input_path, output_path


async def run_next_python_job(*, client: Any = None, runner: Optional[SandboxRunner] = None) -> Optional[Dict[str, Any]]:
    """Claim and execute one queued job. Safe for multiple workers via status CAS."""
    db = client or get_supabase_client()
    queued = (
        db.table("python_analysis_jobs").select("*").eq("status", "queued")
        .order("created_at").limit(1).execute()
    )
    if not queued.data:
        return None
    job = queued.data[0]
    now = datetime.now(timezone.utc).isoformat()
    claimed = (
        db.table("python_analysis_jobs").update({"status": "running", "started_at": now})
        .eq("id", job["id"]).eq("status", "queued").execute()
    )
    if not claimed.data:
        return None
    job = {**job, **claimed.data[0]}
    stage_dir: Optional[Path] = None
    try:
        validation = validate_python_code(job["code"], job.get("package_manifest", {}).keys())
        expected_approval = approval_id_for(
            code_hash=validation["code_hash"],
            dataset_version_hash=job["dataset_version_hash"],
            package_manifest_hash=validation["package_manifest_hash"],
        )
        if (
            validation["code_hash"] != job["code_hash"]
            or validation["package_manifest_hash"] != job["package_manifest_hash"]
            or expected_approval != job["approval_id"]
        ):
            raise PythonSandboxError("PYTHON_JOB_HASH_MISMATCH")
        input_path, output_path = await asyncio.to_thread(_stage_dataset, job)
        stage_dir = input_path.parent
        manifest = {
            "job_id": job["id"], "code": job["code"], "code_hash": job["code_hash"],
            "packages": job["package_manifest"],
            "dataset": {"path": str(input_path), "format": "parquet", "read_only": True,
                        "version_hash": job["dataset_version_hash"]},
            "output": {"path": str(output_path), "allowed": sorted(OUTPUT_KINDS)},
            "limits": job["resource_limits"],
            "isolation": {"network": "none", "root_filesystem": "read_only",
                          "user": "non_root", "drop_capabilities": "all"},
        }
        result = await (runner or get_sandbox_runner()).run(manifest)
        result["code_hash"] = job["code_hash"]
        result["input_hash"] = job["dataset_version_hash"]
        result["package_manifest_hash"] = job["package_manifest_hash"]
        grounded_findings = []
        for index, finding in enumerate(result.get("findings") or []):
            if not isinstance(finding, dict):
                raise PythonSandboxError("PYTHON_INVALID_FINDING")
            grounded_findings.append({
                **finding,
                "id": str(finding.get("id") or f"python_{job['id']}_{index}"),
                "provenance": {
                    **(finding.get("provenance") if isinstance(finding.get("provenance"), dict) else {}),
                    "engine": "external_python_sandbox",
                    "code_hash": job["code_hash"],
                    "input_hash": job["dataset_version_hash"],
                    "package_manifest_hash": job["package_manifest_hash"],
                    "server_verified": True,
                },
            })
        result["findings"] = grounded_findings
        response = (
            db.table("python_analysis_jobs").update({
                "status": "completed", "result_manifest": result,
                "completed_at": datetime.now(timezone.utc).isoformat(), "error_code": None,
            }).eq("id", job["id"]).eq("status", "running").execute()
        )
        return (response.data or [{"id": job["id"], "status": "completed"}])[0]
    except Exception as exc:
        code = str(exc)[:160] if isinstance(exc, PythonSandboxError) else type(exc).__name__
        response = (
            db.table("python_analysis_jobs").update({
                "status": "failed", "error_code": code,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", job["id"]).eq("status", "running").execute()
        )
        return (response.data or [{"id": job["id"], "status": "failed", "error_code": code}])[0]
    finally:
        if stage_dir is not None and stage_dir.exists():
            os.chmod(stage_dir / "input.parquet", 0o600)
            shutil.rmtree(stage_dir, ignore_errors=True)
