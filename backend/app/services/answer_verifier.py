"""Lightweight evidence checks for generated chat answers."""
from __future__ import annotations

import re
import math
from typing import Any, Dict, Iterable, List, Optional

_URL_RE = re.compile(r"https?://[^\s<>)\]}]+", re.IGNORECASE)
_NUMBER_RE = re.compile(
    r"(?<![\w])(?:[$€£฿¥]\s*)?-?\d[\d,]*(?:\.\d+)?\s*"
    r"(?:%|percent|บาท|ดอลลาร์|ล้าน|พัน|แสน|ร้อย|\bk\b|\bm\b|\bbn\b|\bmillion\b|\bbillion\b)?",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(?:19|20)\d{2}[-/]\d{1,2}(?:[-/]\d{1,2})?\b")
_THAI_YEAR_RE = re.compile(r"^\s*(?:19|20)\d{2}\s*$")
_APPROX_PREFIX_RE = re.compile(
    r"(?:ประมาณ|ราว|~|≈|about|around|approximately|roughly)\s*$",
    re.IGNORECASE,
)


def _normalise_url(url: str) -> str:
    return (url or "").rstrip(".,;:!?/").lower()


def _source_text(sources: Iterable[Dict[str, Any]]) -> str:
    return " ".join(
        f"{source.get('title', '')} {source.get('snippet', '')}"
        for source in sources
    ).lower()


def _number_key(value: str) -> str:
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
    return match.group(0).replace(",", "") if match else ""


def _claim_number(value: str) -> float | None:
    key = _number_key(value)
    if not key:
        return None
    try:
        number = float(key)
    except ValueError:
        return None
    lower = value.lower()
    if "ล้าน" in lower:
        number *= 1_000_000
    elif "แสน" in lower:
        number *= 100_000
    elif "พัน" in lower or "ร้อย" in lower:
        number *= 1_000
    elif re.search(r"\b(?:bn|billion)\b", lower):
        number *= 1_000_000_000
    elif re.search(r"\b(?:m|million)\b", lower):
        number *= 1_000_000
    elif re.search(r"\b(?:k|thousand)\b", lower):
        number *= 1_000
    return number


def _format_variants(value: float, unit: str = "") -> set[str]:
    variants: set[str] = set()
    if not math.isfinite(value):
        return variants
    rounded = round(value, 6)
    variants.add(f"{rounded:.6f}".rstrip("0").rstrip("."))
    if abs(value - round(value)) < 0.0005:
        variants.add(str(int(round(value))))
    variants.add(f"{round(value):,}")
    variants.add(f"{round(value, 1):,}")
    variants.add(f"{round(value, 2):,}")
    if unit == "%" or abs(value) <= 100:
        variants.add(f"{round(value, 1)}%")
        variants.add(f"{round(value, 2)}%")
    return {item for item in variants if item}


def _matches_finding(claim: str, findings: List[Dict[str, Any]]) -> bool:
    number = _claim_number(claim)
    if number is None:
        return False
    claim_key = _number_key(claim)
    for finding in findings:
        raw = finding.get("value")
        if not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
            continue
        expected = float(raw)
        unit = str(finding.get("unit") or "")
        is_percent = "%" in claim or unit == "%"
        tolerance = (
            max(0.15, abs(expected) * 0.015)
            if is_percent
            else max(0.01, abs(expected) * 0.006)
        )
        if _APPROX_PREFIX_RE.search(claim):
            tolerance *= 2.5
        if abs(number - expected) <= tolerance:
            return True
        if claim_key in _format_variants(expected, unit):
            return True
    return False


def _is_structural_number(text: str, start: int, end: int, claim: str) -> bool:
    stripped = claim.strip().lower()
    if _THAI_YEAR_RE.match(stripped) or re.fullmatch(r"(?:19|20)\d{2}", _number_key(stripped)):
        return True
    before = text[max(0, start - 45):start].lower()
    after = text[end:min(len(text), end + 45)].lower()
    line_before = text[text.rfind("\n", 0, start) + 1:start]
    if re.fullmatch(r"\s*(?:[-*]\s*)?", line_before) and re.match(
        r"\d+[.)]\s", text[start:]
    ):
        return True
    if re.match(r"\d+[.)]\s*\S", text[start:]):
        return True
    if re.match(r"\d+\s*(?:ข้อ|steps?|items?|points?)\b", text[start:], re.IGNORECASE):
        return True
    if before.endswith("[") and after.startswith("]"):
        return True
    before_end = before.rstrip()
    after_start = after.lstrip()
    if re.search(r"\btop\s*$", before_end):
        return True
    if re.search(
        r"(?:ข้อที่|ลำดับที่|อันดับที่|ครั้งที่|หัวข้อที่|รายการที่|ตารางที่|"
        r"figure|section|page|step|option|item|source|finding)\s*$",
        before_end,
        re.IGNORECASE,
    ):
        return True
    if re.match(
        r"(?:\w+\s+){0,2}(?:step|steps|recommendation|recommendations|option|options|"
        r"point|points|item|items|source|sources|finding|findings|reason|reasons|"
        r"table|figure|page|section|days?|weeks?|months?|quarters?|years?)\b",
        after_start,
    ):
        return True
    if re.match(
        r"(?:ข้อ|รายการ|ขั้นตอน|วัน|สัปดาห์|เดือน|ไตรมาส|ปี)\b",
        after_start,
    ):
        return True
    if re.match(
        r"(?:ข้อเสนอ|คำแนะนำ|ขั้นตอน|ตัวเลือก|ประเด็น|แหล่งข้อมูล|ข้อค้นพบ|หัวข้อ|"
        r"รายการ|วัน|สัปดาห์|เดือน|ไตรมาส|ปี)",
        after_start,
    ):
        return True
    if re.search(r"(?:within|in|next|following|ภายใน|ภาย|ภายหลัง)\s*$", before_end) and re.match(
        r"(?:day|week|month|quarter|year|วัน|สัปดาห์|เดือน|ไตรมาส|ปี)s?\b",
        after_start,
    ):
        return True
    if "95" in stripped and (
        re.search(r"(?:confidence|ci)\s*$", before_end)
        or re.match(r"(?:confidence|ci)\b", after_start)
    ):
        return True
    if re.search(r"\b(?:gpt|gemini|claude|model|version)\s*[-:]?\s*$", before_end):
        return True
    if re.search(r"(?:#|no\.|number)\s*$", before_end):
        return True
    return False


def _extract_numeric_claims(text: str) -> tuple[List[str], List[str]]:
    scrubbed = _URL_RE.sub(lambda match: " " * len(match.group(0)), text)
    scrubbed = _DATE_RE.sub(lambda match: " " * len(match.group(0)), scrubbed)
    quantitative: List[str] = []
    structural: List[str] = []
    for match in _NUMBER_RE.finditer(scrubbed):
        claim = match.group(0)
        target = (
            structural
            if _is_structural_number(scrubbed, match.start(), match.end(), claim)
            else quantitative
        )
        target.append(claim)
    return quantitative, structural


def needs_numeric_correction(verification: Dict[str, Any]) -> bool:
    """True when dataset numbers in narration do not match verified findings."""
    if not verification:
        return False
    unmatched = verification.get("unmatched_dataset_numeric_claims") or []
    return bool(unmatched) and verification.get("finding_count", 0) > 0


def build_correction_context(
    draft: str,
    structured_findings: List[Dict[str, Any]],
    verification: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    unmatched = verification.get("unmatched_dataset_numeric_claims") or []
    if not unmatched or not structured_findings:
        return None
    allowed_lines = []
    for finding in structured_findings[:24]:
        value = finding.get("value")
        if value is None:
            continue
        unit = finding.get("unit") or ""
        metric = finding.get("metric") or finding.get("type") or "metric"
        allowed_lines.append(f"- {metric}: {value} {unit}".strip())
    allowed = "\n".join(allowed_lines) or "- No numeric findings available."
    unmatched_text = ", ".join(unmatched[:10])
    system = (
        "You fix analytical narration after automated numeric verification failed.\n"
        "Rules:\n"
        "1. Keep the same language as the draft.\n"
        "2. Replace ONLY mismatched numeric claims using the allowed values list.\n"
        "3. Do not introduce any number that is not listed under Allowed values.\n"
        "4. Do not repeat a findings table or add a new table.\n"
        "5. Preserve interpretation and recommendations; remove unsupported numeric claims if needed.\n"
        "6. Return only the corrected narration prose."
    )
    user = (
        f"Draft narration:\n{draft.strip()}\n\n"
        f"Allowed values (copy exactly when citing numbers):\n{allowed}\n\n"
        f"Claims that failed verification and must be fixed or removed:\n{unmatched_text}\n"
    )
    return {"system": system, "user": user}


def verify_answer(
    answer: str,
    *,
    web_sources: List[Dict[str, Any]] | None = None,
    has_dataset_metrics: bool = False,
    structured_findings: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Return a transparent verification summary without inventing certainty."""
    text = answer or ""
    sources = web_sources or []
    source_urls = {
        _normalise_url(source.get("url", ""))
        for source in sources
        if source.get("url")
    }
    cited_urls = {_normalise_url(url) for url in _URL_RE.findall(text)}
    cited_known = cited_urls & source_urls
    unknown_urls = cited_urls - source_urls
    numeric_claims, ignored_structural_claims = _extract_numeric_claims(text)
    findings = structured_findings or []
    evidence_scope_active = bool(sources or has_dataset_metrics or findings)
    evidence_text = _source_text(sources).replace(",", "")
    supported_numeric_claims = [
        claim for claim in numeric_claims
        if _number_key(claim) and _number_key(claim) in evidence_text
    ]
    dataset_numeric_claims = (
        [
            claim for claim in numeric_claims
            if _claim_number(claim) is not None
        ]
        if evidence_scope_active
        else []
    )
    matched_dataset_claims = [
        claim for claim in dataset_numeric_claims
        if _matches_finding(claim, findings)
    ]
    unmatched_dataset_claims = [
        claim for claim in dataset_numeric_claims
        if claim not in matched_dataset_claims
        and claim not in supported_numeric_claims
    ]

    warnings: List[str] = []
    if sources and not cited_known:
        warnings.append("External context was used but no fetched source URL was cited.")
    if unknown_urls:
        warnings.append("The answer contains URLs that were not in the fetched evidence.")
    if sources and numeric_claims and not has_dataset_metrics:
        unsupported_count = len(numeric_claims) - len(supported_numeric_claims)
        if unsupported_count:
            warnings.append(
                f"{unsupported_count} numeric claim(s) were not found in fetched source snippets."
            )
    if findings and unmatched_dataset_claims:
        warnings.append(
            f"{len(unmatched_dataset_claims)} numeric claim(s) do not match verified dataset findings."
        )

    if warnings:
        status = "needs_review"
    elif sources or has_dataset_metrics:
        status = "grounded"
    else:
        status = "not_required"

    evidence_count = len(sources) + (1 if has_dataset_metrics else 0)
    coverage = 1.0
    if sources:
        coverage = len(cited_known) / max(1, min(len(sources), 3))
    return {
        "status": status,
        "evidence_scope_active": evidence_scope_active,
        "evidence_count": evidence_count,
        "cited_source_count": len(cited_known),
        "numeric_claim_count": len(numeric_claims),
        "supported_numeric_claim_count": len(supported_numeric_claims),
        "dataset_numeric_claim_count": len(dataset_numeric_claims),
        "matched_dataset_numeric_claim_count": len(matched_dataset_claims),
        "unmatched_dataset_numeric_claims": unmatched_dataset_claims[:10],
        "ignored_structural_numeric_claims": ignored_structural_claims[:20],
        "finding_count": len(findings),
        "numeric_correction_required": needs_numeric_correction(
            {
                "unmatched_dataset_numeric_claims": unmatched_dataset_claims,
                "finding_count": len(findings),
            }
        ),
        "citation_coverage": round(min(1.0, coverage), 2),
        "warnings": warnings,
    }
