"""Journal des requêtes : ajout, lecture et reconstruction (rapport G.8)."""
from __future__ import annotations

import datetime as dt

from foot_predictor.rawstore import manifest, store

T0 = dt.datetime(2026, 10, 2, 8, 0, 0, tzinfo=dt.timezone.utc)


def _write(raw_dir, rel_dir, stem, body, fetched_at, duration_ms=120):
    envelope = store.build_envelope(
        endpoint="/fixtures",
        params={"league": 39, "season": 2023},
        fetched_at=fetched_at,
        http_status=200,
        headers_quota={},
        body=body,
    )
    stored = store.write_envelope(raw_dir, rel_dir, stem, envelope, fetched_at)
    entry = manifest.entry_for_stored(
        envelope, stored, source="api_football", duration_ms=duration_ms, extra={"tag": stem}
    )
    manifest.append_entry(raw_dir, "api_football", entry)
    return entry


def test_append_and_read_entries(tmp_path):
    entry = _write(tmp_path, "api_football/a", "k", {"errors": [], "results": 3}, T0)

    entries = manifest.read_entries(tmp_path, "api_football")
    assert entries == [entry]
    assert entry["errors"] == [] and entry["results"] == 3
    assert entry["file"].startswith("api_football/a/k__")
    assert entry["tag"] == "k"


def test_read_entries_without_manifest(tmp_path):
    assert manifest.read_entries(tmp_path, "api_football") == []


def test_rebuild_matches_original_except_duration(tmp_path):
    originals = [
        _write(tmp_path, "api_football/b", "k2", {"errors": {"plan": "x"}, "results": 0}, T0 + dt.timedelta(minutes=1)),
        _write(tmp_path, "api_football/a", "k1", {"errors": [], "results": 5}, T0),
    ]
    original_manifest = manifest.manifest_path(tmp_path, "api_football").read_bytes()

    target, rebuilt = manifest.rebuild(
        tmp_path, "api_football", extra_fields=lambda env: {"http_ok": env["http_status"] == 200}
    )

    expected = sorted(originals, key=lambda e: e["timestamp"])
    for original, new in zip(expected, rebuilt, strict=True):
        for key in ("timestamp", "endpoint", "params", "http_status", "errors", "results", "file", "sha256"):
            assert new[key] == original[key]
        assert new["duration_ms"] is None
        assert new["http_ok"] is True
    assert manifest.read_manifest_file(target) == rebuilt
    # Le journal d'origine n'est pas touché.
    assert manifest.manifest_path(tmp_path, "api_football").read_bytes() == original_manifest
    assert ".rebuilt-" in target.name
