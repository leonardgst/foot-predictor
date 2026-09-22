"""Tests du téléchargement Understat niveau joueur (`ingestion/understat_player_scraper.py`) :
le client `UnderstatClient` est toujours mocké (jamais de vraie requête vers
understat.com), construction du payload par match joueur (arrondis, valeurs
manquantes défaut à 0), et idempotence/gestion d'erreur de l'ingestion en
base (`db`)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from foot_predictor.db.models import SourceIngestionLog, UnderstatPlayerMatch
from foot_predictor.ingestion import understat_player_scraper as scraper


# ---------------------------------------------------------------------------
# fetch_league_players / fetch_player_matches : chaîne client mockée
# ---------------------------------------------------------------------------


def test_fetch_league_players_calls_expected_client_chain(mocker):
    fake_league = mocker.Mock()
    fake_league.get_player_data.return_value = [{"id": "123", "player_name": "Cole Palmer"}]
    fake_client = mocker.Mock()
    fake_client.league.return_value = fake_league

    result = scraper.fetch_league_players(fake_client, "EPL", "2024")

    fake_client.league.assert_called_once_with(league="EPL")
    fake_league.get_player_data.assert_called_once_with(season="2024")
    assert result == [{"id": "123", "player_name": "Cole Palmer"}]


def test_fetch_player_matches_calls_expected_client_chain(mocker):
    fake_player = mocker.Mock()
    fake_player.get_match_data.return_value = [{"date": "2024-08-17"}]
    fake_client = mocker.Mock()
    fake_client.player.return_value = fake_player

    result = scraper.fetch_player_matches(fake_client, "123")

    fake_client.player.assert_called_once_with(player="123")
    fake_player.get_match_data.assert_called_once_with()
    assert result == [{"date": "2024-08-17"}]


# ---------------------------------------------------------------------------
# _build_payload : fonction pure
# ---------------------------------------------------------------------------


def _match_entry(**overrides) -> dict:
    base = {
        "date": "2024-08-17 14:00:00",
        "h_team": "Manchester United",
        "a_team": "Fulham",
        "xG": 0.4523,
        "xA": 0.1289,
        "npxG": 0.4523,
        "time": "78",
    }
    base.update(overrides)
    return base


def test_build_payload_happy_path_rounds_and_converts_types():
    payload = scraper._build_payload("Cole Palmer", _match_entry())

    assert payload == {
        "player_name": "Cole Palmer",
        "match_date": "2024-08-17",
        "home_team": "Manchester United",
        "away_team": "Fulham",
        "xg": 0.45,
        "xa": 0.13,
        "npxg": 0.45,
        "minutes": 78,
    }


def test_build_payload_defaults_missing_xg_fields_to_zero():
    entry = {"date": "2024-08-17", "h_team": "A", "a_team": "B"}

    payload = scraper._build_payload("Player X", entry)

    assert payload["xg"] == 0.0
    assert payload["xa"] == 0.0
    assert payload["npxg"] == 0.0
    assert payload["minutes"] == 0


def test_build_payload_treats_explicit_none_xg_as_zero():
    """Understat peut renvoyer `None` explicitement (pas juste absence de clé)
    pour un joueur n'ayant pas joué -- `or 0` dans le code doit l'absorber."""
    payload = scraper._build_payload("Player X", _match_entry(xG=None, xA=None, npxG=None))

    assert payload["xg"] == 0.0
    assert payload["xa"] == 0.0
    assert payload["npxg"] == 0.0


# ---------------------------------------------------------------------------
# ingest_league_players : idempotence, skip sans date, gestion d'erreur (db)
# ---------------------------------------------------------------------------


def _fake_client(mocker, players: list[dict], matches_by_player: dict[str, list[dict]]):
    fake_league = mocker.Mock()
    fake_league.get_player_data.return_value = players

    def _player_side_effect(player):
        fake_player = mocker.Mock()
        fake_player.get_match_data.return_value = matches_by_player[player]
        return fake_player

    fake_client = mocker.Mock()
    fake_client.league.return_value = fake_league
    fake_client.player.side_effect = _player_side_effect
    return fake_client


@pytest.mark.db
def test_ingest_league_players_creates_rows_and_skips_entries_without_date(db_session, mocker):
    players = [{"id": "1", "player_name": "Cole Palmer"}]
    matches = {"1": [_match_entry(), {"h_team": "A", "a_team": "B"}]}  # 2e sans "date" -> skip
    fake_client = _fake_client(mocker, players, matches)
    mocker.patch.object(scraper.time, "sleep")

    counts = scraper.ingest_league_players(db_session, fake_client, "EPL", "2024")

    assert counts["created"] == 1
    stored = db_session.scalars(select(UnderstatPlayerMatch)).all()
    assert len(stored) == 1
    assert stored[0].raw_payload["player_name"] == "Cole Palmer"


@pytest.mark.db
def test_ingest_league_players_second_run_is_idempotent(db_session, mocker):
    players = [{"id": "1", "player_name": "Cole Palmer"}]
    matches = {"1": [_match_entry()]}
    fake_client = _fake_client(mocker, players, matches)
    mocker.patch.object(scraper.time, "sleep")
    scraper.ingest_league_players(db_session, fake_client, "EPL", "2024")

    counts = scraper.ingest_league_players(db_session, fake_client, "EPL", "2024")

    assert counts["created"] == 0
    assert counts["unchanged"] == 1
    rows = db_session.scalars(select(UnderstatPlayerMatch)).all()
    assert len(rows) == 1


@pytest.mark.db
def test_ingest_league_players_marks_log_failed_on_client_exception(db_session, mocker):
    fake_league = mocker.Mock()
    fake_league.get_player_data.side_effect = RuntimeError("understat.com unreachable")
    fake_client = mocker.Mock()
    fake_client.league.return_value = fake_league

    counts = scraper.ingest_league_players(db_session, fake_client, "EPL", "2024")

    assert "error" in counts
    log = db_session.scalar(select(SourceIngestionLog).where(SourceIngestionLog.source_name == "understat"))
    assert log is not None
    assert log.status == "failed"
