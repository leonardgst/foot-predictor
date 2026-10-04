"""Collecteur live de football-data, sans réseau : prochains matchs, saison courante, scellé, plafond, âge."""

from __future__ import annotations

import datetime as dt
import json

import pytest
import requests

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data import live
from foot_predictor.collect.football_data.download import USER_AGENT, Throttle
from foot_predictor.rawstore.backup import verify

# Format relevé sur le vrai fichier (sous-étape 5.10) ; équipes inventées.
FIXTURES = (
    b"\xef\xbb\xbfDiv,Date,Time,HomeTeam,AwayTeam,B365H,B365D,B365A,B365>2.5,B365<2.5\r\n"
    b"E0,10/10/2026,15:00,Equipe A,Equipe B,1.9,3.5,4.2,1.8,2.0\r\n"
)
SEASON = (
    b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,HST,AST\r\nE0,08/08/2026,20:00,Equipe A,Equipe C,1,0,9,7,4,2\r\n"
)


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content, self.status_code = content, status_code


class FakeGet:
    def __init__(self, content: bytes = FIXTURES, status: int = 200, error: Exception | None = None) -> None:
        self.content, self.status, self.error = content, status, error
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        if self.error:
            raise self.error
        return FakeResponse(self.content, self.status)


def no_throttle() -> Throttle:
    return Throttle(interval=0.0, sleep=lambda _: None)


def at(hour: int, minute: int = 0):
    return lambda: dt.datetime(2026, 10, 4, hour, minute, tzinfo=dt.UTC)


def test_fixtures_file_is_stored_byte_for_byte_with_its_manifest_line(tmp_path):
    get = FakeGet()
    report = live.fetch(tmp_path, [live.fixtures_target()], max_requests=1, get=get, throttle=no_throttle(), now=at(10))
    assert len(report.stored) == 1
    stored = raw_bytes.latest(tmp_path, live.FIXTURES_DIR, "fixtures", ".csv")
    assert stored.read_bytes() == FIXTURES and stored.name == "fixtures__20261004T100000000000Z.csv"
    url, headers = get.calls[0]
    assert url == "https://football-data.co.uk/fixtures.csv" and headers["User-Agent"] == USER_AGENT
    entry = json.loads((tmp_path / "_manifest" / "football_data.jsonl").read_text(encoding="utf-8"))
    assert (
        entry["endpoint"] == "fixtures"
        and entry["file"] == "football_data/fixtures/fixtures__20261004T100000000000Z.csv"
    )
    checked = verify(tmp_path)  # le fichier se vérifie comme les autres bruts (sha256 du journal)
    assert checked.ok and checked.verified == 1 and not checked.unlisted


def test_a_recent_version_is_not_requested_again_and_an_old_one_gets_a_new_version(tmp_path):
    target = live.fixtures_target()
    live.fetch(tmp_path, [target], max_requests=1, get=FakeGet(), throttle=no_throttle(), now=at(10))
    get = FakeGet()
    report = live.fetch(tmp_path, [target], max_requests=1, get=get, throttle=no_throttle(), now=at(15, 59))
    assert report.recent == [target] and not get.calls  # moins de 6 heures : aucune requête
    report = live.fetch(tmp_path, [target], max_requests=1, get=get, throttle=no_throttle(), now=at(16, 1))
    assert len(report.stored) == 1 and len(raw_bytes.versions(tmp_path, live.FIXTURES_DIR, "fixtures", ".csv")) == 2


def test_the_request_cap_is_respected(tmp_path):
    targets = [live.season_target(d, 2026) for d in ("E0", "SP1", "D1")]
    get = FakeGet(SEASON)
    report = live.fetch(tmp_path, targets, max_requests=2, get=get, throttle=no_throttle(), now=at(10))
    assert len(get.calls) == 2 and len(report.stored) == 2 and report.skipped_cap == targets[2:]
    assert get.calls[0][0] == "https://football-data.co.uk/mmz4281/2627/E0.csv"


def test_invalid_answers_are_not_stored(tmp_path):
    for get in (FakeGet(b"<html>erreur</html>"), FakeGet(status=404), FakeGet(error=requests.ConnectionError())):
        report = live.fetch(tmp_path, [live.fixtures_target()], max_requests=1, get=get, throttle=no_throttle(),
                            now=at(10))  # fmt: skip
        assert len(report.failed) == 1 and not report.stored
    assert raw_bytes.latest(tmp_path, live.FIXTURES_DIR, "fixtures", ".csv") is None
    assert not live.looks_like_fixtures(SEASON.replace(b"HomeTeam", b"Home")) and live.looks_like_fixtures(FIXTURES)


def test_sealed_seasons_are_refused_until_the_sealed_test_is_done(tmp_path, capsys):
    with pytest.raises(live.SealedSeasonRefused):
        live.check_season_allowed(2026, lambda: False)
    live.check_season_allowed(2026, lambda: True)
    live.check_season_allowed(2024, lambda: False)
    code = live.main(["--raw-dir", str(tmp_path), "season", "--season", "2026", "--max-requests", "1"],
                     sealed_test_done=lambda: False)  # fmt: skip
    assert code == 2 and "scellés" in capsys.readouterr().err
    assert not (tmp_path / "football_data").exists()


def test_cli_refuses_the_api_raw_dir_and_requires_a_cap(tmp_path, capsys):
    (tmp_path / "api_football").mkdir()
    assert live.main(["--raw-dir", str(tmp_path), "fixtures", "--max-requests", "1"]) == 2
    with pytest.raises(SystemExit):
        live.build_parser().parse_args(["fixtures"])


def test_dry_run_sends_nothing(tmp_path, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("aucune requête en --dry-run")

    monkeypatch.setattr(live.requests, "get", forbidden)
    assert live.main(["--raw-dir", str(tmp_path), "fixtures", "--max-requests", "1", "--dry-run"]) == 0
    assert "fixtures.csv (à demander)" in capsys.readouterr().out
    assert not (tmp_path / "football_data").exists()
