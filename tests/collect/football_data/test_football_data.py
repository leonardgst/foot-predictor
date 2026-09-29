"""Tests du collecteur football-data, sans réseau (réponses simulées)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
import requests

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data.__main__ import main
from foot_predictor.collect.football_data.check import check, shape
from foot_predictor.collect.football_data.download import (
    USER_AGENT,
    Target,
    Throttle,
    download,
    file_url,
    looks_like_csv,
    plan,
    season_code,
    season_dir,
)
from foot_predictor.rawstore.backup import verify
from foot_predictor.rawstore.lock import CollectLock, LockHeldError

# CSV synthétique, avec le BOM et les colonnes de fin vides des vrais fichiers.
CSV = b"\xef\xbb\xbfDiv,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,B365H,,\r\nE0,16/08/2024,20:00,Equipe A,Equipe B,1,0,1.5,,\r\nE0,17/08/2024,15:00,Equipe C,Equipe D,2,2,2.1,,\r\n,,,,,,,,,\r\n"


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content, self.status_code = content, status_code


class FakeGet:
    def __init__(self, responses: dict[str, FakeResponse] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return self.responses.get(url, FakeResponse(CSV))


def clock():
    moments = iter(dt.datetime(2026, 9, 29, 12, 0, second, tzinfo=dt.UTC) for second in range(60))
    return lambda: next(moments)


def no_throttle() -> Throttle:
    return Throttle(interval=0.0, sleep=lambda _: None)


def snapshot(directory: Path) -> dict[str, bytes]:
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def test_season_code_and_url():
    assert season_code(2000) == "0001"
    assert season_code(2026) == "2627"
    assert season_code(2099) == "9900"
    assert file_url("E0", 2023) == "https://www.football-data.co.uk/mmz4281/2324/E0.csv"


def test_looks_like_csv():
    assert looks_like_csv(CSV)
    assert looks_like_csv(b"Div,Date\n")
    assert not looks_like_csv(b"<!DOCTYPE html><html>404</html>")


def test_download_stores_bytes_exactly_with_manifest(tmp_path):
    get = FakeGet()
    report = download(tmp_path, [Target("E0", 2024)], max_requests=5, get=get, throttle=no_throttle(), now=clock())

    assert [t.division for t in report.stored] == ["E0"]
    stored = raw_bytes.versions(tmp_path, season_dir(2024), "E0", ".csv")
    assert len(stored) == 1
    assert stored[0].read_bytes() == CSV  # octet pour octet, BOM et CRLF compris
    assert stored[0].name == "E0__20260929T120000000000Z.csv"
    assert get.calls[0][1] == {"User-Agent": USER_AGENT}

    (entry,) = [json.loads(line) for line in (tmp_path / "_manifest" / "football_data.jsonl").read_text().splitlines()]
    assert entry["url"] == file_url("E0", 2024)
    assert entry["size_bytes"] == len(CSV)
    assert entry["file"] == "football_data/csv/season=2024/E0__20260929T120000000000Z.csv"
    # Les outils existants (backup, raw_check) vérifient ces fichiers par le journal.
    report = verify(tmp_path)
    assert report.ok and report.verified == 1
    assert not (tmp_path / "_lock" / "collecte.lock").exists()  # verrou rendu


def test_redownload_adds_a_version_never_overwrites(tmp_path):
    now = clock()
    download(tmp_path, [Target("E0", 2024)], max_requests=5, get=FakeGet(), throttle=no_throttle(), now=now)
    first = raw_bytes.latest(tmp_path, season_dir(2024), "E0", ".csv").read_bytes()
    download(tmp_path, [Target("E0", 2024)], max_requests=5, get=FakeGet(), throttle=no_throttle(), now=now)
    found = raw_bytes.versions(tmp_path, season_dir(2024), "E0", ".csv")
    assert len(found) == 2 and found[0].read_bytes() == first


def test_same_timestamp_is_refused(tmp_path):
    fixed = dt.datetime(2026, 9, 29, tzinfo=dt.UTC)
    raw_bytes.write_bytes(tmp_path, "x", "E0", ".csv", b"a", fixed)
    with pytest.raises(FileExistsError):
        raw_bytes.write_bytes(tmp_path, "x", "E0", ".csv", b"b", fixed)


def test_failures_are_reported_not_stored(tmp_path):
    get = FakeGet(
        {
            file_url("E0", 2024): FakeResponse(b"not found", 404),
            file_url("E1", 2024): FakeResponse(b"<html>maintenance</html>"),
        }
    )
    report = download(
        tmp_path,
        [Target("E0", 2024), Target("E1", 2024), Target("SP1", 2024)],
        max_requests=5,
        get=get,
        throttle=no_throttle(),
        now=clock(),
    )
    assert [reason for _, reason in report.failed] == ["HTTP 404", "réponse qui n'est pas un CSV football-data"]
    assert [t.division for t in report.stored] == ["SP1"]
    assert len((tmp_path / "_manifest" / "football_data.jsonl").read_text().splitlines()) == 1


def test_network_error_is_reported(tmp_path):
    def broken(*_args, **_kwargs):
        raise requests.ConnectionError("hors ligne")

    report = download(tmp_path, [Target("E0", 2024)], max_requests=1, get=broken, throttle=no_throttle(), now=clock())
    assert report.failed[0][1] == "erreur réseau : ConnectionError"


def test_cap_limits_requests(tmp_path):
    get = FakeGet()
    targets = [Target(d, 2024) for d in ("E0", "E1", "SP1")]
    report = download(tmp_path, targets, max_requests=2, get=get, throttle=no_throttle(), now=clock())
    assert len(get.calls) == 2
    assert [t.division for t in report.skipped_cap] == ["SP1"]


def test_throttle_spaces_requests():
    now = [0.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    throttle = Throttle(interval=1.0, clock=lambda: now[0], sleep=sleep)
    throttle.wait()
    now[0] += 0.3
    throttle.wait()
    throttle.wait()
    assert slept == [pytest.approx(0.7), pytest.approx(1.0)]


def test_download_refused_while_locked(tmp_path):
    with CollectLock(tmp_path, "autre commande"), pytest.raises(LockHeldError):
        download(tmp_path, [Target("E0", 2024)], max_requests=1, get=FakeGet(), throttle=no_throttle())


def test_plan_skips_present_files(tmp_path):
    raw_bytes.write_bytes(tmp_path, season_dir(2024), "E0", ".csv", CSV, dt.datetime(2026, 9, 29, tzinfo=dt.UTC))
    todo, present = plan(tmp_path, ("E0", "E1"), range(2024, 2025))
    assert [t.division for t in todo] == ["E1"] and [t.division for t in present] == ["E0"]
    todo, present = plan(tmp_path, ("E0", "E1"), range(2024, 2025), redownload=True)
    assert len(todo) == 2 and not present


def test_dry_run_writes_nothing(tmp_path, capsys):
    """E-027 : une simulation ne crée ni fichier, ni dossier, ni verrou."""
    missing = tmp_path / "absent"
    assert main(["--raw-dir", str(missing), "--division", "E0", "--first-season", "2024", "--last-season", "2024",
                 "download", "--max-requests", "5", "--dry-run"]) == 0  # fmt: skip
    assert not missing.exists()
    assert "mmz4281/2425/E0.csv" in capsys.readouterr().out

    existing = tmp_path / "raw"
    raw_bytes.write_bytes(existing, season_dir(2023), "E0", ".csv", CSV, dt.datetime(2026, 9, 29, tzinfo=dt.UTC))
    before = snapshot(existing)
    assert main(["--raw-dir", str(existing), "download", "--max-requests", "300", "--dry-run"]) == 0
    assert snapshot(existing) == before


def test_api_raw_dir_is_refused(tmp_path):
    (tmp_path / "api_football").mkdir()
    before = snapshot(tmp_path)
    assert main(["--raw-dir", str(tmp_path), "download", "--max-requests", "1"]) == 2
    assert snapshot(tmp_path) == before


def test_shape_counts_matches_and_named_columns():
    assert shape(CSV) == (2, 8)
    assert shape(b"") == (0, 0)
    assert shape("Div,Date,HomeTeam\nE0,01/01/01,Équipe\n".encode("cp1252")) == (1, 3)  # ancien encodage


def test_check_reports_missing_and_empty(tmp_path, capsys):
    stamp = dt.datetime(2026, 9, 29, tzinfo=dt.UTC)
    raw_bytes.write_bytes(tmp_path, season_dir(2024), "E0", ".csv", CSV, stamp)
    raw_bytes.write_bytes(tmp_path, season_dir(2024), "E1", ".csv", b"Div,Date\r\n", stamp)
    shapes = {(s.division, s.season): s for s in check(tmp_path, ("E0", "E1", "SP1"), range(2024, 2025))}
    assert shapes[("E0", 2024)].matches == 2
    assert shapes[("E1", 2024)].empty
    assert shapes[("SP1", 2024)].path is None
    code = main(["--raw-dir", str(tmp_path), "--division", "E0", "--division", "E1", "--division", "SP1",
                 "--first-season", "2024", "--last-season", "2024", "check"])  # fmt: skip
    assert code == 1
    assert "absents : 1 ; vides : 1" in capsys.readouterr().out
