import asyncio
import json
from types import SimpleNamespace

from app.schemas.chat import ChatRequest
from app.services.chat import stream_handler


def test_verification_failure_returns_review_status_without_raising(monkeypatch):
    def broken_verifier(*args, **kwargs):
        raise TypeError("unexpected verifier argument")

    monkeypatch.setattr(stream_handler, "verify_answer", broken_verifier)

    result = stream_handler._verify_answer_safely(
        "answer",
        web_sources=[],
        has_dataset_metrics=False,
    )

    assert result["status"] == "needs_review"
    assert result["warnings"]


def test_safe_verifier_passes_only_supported_inputs(monkeypatch):
    captured = {}

    def verifier(answer, *, web_sources, has_dataset_metrics):
        captured.update(
            answer=answer,
            web_sources=web_sources,
            has_dataset_metrics=has_dataset_metrics,
        )
        return {"status": "grounded"}

    monkeypatch.setattr(stream_handler, "verify_answer", verifier)

    result = stream_handler._verify_answer_safely(
        "verified answer",
        web_sources=[{"url": "https://example.com"}],
        has_dataset_metrics=True,
    )

    assert result == {"status": "grounded"}
    assert captured == {
        "answer": "verified answer",
        "web_sources": [{"url": "https://example.com"}],
        "has_dataset_metrics": True,
    }


def test_numeric_rewrite_preserves_render_chart_command():
    original = """Analysis draft.

```json
{"action":"render_chart","chart_type":"bar","config":{"title":"Revenue"},"data":[{"name":"A","value":10}]}
```"""

    result = stream_handler._preserve_system_commands(
        original,
        "Corrected final analysis.",
    )

    assert result.startswith("Corrected final analysis.")
    assert '"action":"render_chart"' in result


def test_system_command_is_not_duplicated_after_rewrite():
    command = """```json
{"action":"generate_report","destination":"visualization","title":"Report"}
```"""

    result = stream_handler._preserve_system_commands(
        f"Draft\n\n{command}",
        f"Corrected\n\n{command}",
    )

    assert result.count('"action":"generate_report"') == 1


def test_visualization_proposal_replaces_chat_chart_commands():
    draft = """Analysis

```json
{"action":"render_chart","chart_type":"bar","data":[{"name":"A","value":10}]}
```

Keep this ordinary JSON:
```json
{"status":"ok"}
```"""
    proposal = {
        "action": "propose_visualization",
        "title": "Sales dashboard",
        "filters": [],
        "kpis": [],
        "widgets": [],
    }

    cleaned = stream_handler._remove_system_commands(
        draft,
        {"render_chart", "generate_report", "propose_visualization"},
    )
    result = f"{cleaned}\n\n{stream_handler._proposal_block(proposal)}"

    assert '"action":"render_chart"' not in result
    assert '"status":"ok"' in result
    assert '"action": "propose_visualization"' in result


def test_stream_usage_is_accumulated_across_continuations():
    first = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=200,
        total_tokens=300,
    )
    second = SimpleNamespace(
        prompt_tokens=250,
        completion_tokens=80,
        total_tokens=330,
    )

    usage = stream_handler._merge_usage(None, first)
    usage = stream_handler._merge_usage(usage, second)

    assert usage == {
        "prompt_tokens": 350,
        "completion_tokens": 280,
        "total_tokens": 630,
    }


def test_length_continuation_keeps_original_context_and_partial_answer():
    original = [{"role": "system", "content": "system rules"}]

    messages = stream_handler._continuation_messages(
        original,
        "คำตอบที่ถูกตัดกลางประโยค",
    )

    assert messages[0] == original[0]
    assert messages[-2] == {
        "role": "assistant",
        "content": "คำตอบที่ถูกตัดกลางประโยค",
    }
    assert "render_chart" in messages[-1]["content"]
    assert "without repeating" in messages[-1]["content"]


