"""One-shot narration correction when numeric verification fails."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.answer_verifier import (
    build_correction_context,
    needs_numeric_correction,
    verify_answer,
)


async def retry_narration_for_numeric_mismatch(
    draft: str,
    *,
    structured_findings: List[Dict[str, Any]],
    verification: Dict[str, Any],
    model: str,
    chat_completion_fn: Callable[..., Any],
    response_mode: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Return corrected narration and metadata. Keeps draft when correction is unnecessary."""
    meta: Dict[str, Any] = {"attempted": False, "applied": False}
    if not needs_numeric_correction(verification):
        return draft, meta

    meta["attempted"] = True
    context = build_correction_context(draft, structured_findings, verification)
    if not context:
        return draft, meta

    temperature = min(0.2, float((response_mode or {}).get("temperature", 0.35)))
    max_tokens = min(900, int((response_mode or {}).get("max_output_tokens", 900)))

    try:
        response = await chat_completion_fn(
            model=model,
            messages=[
                {"role": "system", "content": context["system"]},
                {"role": "user", "content": context["user"]},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        corrected = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        meta["error"] = str(exc)
        return draft, meta

    if not corrected or corrected == draft.strip():
        return draft, meta

    recheck = verify_answer(
        corrected,
        has_dataset_metrics=True,
        structured_findings=structured_findings,
    )
    meta["applied"] = True
    meta["verification_before"] = verification.get("status")
    meta["verification_after"] = recheck.get("status")
    meta["unmatched_before"] = verification.get("unmatched_dataset_numeric_claims") or []
    meta["unmatched_after"] = recheck.get("unmatched_dataset_numeric_claims") or []
    return corrected, meta
