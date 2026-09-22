"""Tests du scraper raw pour /injuries (`ingestion/injuries_scraper.py`).

`requests.get` est systématiquement mocké : aucun appel réseau réel vers
API-Football n'est jamais effectué dans ces tests.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import select

from foot_predictor.db.models import ApiFootballInjuries
from foot_predictor.ingestion.injuries_scraper import fetch_injuries, ingest_league_season_injuries

pytestmark = pytest.mark.db


INJURIES_RESPONSE = {
    "response": [
        {
            "player": {"id": 276, "name": "N. Player", "photo": "https://example.com/276.png"},
            "team": {"id": 50, "name": "Manchester City", "logo": "https://example.com/50.png"},
            "fixture": {
                "id": 592872,
                "timezone": "UTC",
                "date": "2021-08-28T14:00:00+00:00",
                "timestamp": 1630159200,
            },
            "league": {
                "id": 39,
                "season": 2021,
                "name": "Premier League",
                "country": "England",
                "logo": "https://example.com/39.png",
                "flag": "https://example.com/england.svg",
            },
            "type": "Missing Fixture",
            "reason": "Knee Injury",
        },
        {
            "player": {"id": 277, "name": "M. Autre", "photo": "https://example.com/277.png"},
            "team": {"id": 50, "name": "Manchester City", "logo": "https://example.com/50.png"},
            "fixture": {
                "id": 592873,
                "timezone": "UTC",
                "date": "2021-08-29T14:00:00+00:00",
                "timestamp": 1630245600,
            },
            "league": {
                "id": 39,
                "season": 2021,
                "name": "Premier League",
                "country": "England",
                "logo": "https://example.com/39.png",
                "flag": "https://example.com/england.svg",
            },
            "type": "Suspended",
            "reason": "Red Card",
        },
    ]
}


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "dummy-test-key")


def _mock_response(mocker, payload: dict):
    response = mocker.Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_fetch_injuries_parses_response(mocker):
    mock_get = mocker.patch("foot_predictor.ingestion.injuries_scraper.requests.get")
    mock_get.return_value = _mock_response(mocker, INJURIES_RESPONSE)

    entries = fetch_injuries(league_id=39, season=2021)

    assert len(entries) == 2
    assert entries[0]["player"]["name"] == "N. Player"
    assert entries[0]["reason"] == "Knee Injury"

    called_kwargs = mock_get.call_args.kwargs
    assert called_kwargs["params"] == {"league": 39, "season": 2021}
    assert called_kwargs["headers"] == {"x-apisports-key": "dummy-test-key"}


def test_ingest_league_season_injuries_inserts_raw_rows(db_session, mocker):
    mocker.patch(
        "foot_predictor.ingestion.injuries_scraper.requests.get",
        return_value=_mock_response(mocker, INJURIES_RESPONSE),
    )

    counts = ingest_league_season_injuries(db_session, league_id=39, season=2021)

    assert counts == {"created": 2, "already_ingested": 0}
    rows = db_session.scalars(select(ApiFootballInjuries)).all()
    assert len(rows) == 2


def test_ingest_league_season_injuries_is_idempotent_on_rerun(db_session, mocker):
    mocker.patch(
        "foot_predictor.ingestion.injuries_scraper.requests.get",
        return_value=_mock_response(mocker, INJURIES_RESPONSE),
    )

    ingest_league_season_injuries(db_session, league_id=39, season=2021)
    counts = ingest_league_season_injuries(db_session, league_id=39, season=2021)

    assert counts == {"created": 0, "already_ingested": 2}
    rows = db_session.scalars(select(ApiFootballInjuries)).all()
    assert len(rows) == 2