def test_stream_preserves_numeric_general_chat_without_tool_evidence(monkeypatch):
    class FakeContext:
        async def prepare(self, _request, on_status=None):
            return (
                "test-model",
                [{"role": "system", "content": "answer"}],
                None,
                {
                    "response_mode": {"max_output_tokens": 128, "temperature": 0.1},
                    "web_sources": [],
                    "structured_findings": [],
                    "has_dataset_metrics": False,
                    "tool_execution": {
                        "policy": "tool_first_compute_only",
                        "satisfied": True,
                        "calls": [],
                    },
                },
            )

    class FakeLlm:
        async def safe_chat_completion_stream(self, **kwargs):
            yield SimpleNamespace(
                model="test-model",
                usage=None,
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="ยอดขายเพิ่มขึ้น 999%"),
                        finish_reason="stop",
                    )
                ],
            )

    monkeypatch.setattr(stream_handler, "save_chat_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        stream_handler,
        "record_chat_quality_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(stream_handler, "log_pipeline_event", lambda *args, **kwargs: None)

    async def run():
        handler = stream_handler.ChatStreamHandler(FakeLlm(), FakeContext())
        request = ChatRequest(
            messages=[{"role": "user", "content": "ช่วยยกตัวอย่างงบประมาณ"}],
            user_id="user-1",
        )
        return [
            json.loads(raw.removeprefix("data: ").strip())
            async for raw in handler.stream_chat_completion(request)
        ]

    events = asyncio.run(run())
    tokens = "".join(event.get("content", "") for event in events if event["type"] == "token")
    done = next(event for event in events if event["type"] == "done")

    assert "999" in tokens
    assert "999" in done["message"]["content"]
    assert "ระบบตัดข้อความที่มีตัวเลข" not in done["message"]["content"]
    assert done["verification"]["tool_grounding_gate"]["applied"] is False
    assert done["verification"]["tool_grounding_gate"]["reason"] == "no_tool_evidence"


def test_required_tool_failure_skips_llm_generation(monkeypatch):
    class FakeContext:
        async def prepare(self, _request, on_status=None):
            return (
                "test-model",
                [{"role": "system", "content": "must not run"}],
                None,
                {
                    "response_mode": {},
                    "blocked_answer": "tool failed; no model calculation",
                    "tool_execution": {
                        "policy": "tool_first_compute_only",
                        "satisfied": False,
                        "missing": ["safe_calculator"],
                        "calls": [],
                    },
                },
            )

    class FakeLlm:
        async def safe_chat_completion_stream(self, **kwargs):
            raise AssertionError("LLM must not run after the required tool failed")
            yield

    async def run():
        handler = stream_handler.ChatStreamHandler(FakeLlm(), FakeContext())
        request = ChatRequest(
            messages=[{"role": "user", "content": "calculate this"}],
            user_id="user-1",
        )
        return [
            json.loads(raw.removeprefix("data: ").strip())
            async for raw in handler.stream_chat_completion(request)
        ]

    events = asyncio.run(run())
    done = next(event for event in events if event["type"] == "done")
    assert done["verification"]["status"] == "blocked"
    assert done["tool_execution"]["missing"] == ["safe_calculator"]


async def _run_stream_automatic_continuation_test(monkeypatch):
    class FakeContext:
        async def prepare(self, _request, on_status=None):
            return (
                "test-model",
                [{"role": "system", "content": "Return a complete report."}],
                None,
                {
                    "response_mode": {
                        "max_output_tokens": 4096,
                        "temperature": 0.4,
                    },
                    "web_sources": [],
                    "structured_findings": [],
                },
            )

    class FakeLlm:
        def __init__(self):
            self.calls = []

        async def safe_chat_completion_stream(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                yield SimpleNamespace(
                    model="test-model",
                    usage=None,
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="ส่วนแรก"),
                            finish_reason=None,
                        )
                    ],
                )
                yield SimpleNamespace(
                    model="test-model",
                    usage=SimpleNamespace(
                        prompt_tokens=100,
                        completion_tokens=4096,
                        total_tokens=4196,
                    ),
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=None),
                            finish_reason="length",
                        )
                    ],
                )
            else:
                yield SimpleNamespace(
                    model="test-model",
                    usage=None,
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="จนจบพร้อมกราฟ"),
                            finish_reason=None,
                        )
                    ],
                )
                yield SimpleNamespace(
                    model="test-model",
                    usage=SimpleNamespace(
                        prompt_tokens=180,
                        completion_tokens=120,
                        total_tokens=300,
                    ),
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=None),
                            finish_reason="stop",
                        )
                    ],
                )

    monkeypatch.setattr(stream_handler, "save_chat_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        stream_handler,
        "record_chat_quality_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(stream_handler, "log_pipeline_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        stream_handler,
        "_verify_answer_safely",
        lambda *args, **kwargs: {"status": "grounded"},
    )

    llm = FakeLlm()
    handler = stream_handler.ChatStreamHandler(llm, FakeContext())
    request = ChatRequest(
        messages=[{"role": "user", "content": "สร้างรายงานพร้อมกราฟ"}],
        user_id="00000000-0000-0000-0000-000000000001",
        tier="pro",
        model_mode="deep",
    )

    events = []
    async for raw in handler.stream_chat_completion(request):
        events.append(json.loads(raw.removeprefix("data: ").strip()))

    done = next(event for event in events if event["type"] == "done")
    assert done["message"]["content"] == "ส่วนแรกจนจบพร้อมกราฟ"
    assert done["finish_reason"] == "stop"
    assert done["generation_continuations"] == 1
    assert done["generation_truncated"] is False
    assert done["usage"] == {
        "prompt_tokens": 280,
        "completion_tokens": 4216,
        "total_tokens": 4496,
    }
    assert any(event.get("stage") == "continuing" for event in events)
    assert llm.calls[1]["messages"][-2]["content"] == "ส่วนแรก"


def test_stream_automatically_continues_when_provider_hits_length(monkeypatch):
    asyncio.run(_run_stream_automatic_continuation_test(monkeypatch))
