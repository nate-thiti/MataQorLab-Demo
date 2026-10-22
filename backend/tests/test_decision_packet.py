from app.services.decision_packet import (
    apply_prove,
    can_mark_final,
    decision_brief,
    enrich_decision_insights,
    evaluate_staleness,
    normalize_decision_packet,
    prove_diff,
    set_insight_action,
    source_fingerprint,
    upsert_pin,
)


def test_pin_with_grounded_evidence_advances_lifecycle():
    packet = upsert_pin({}, {
        "title": "Revenue spike",
        "summary": "Branch A leads.",
        "source_message_id": "msg-1",
        "verification_status": "grounded",
        "claims": ["Branch A is #1"],
        "evidence": {"widget_id": "ranking", "value": 120},
        "formula": "SUM(revenue) GROUP BY branch",
    })
    assert packet["lifecycle"] == "proved"
    assert packet["pins"][0]["title"] == "Revenue spike"
    assert packet["pins"][0]["formula"] == "SUM(revenue) GROUP BY branch"


def test_staleness_when_fingerprint_changes():
    proved = apply_prove({}, fingerprint="fp-1", computed={"kpis": [{"kind": "sum", "label": "Revenue", "field": "revenue", "value": 100}]})
    stale = evaluate_staleness(proved, live_fingerprint="fp-2")
    assert stale["is_stale"] is True
    assert stale["lifecycle"] == "stale"


def test_reprove_produces_kpi_diff_and_clears_stale():
    first = apply_prove(
        {},
        fingerprint="fp-1",
        computed={"kpis": [{"kind": "sum", "label": "Revenue", "field": "revenue", "value": 100}]},
    )
    second = apply_prove(
        first,
        fingerprint="fp-2",
        computed={"kpis": [{"kind": "sum", "label": "Revenue", "field": "revenue", "value": 150}]},
    )
    assert second["lifecycle"] == "proved"
    assert second["is_stale"] is False
    assert second["last_prove"]["diff"][0]["before"] == 100
    assert second["last_prove"]["diff"][0]["after"] == 150
    assert second["last_prove"]["diff"][0]["change_pct"] == 50.0


def test_mark_final_blocked_when_stale_or_empty():
    ok, _ = can_mark_final({"lifecycle": "draft", "pins": []}, has_grounded_story=False)
    assert ok is False
    stale = evaluate_staleness(
        apply_prove({}, fingerprint="fp-1", computed={"kpis": []}),
        live_fingerprint="fp-2",
    )
    ok, reason = can_mark_final(stale)
    assert ok is False
    assert "Re-prove" in reason
    ok, _ = can_mark_final(
        upsert_pin({}, {"title": "A", "verification_status": "grounded", "evidence": {"x": 1}}),
    )
    assert ok is True


def test_insight_actions_and_brief():
    insights = [{"kind": "driver", "title": "Lead", "evidence": {"widget_id": "w1"}}]
    packet = set_insight_action({}, action_key="driver:w1", status="done", note="Checked", owner="Nate")
    enriched = enrich_decision_insights(insights, packet)
    assert enriched[0]["action"]["status"] == "done"
    brief = decision_brief(
        {"title": "Ops", "executive_summary": "Summary", "decision_packet": packet, "source_config": {"source_fingerprint": "fp"}},
        {"story": {"headline": "Headline", "evidence_ids": ["e1"]}, "decision_insights": insights, "source": {"source_fingerprint": "fp"}},
    )
    assert brief["title"] == "Ops"
    assert brief["headline"] == "Headline"
    assert brief["pin_count"] == 0
    assert brief["verified_evidence_count"] == 1


def test_source_fingerprint_prefers_immutable_fields():
    assert source_fingerprint({"cleaning_recipe": {"source_fingerprint": "abc"}}) == "abc"
    assert source_fingerprint({"file_name": "sales.csv"}) == "sales.csv"


def test_prove_diff_ignores_unchanged():
    assert prove_diff(
        [{"kind": "sum", "label": "Revenue", "field": "revenue", "value": 10}],
        [{"kind": "sum", "label": "Revenue", "field": "revenue", "value": 10}],
    ) == []


def test_normalize_unknown_lifecycle():
    assert normalize_decision_packet({"lifecycle": "nope"})["lifecycle"] == "draft"
