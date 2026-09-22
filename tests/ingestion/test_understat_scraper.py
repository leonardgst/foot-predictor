"""Tests du téléchargement Understat niveau équipe (`ingestion/understat_scraper.py`) :
le client `UnderstatClient` est toujours mocké (jamais de vraie requête vers
understat.com), construction du payload (`_build_payload`, cas où un match
est ignoré -- pas encore joué / xG absent), et idempotence de l'ingestion en
base (`db`)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from foot_predictor.db.models import SourceIngestionLog, UnderstatMatchStats
from foot_predictor.ingestion import understat_scraper as scraper


# ---------------------------------------------------------------------------
# fetch_league_matches : appelle bien la chaîne client.league(...).get_match_data(...)
# ---------------------------------------------------------------------------


def test_fetch_league_matches_calls_expected_client_chain(mocker):
    fake_league = mocker.Mock()
    fake_league.get_match_data.return_value = [{"isResult": True}]
    fake_client = mocker.Mock()
    fake_client.league.return_value = fake_league

    result = scraper.fetch_league_matches(fake_client, "EPL", "2024")

    fake_client.league.assert_called_once_with(league="EPL")
    fake_league.get_match_data.assert_called_once_with(season="2024")
    assert result == [{"isResult": True}]


# ---------------------------------------------------------------------------
# _build_payload : fonction pure
# ---------------------------------------------------------------------------


def _match_entry(**overrides) -> dict:
    base = {
        "isResult": True,
        "datetime": "2024-08-17 14:00:00",
        "h": {"title": "Manchester_United"},
        "a": {"title": "Fulham"},
        "xG": {"h": 1.849, "a": 0.617},
    }
    base.update(overrides)
    return base


def test_build_payload_happy_path_builds_expected_dict():
    payload = scraper._build_payload(_match_entry())

    assert payload == {
        "match_date": "2024-08-17",
        "home_team": "Manchester_United",
        "away_team": "Fulham",
        "home_xg": 1.85,
        "away_xg": 0.62,
    }


def test_build_payload_returns_none_for_match_not_yet_played():
    payload = scraper._build_payload(_match_entry(isResult=False))

    assert payload is None


def test_build_payload_returns_none_when_datetime_missing():
    payload = scraper._build_payload(_match_entry(datetime=None))

    assert payload is None


def test_build_payload_returns_none_when_xg_missing():
    payload = scraper._build_payload(_match_entry(xG={}))

    assert payload is None


def test_build_payload_returns_none_when_only_one_side_xg_missing():
    payload = scraper._build_payload(_match_entry(xG={"h": 1.2}))

    assert payload is None


# ---------------------------------------------------------------------------
# ingest_league_matches : upsert idempotent + gestion d'erreur (db)
# ---------------------------------------------------------------------------


def _fake_client_with_matches(mocker, matches: list[dict]):
    fake_league = mocker.Mock()
    fake_league.get_match_data.return_value = matches
    fake_client = mocker.Mock()
    fake_client.league.return_value = fake_league
    return fake_client


@pytest.mark.db
def test_ingest_league_matches_creates_rows_and_skips_unplayed_entries(db_session, mocker):
    matches = [_match_entry(), _match_entry(isResult=False)]
    fake_client = _fake_client_with_matches(mocker, matches)

    counts = scraper.ingest_league_matches(db_session, fake_client, "EPL", "2024")

    assert counts == {"created": 1, "updated": 0, "unchanged": 0, "skipped": 1}
    stored = db_session.scalars(select(UnderstatMatchStats)).all()
    assert len(stored) == 1
    assert stored[0].raw_payload["home_team"] == "Manchester_United"


@pytest.mark.db
def test_ingest_league_matches_second_run_is_idempotent(db_session, mocker):
    fake_client = _fake_client_with_matches(mocker, [_match_entry()])
    scraper.ingest_league_matches(db_session, fake_client, "EPL", "2024")

    counts = scraper.ingest_league_matches(db_session, fake_client, "EPL", "2024")

    assert counts["created"] == 0
    assert counts["unchanged"] == 1
    rows = db_session.scalars(select(UnderstatMatchStats)).all()
    assert len(rows) == 1  # pas de doublon


@pytest.mark.db
def test_ingest_league_matches_marks_log_failed_on_client_exception(db_session, mocker):
    fake_league = mocker.Mock()
    fake_league.get_match_data.side_effect = RuntimeError("understat.com unreachable")
    fake_client = mocker.Mock()
    fake_client.league.return_value = fake_league

    counts = scraper.ingest_league_matches(db_session, fake_client, "EPL", "2024")

    assert "error" in counts
    log = db_session.scalar(select(SourceIngestionLog).where(SourceIngestionLog.source_name == "understat"))
    assert log is not None
    assert log.status == "failed"
