"""Sauvegarde et vérification des sha256 (ADR-0006)."""
from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.rawstore import backup, manifest, store

T0 = dt.datetime(2026, 10, 19, 8, 0, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def raw_dir(tmp_path):
    raw = tmp_path / "raw"
    for i in range(3):
        fetched_at = T0 + dt.timedelta(seconds=i)
        envelope = store.build_envelope(
            endpoint="/teams", params={"league": 39, "season": 2015 + i}, fetched_at=fetched_at,
            http_status=200, headers_quota={}, body={"errors": [], "results": 1, "response": [i]},
        )
        stored = store.write_envelope(raw, "api_football/teams/league=39", f"season={2015 + i}", envelope, fetched_at)
        manifest.append_entry(raw, "api_football", manifest.entry_for_stored(envelope, stored, source="api_football", duration_ms=1))
    (raw / "_queue").mkdir()
    (raw / "_queue" / "api_football.sqlite").write_bytes(b"sqlite")
    return raw


def test_backup_copies_everything_and_verifies(raw_dir, tmp_path):
    dest = tmp_path / "disque_externe" / "raw"
    report = backup.backup(raw_dir, dest)

    assert report.ok
    assert report.verified == 3
    assert report.unlisted == [] and report.missing == [] and report.mismatched == []
    assert (dest / "_queue" / "api_football.sqlite").read_bytes() == b"sqlite"


def test_verify_detects_corrupted_missing_and_unlisted_files(raw_dir, tmp_path):
    dest = tmp_path / "copie"
    backup.backup(raw_dir, dest)
    files = sorted((dest / "api_football").rglob("*.json.gz"))
    files[0].write_bytes(b"octets corrompus")
    files[1].unlink()
    (dest / "api_football" / "hors_journal__20261019T000000000000Z.json.gz").write_bytes(b"x")

    report = backup.verify(dest)

    assert not report.ok
    assert report.verified == 1
    assert report.mismatched == [files[0].relative_to(dest).as_posix()]
    assert report.missing == [files[1].relative_to(dest).as_posix()]
    assert report.unlisted == ["api_football/hors_journal__20261019T000000000000Z.json.gz"]
    # L'original n'est pas affecté.
    assert backup.verify(raw_dir).ok


def test_backup_refuses_non_empty_destination(raw_dir, tmp_path):
    dest = tmp_path / "occupe"
    dest.mkdir()
    (dest / "fichier.txt").write_text("déjà là")
    with pytest.raises(FileExistsError):
        backup.backup(raw_dir, dest)


def test_backup_refuses_destination_inside_raw(raw_dir):
    with pytest.raises(ValueError):
        backup.backup(raw_dir, raw_dir / "copie")
