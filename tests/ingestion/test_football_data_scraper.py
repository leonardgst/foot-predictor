"""Tests du téléchargement football-data.co.uk (`ingestion/football_data_scraper.py`) :
parsing du CSV brut (fonctions pures), appel HTTP mocké (jamais de vraie
requête vers football-data.co.uk), et idempotence de l'upsert en base
(`db`)."""
from __future__ import annotations

import requests
import pytest
from sqlalchemy import select

from foot_predictor.db.models import FootballDataMatch, SourceIngestionLog
from foot_predictor.ingestion import football_data_scraper as scraper


# ---------------------------------------------------------------------------
# Fonctions pures : season_code, parse_csv_content
# ---------------------------------------------------------------------------


def test_season_code_formats_start_and_end_year_on_two_digits():
    assert scraper.season_code(2024) == "2425"


def test_season_code_handles_century_rollover():
    assert scraper.season_code(1999) == "9900"


_CSV_HEADER = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"


def test_parse_csv_content_parses_realistic_row_into_expected_payload():
    csv_text = _CSV_HEADER + "E0,16/08/2024,Man United,Fulham,1,0,H\n"

    payloads = scraper.parse_csv_content(csv_text, "2024-2025")

    assert payloads == [
        {
            "div": "E0",
            "season_label": "2024-2025",
            "date": "2024-08-16",
            "home_team": "Man United",
            "away_team": "Fulham",
            "fthg": 1,
            "ftag": 0,
        }
    ]


def test_parse_csv_content_handles_two_digit_year_format():
    """Saisons anciennes : année sur 2 chiffres ('DD/MM/YY')."""
    csv_text = _CSV_HEADER + "E0,19/08/00,Charlton,Man City,4,0,H\n"

    payloads = scraper.parse_csv_content(csv_text, "2000-2001")

    assert payloads[0]["date"] == "2000-08-19"


def test_parse_csv_content_skips_blank_trailing_row():
    """football-data.co.uk termine fréquemment ses CSV par une ligne vide."""
    csv_text = _CSV_HEADER + "E0,16/08/2024,Man United,Fulham,1,0,H\n" + ",,,,,,\n"

    payloads = scraper.parse_csv_content(csv_text, "2024-2025")

    assert len(payloads) == 1


def test_parse_csv_content_missing_score_becomes_none():
    """Un match pas encore joué n'a pas de score renseigné dans le CSV."""
    csv_text = _CSV_HEADER + "E0,30/08/2025,Man United,Fulham,,,\n"

    payloads = scraper.parse_csv_content(csv_text, "2025-2026")

    assert payloads[0]["fthg"] is None
    assert payloads[0]["ftag"] is None


def test_parse_csv_content_raises_on_unrecognized_date_format():
    csv_text = _CSV_HEADER + "E0,2024-08-16,Man United,Fulham,1,0,H\n"

    with pytest.raises(ValueError, match="Format de date non reconnu"):
        scraper.parse_csv_content(csv_text, "2024-2025")


# ---------------------------------------------------------------------------
# fetch_division : appel HTTP mocké
# ---------------------------------------------------------------------------


def test_fetch_division_builds_expected_url_and_decodes_content(mocker):
    fake_response = mocker.Mock()
    fake_response.content = "Div,Date\r\nE0,16/08/2024\r\n".encode("utf-8-sig")
    fake_response.raise_for_status = mocker.Mock()
    mock_get = mocker.patch.object(scraper.requests, "get", return_value=fake_response)

    csv_text = scraper.fetch_division("E0", "2024-2025")

    mock_get.assert_called_once_with(
        "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
        headers={"User-Agent": scraper.USER_AGENT},
        timeout=30,
    )
    assert csv_text == "Div,Date\r\nE0,16/08/2024\r\n"
    fake_response.raise_for_status.assert_called_once()


def test_fetch_division_raises_on_http_error(mocker):
    fake_response = mocker.Mock()
    fake_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    mocker.patch.object(scraper.requests, "get", return_value=fake_response)

    with pytest.raises(requests.HTTPError):
        scraper.fetch_division("E0", "2024-2025")


# ---------------------------------------------------------------------------
# ingest_football_data_source : upsert idempotent + gestion d'erreur (db)
# ---------------------------------------------------------------------------

_TWO_MATCH_CSV = (
    _CSV_HEADER
    + "E0,16/08/2024,Man United,Fulham,1,0,H\n"
    + "E0,17/08/2024,Arsenal,Wolves,2,1,H\n"
)


@pytest.mark.db
def test_ingest_football_data_source_creates_rows_then_marks_unchanged_on_rerun(db_session, mocker):
    mocker.patch.object(scraper, "DIVISIONS", ["E0"])
    mocker.patch.object(scraper, "fetch_division", return_value=_TWO_MATCH_CSV)

    first_summary = scraper.ingest_football_data_source(db_session, "2024-2025")
    assert first_summary["E0"] == {"created": 2, "updated": 0, "unchanged": 0}
    assert db_session.scalar(select(FootballDataMatch)) is not None
    rows_after_first = db_session.scalars(select(FootballDataMatch)).all()
    assert len(rows_after_first) == 2

    second_summary = scraper.ingest_football_data_source(db_session, "2024-2025")
    assert second_summary["E0"] == {"created": 0, "updated": 0, "unchanged": 2}
    rows_after_second = db_session.scalars(select(FootballDataMatch)).all()
    assert len(rows_after_second) == 2  # pas de doublon


@pytest.mark.db
def test_ingest_football_data_source_updates_row_when_score_changes(db_session, mocker):
    mocker.patch.object(scraper, "DIVISIONS", ["E0"])
    mocker.patch.object(scraper, "fetch_division", return_value=_TWO_MATCH_CSV)
    scraper.ingest_football_data_source(db_session, "2024-2025")

    corrected_csv = _CSV_HEADER + "E0,16/08/2024,Man United,Fulham,2,0,H\n" + "E0,17/08/2024,Arsenal,Wolves,2,1,H\n"
    mocker.patch.object(scraper, "fetch_division", return_value=corrected_csv)

    summary = scraper.ingest_football_data_source(db_session, "2024-2025")

    assert summary["E0"] == {"created": 0, "updated": 1, "unchanged": 1}


@pytest.mark.db
def test_ingest_football_data_source_marks_division_failed_on_http_error(db_session, mocker):
    mocker.patch.object(scraper, "DIVISIONS", ["E0"])
    mocker.patch.object(
        scraper, "fetch_division", side_effect=requests.RequestException("timeout")
    )

    summary = scraper.ingest_football_data_source(db_session, "2024-2025")

    assert "error" in summary["E0"]
    log = db_session.scalar(select(SourceIngestionLog).where(SourceIngestionLog.source_name == "football-data"))
    assert log is not None
    assert log.status == "failed"
