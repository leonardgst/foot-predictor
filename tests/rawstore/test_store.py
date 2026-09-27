"""Écriture atomique et absence d'écrasement du brut (ADR-0003)."""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib

import pytest

from foot_predictor.rawstore import store

FETCHED_AT = dt.datetime(2026, 10, 2, 8, 15, 30, 123456, tzinfo=dt.timezone.utc)


def _envelope(body=None):
    return store.build_envelope(
        endpoint="/fixtures",
        params={"league": 39, "season": 2023},
        fetched_at=FETCHED_AT,
        http_status=200,
        headers_quota={"x-ratelimit-requests-remaining": "7000"},
        body=body if body is not None else {"errors": [], "results": 0, "response": []},
    )


def test_write_envelope_creates_versioned_file_and_roundtrips(tmp_path):
    envelope = _envelope()
    stored = store.write_envelope(tmp_path, "api_football/fixtures_list/league=39", "season=2023", envelope, FETCHED_AT)

    assert stored.relative_path == (
        "api_football/fixtures_list/league=39/season=2023__20261002T081530123456Z.json.gz"
    )
    assert store.read_envelope(stored.path) == envelope
    assert set(envelope) == {"request", "fetched_at", "http_status", "headers_quota", "body"}
    assert stored.sha256 == hashlib.sha256(stored.path.read_bytes()).hexdigest()
    assert list(stored.path.parent.glob("*.tmp")) == []


def test_write_envelope_never_overwrites(tmp_path):
    first = store.write_envelope(tmp_path, "a", "k", _envelope({"v": 1}), FETCHED_AT)
    original = first.path.read_bytes()

    with pytest.raises(store.RawFileExistsError):
        store.write_envelope(tmp_path, "a", "k", _envelope({"v": 2}), FETCHED_AT)

    assert first.path.read_bytes() == original
    assert list(first.path.parent.glob("*.tmp")) == []


def test_recollection_creates_new_version_and_latest_picks_it(tmp_path):
    store.write_envelope(tmp_path, "a", "k", _envelope({"v": 1}), FETCHED_AT)
    later = FETCHED_AT + dt.timedelta(days=3)
    second = store.write_envelope(tmp_path, "a", "k", _envelope({"v": 2}), later)

    assert len(list((tmp_path / "a").glob("k__*.json.gz"))) == 2
    assert store.latest_version(tmp_path, "a", "k") == second.path
    assert store.latest_version(tmp_path, "a", "absent") is None
    assert store.latest_version(tmp_path, "dossier_absent", "k") is None


def test_failed_write_leaves_no_partial_file(tmp_path, monkeypatch):
    """Un plantage au moment du renommage ne laisse ni fichier final ni .tmp."""

    def boom(src, dst):
        raise OSError("disque plein simulé")

    monkeypatch.setattr(store.os, "rename", boom)
    with pytest.raises(OSError):
        store.write_envelope(tmp_path, "a", "k", _envelope(), FETCHED_AT)

    assert list((tmp_path / "a").iterdir()) == []


def test_encoding_is_deterministic():
    envelope = _envelope({"b": 1, "a": 2})
    assert store.encode_envelope(envelope) == store.encode_envelope(dict(reversed(envelope.items())))
    assert gzip.decompress(store.encode_envelope(envelope)).startswith(b"{")


def test_iter_raw_files_ignores_tmp(tmp_path):
    stored = store.write_envelope(tmp_path, "api_football/x", "k", _envelope(), FETCHED_AT)
    (stored.path.parent / "orphelin.json.gz.tmp").write_bytes(b"...")

    assert store.iter_raw_files(tmp_path, "api_football") == [stored.path]
    assert store.iter_raw_files(tmp_path, "autre_source") == []
