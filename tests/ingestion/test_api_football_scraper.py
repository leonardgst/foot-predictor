"""Tests du téléchargement API-Football (`ingestion/api_football_scraper.py`) :
en-têtes d'authentification, appels HTTP mockés (jamais de vraie requête vers
api-sports.io), filtrage des fixtures non terminées, et logique de skip
`_fixture_already_ingested` -- le coeur du mécanisme de reprise sur
plusieurs jours (`db`, cf. docstring du module)."""
from __future__ import annotations

import requests
import pytest
from sqlalchemy import select

from foot_predictor.db.models import ApiFootballFixtureDetail, SourceIngestionLog
from foot_predictor.ingestion import api_football_scraper as scraper


# ---------------------------------------------------------------------------
# _headers
# ---------------------------------------------------------------------------


def test_headers_raises_without_api_key_env_var(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)

    with pytest.raises(RuntimeError, match="API_FOOTBALL_KEY"):
        scraper._headers()


def test_headers_returns_expected_header_when_api_key_set(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "secret-key-123")

    assert scraper._headers() == {"x-apisports-key": "secret-key-123"}


# ---------------------------------------------------------------------------
# fetch_fixtures / fetch_fixture_detail : appels HTTP mockés
# ---------------------------------------------------------------------------


def test_fetch_fixtures_calls_expected_url_params_and_returns_response_list(monkeypatch, mocker):
    monkeypatch.setenv("API_FOOTBALL_KEY", "secret-key-123")
    fake_response = mocker.Mock()
    fake_response.json.return_value = {"response": [{"fixture": {"id": 1}}]}
    mock_get = mocker.patch.object(scraper.requests, "get", return_value=fake_response)

    result = scraper.fetch_fixtures(61, 2024, "2024-08-01", "2025-06-30")

    mock_get.assert_called_once_with(
        "https://v3.football.api-sports.io/fixtures",
        headers={"x-apisports-key": "secret-key-123"},
        params={"league": 61, "season": 2024, "from": "2024-08-01", "to": "2025-06-30"},
        timeout=30,
    )
    fake_response.raise_for_status.assert_called_once()
    assert result == [{"fixture": {"id": 1}}]


def test_fetch_fixtures_returns_empty_list_when_response_key_absent(monkeypatch, mocker):
    monkeypatch.setenv("API_FOOTBALL_KEY", "secret-key-123")
    fake_response = mocker.Mock()
    fake_response.json.return_value = {}
    mocker.patch.object(scraper.requests, "get", return_value=fake_response)

    assert scraper.fetch_fixtures(61, 2024, "2024-08-01", "2025-06-30") == []


def test_fetch_fixtures_raises_on_http_error(monkeypatch, mocker):
    monkeypatch.setenv("API_FOOTBALL_KEY", "secret-key-123")
    fake_response = mocker.Mock()
    fake_response.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
    mocker.patch.object(scraper.requests, "get", return_value=fake_response)

    with pytest.raises(requests.HTTPError):
        scraper.fetch_fixtures(61, 2024, "2024-08-01", "2025-06-30")


def test_fetch_fixture_detail_returns_first_item_of_response(monkeypatch, mocker):
    monkeypatch.setenv("API_FOOTBALL_KEY", "secret-key-123")
    fake_response = mocker.Mock()
    fake_response.json.return_value = {"response": [{"fixture": {"id": 42}}]}
    mocker.patch.object(scraper.requests, "get", return_value=fake_response)

    detail = scraper.fetch_fixture_detail(42)

    assert detail == {"fixture": {"id": 42}}


def test_fetch_fixture_detail_returns_none_when_response_empty(monkeypatch, mocker):
    monkeypatch.setenv("API_FOOTBALL_KEY", "secret-key-123")
    fake_response = mocker.Mock()
    fake_response.json.return_value = {"response": []}
    mocker.patch.object(scraper.requests, "get", return_value=fake_response)

    assert scraper.fetch_fixture_detail(999) is None


# ---------------------------------------------------------------------------
# season_date_range : fonction pure
# ---------------------------------------------------------------------------


def test_season_date_range_spans_august_to_june():
    assert scraper.season_date_range(2015) == ("2015-08-01", "2016-06-30")


# ---------------------------------------------------------------------------
# ingest_league_fixture_details : filtrage FT, skip already_ingested, erreurs (db)
# ---------------------------------------------------------------------------


def _fixture_stub(fixture_id: int, status_short: str = "FT") -> dict:
    return {"fixture": {"id": fixture_id, "status": {"short": status_short}}}


@pytest.mark.db
def test_ingest_skips_fixtures_that_are_not_finished(db_session, mocker):
    mocker.patch.object(scraper, "fetch_fixtures", return_value=[_fixture_stub(1, "NS")])
    fetch_detail = mocker.patch.object(scraper, "fetch_fixture_detail")

    counts = scraper.ingest_league_fixture_details(db_session, 61, 2024, "2024-08-01", "2025-06-30")

    assert counts["not_finished"] == 1
    assert counts["created"] == 0
    fetch_detail.assert_not_called()


@pytest.mark.db
def test_ingest_skips_fixtures_already_in_raw_without_calling_fetch_detail(db_session, mocker):
    """Coeur du mécanisme de reprise multi-jours (cf. docstring du module) :
    un fixture déjà présent en raw ne doit jamais déclencher un nouvel appel
    /fixtures?id= (économie de quota)."""
    existing_log = SourceIngestionLog(source_name="api-football", status="success")
    db_session.add(existing_log)
    db_session.flush()
    db_session.add(
        ApiFootballFixtureDetail(ingestion_id=existing_log.id, raw_payload=_fixture_stub(7))
    )
    db_session.flush()

    mocker.patch.object(scraper, "fetch_fixtures", return_value=[_fixture_stub(7, "FT")])
    fetch_detail = mocker.patch.object(scraper, "fetch_fixture_detail")
    mocker.patch.object(scraper.time, "sleep")

    counts = scraper.ingest_league_fixture_details(db_session, 61, 2024, "2024-08-01", "2025-06-30")

    assert counts["already_ingested"] == 1
    assert counts["created"] == 0
    fetch_detail.assert_not_called()


@pytest.mark.db
def test_ingest_creates_new_fixture_detail_when_not_already_ingested(db_session, mocker):
    mocker.patch.object(scraper, "fetch_fixtures", return_value=[_fixture_stub(99, "FT")])
    full_detail = {"fixture": {"id": 99, "status": {"short": "FT"}}, "teams": {"home": "A", "away": "B"}}
    mocker.patch.object(scraper, "fetch_fixture_detail", return_value=full_detail)
    mocker.patch.object(scraper.time, "sleep")

    counts = scraper.ingest_league_fixture_details(db_session, 61, 2024, "2024-08-01", "2025-06-30")

    assert counts["created"] == 1
    stored = db_session.scalar(select(ApiFootballFixtureDetail))
    assert stored.raw_payload == full_detail


@pytest.mark.db
def test_ingest_marks_log_failed_on_request_exception(db_session, mocker):
    mocker.patch.object(scraper, "fetch_fixtures", side_effect=requests.RequestException("quota exceeded"))

    counts = scraper.ingest_league_fixture_details(db_session, 61, 2024, "2024-08-01", "2025-06-30")

    assert "error" in counts
    log = db_session.scalar(select(SourceIngestionLog).where(SourceIngestionLog.source_name == "api-football"))
    assert log is not None
    assert log.status == "failed"
