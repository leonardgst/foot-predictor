"""Tests de l'ingestion raw.api_football_injuries -> staging.player_injury
(`ingestion/injuries.py`). Aucun réseau : les lignes raw sont insérées
directement en base, comme pour les extracteurs de api_football.py."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from foot_predictor.db.models import ApiFootballInjuries, Player, PlayerInjury, SourceIngestionLog
from foot_predictor.ingestion.injuries import ingest_api_football_injuries

pytestmark = pytest.mark.db


def _injury_payload(
    *,
    player_id: int = 276,
    player_name: str = "N. Player",
    fixture_id: int = 592872,
    date: str = "2021-08-28T14:00:00+00:00",
    reason: str | None = "Knee Injury",
    type_: str = "Missing Fixture",
) -> dict:
    payload = {
        "player": {"id": player_id, "name": player_name, "photo": "https://example.com/photo.png"},
        "team": {"id": 50, "name": "Manchester City", "logo": "https://example.com/logo.png"},
        "fixture": {"id": fixture_id, "timezone": "UTC", "date": date, "timestamp": 1630159200},
        "league": {
            "id": 39,
            "season": 2021,
            "name": "Premier League",
            "country": "England",
            "logo": "https://example.com/league.png",
            "flag": "https://example.com/flag.svg",
        },
        "type": type_,
        "reason": reason,
    }
    if reason is None:
        payload.pop("reason")
    return payload


@pytest.fixture
def make_raw_injury(db_session):
    log = SourceIngestionLog(source_name="api-football", payload_ref="test", status="success")
    db_session.add(log)
    db_session.flush()

    def _make(payload: dict) -> ApiFootballInjuries:
        row = ApiFootballInjuries(ingestion_id=log.id, raw_payload=payload)
        db_session.add(row)
        db_session.flush()
        return row

    return _make


def test_ingest_creates_player_injury_with_expected_fields(db_session, make_raw_injury):
    make_raw_injury(_injury_payload())

    processed, skipped = ingest_api_football_injuries(db_session)

    assert (processed, skipped) == (1, 0)
    injury = db_session.scalar(select(PlayerInjury))
    assert injury is not None
    assert injury.start_date == dt.date(2021, 8, 28)
    assert injury.injury_type == "Knee Injury"
    assert injury.end_date is None

    player = db_session.get(Player, injury.player_id)
    assert player.full_name == "N. Player"


def test_ingest_is_idempotent_on_rerun(db_session, make_raw_injury):
    make_raw_injury(_injury_payload())

    ingest_api_football_injuries(db_session)
    processed, skipped = ingest_api_football_injuries(db_session)

    assert (processed, skipped) == (1, 0)
    injuries = db_session.scalars(select(PlayerInjury)).all()
    assert len(injuries) == 1


def test_ingest_falls_back_to_type_when_reason_missing(db_session, make_raw_injury):
    make_raw_injury(_injury_payload(reason=None, type_="Suspended"))

    processed, skipped = ingest_api_football_injuries(db_session)

    assert (processed, skipped) == (1, 0)
    injury = db_session.scalar(select(PlayerInjury))
    assert injury.injury_type == "Suspended"


def test_ingest_same_player_two_entries_creates_two_distinct_rows(db_session, make_raw_injury):
    make_raw_injury(
        _injury_payload(fixture_id=592872, date="2021-08-28T14:00:00+00:00", reason="Knee Injury")
    )
    make_raw_injury(
        _injury_payload(fixture_id=592900, date="2021-09-15T14:00:00+00:00", reason="Ankle Injury")
    )

    processed, skipped = ingest_api_football_injuries(db_session)

    assert (processed, skipped) == (2, 0)
    injuries = db_session.scalars(select(PlayerInjury)).all()
    assert len(injuries) == 2
    players = db_session.scalars(select(Player)).all()
    assert len(players) == 1  # même joueur, deux blessures distinctes
