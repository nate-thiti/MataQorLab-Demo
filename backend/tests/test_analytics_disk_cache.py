"""Tests for disk-backed analytics cache."""
from app.core.config import settings
from app.services import analytics_cache


def test_analytics_disk_cache_survives_memory_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ANALYTICS_DISK_CACHE_DIR", str(tmp_path))
    key = analytics_cache.base_cache_key("u1", "data.csv", {"a": "b"})
    payload = {"formatted_notes": "hello", "stats": {"rows": 10}}
    analytics_cache.set_base_analytics(key, payload)

    analytics_cache._base_cache.clear()
    restored = analytics_cache.get_base_analytics(key)
    assert restored == payload


def test_base_cache_key_includes_cleaning_profile():
    standard = analytics_cache.base_cache_key("u1", "data.csv", {"a": "b"}, cleaning_profile="standard")
    financial = analytics_cache.base_cache_key("u1", "data.csv", {"a": "b"}, cleaning_profile="financial")
    assert standard != financial


def test_base_cache_key_includes_complete_dataset_provenance():
    provenance = {
        "dataset_version_id": "version-1",
        "source_fingerprint": "source-1",
        "contract_hash": "contract-1",
        "recipe_hash": "recipe-1",
    }
    key = analytics_cache.base_cache_key(
        "u1", "data.csv", {"a": "b"}, provenance=provenance
    )

    for field in provenance:
        changed = dict(provenance)
        changed[field] = f"{changed[field]}-changed"
        assert key != analytics_cache.base_cache_key(
            "u1", "data.csv", {"a": "b"}, provenance=changed
        )


def test_question_result_disk_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ANALYTICS_DISK_CACHE_DIR", str(tmp_path))
    key = analytics_cache.question_cache_key("u1", "data.csv", None, "What is revenue?")
    analytics_cache.set_question_result(key, {"answer": 42})
    analytics_cache._question_cache.clear()
    assert analytics_cache.get_question_result(key) == {"answer": 42}
