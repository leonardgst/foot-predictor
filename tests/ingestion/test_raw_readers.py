"""Lecteurs du brut : API (dernière version, lot le plus récent, `daily/` ignoré) et CSV football-data."""

from __future__ import annotations

import datetime as dt

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data.download import season_dir
from foot_predictor.ingestion import raw_api
from foot_predictor.ingestion.football_data_csv import parse_date, read_matches
from foot_predictor.rawstore.store import build_envelope, write_envelope

T1 = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
T2 = dt.datetime(2026, 9, 2, tzinfo=dt.UTC)


def store(raw_dir, rel_dir, stem, response, at):
    envelope = build_envelope(
        endpoint="/fixtures", params={}, fetched_at=at, http_status=200, headers_quota={}, body={"response": response}
    )
    write_envelope(raw_dir, rel_dir, stem, envelope, at)


def fixture(fid, home=1, away=2, status="FT", date="2024-08-17T14:00:00+00:00"):
    return {
        "fixture": {"id": fid, "date": date, "status": {"short": status}},
        "teams": {"home": {"id": home, "name": "H"}, "away": {"id": away, "name": "A"}},
    }


def test_latest_fixtures_list_wins(tmp_path):
    rel = "api_football/fixtures_list/league=39"
    store(tmp_path, rel, "season=2024", [fixture(1, status="NS")], T1)
    store(tmp_path, rel, "season=2024", [fixture(1, status="FT"), fixture(2)], T2)
    listed = raw_api.listed_fixtures(tmp_path, 39, 2024)
    assert [(f.fixture_id, f.status) for f in listed] == [(1, "FT"), (2, "FT")]
    assert listed[0].kickoff == dt.datetime(2024, 8, 17, 14, tzinfo=dt.UTC)
    assert raw_api.league_seasons(tmp_path) == [(39, 2024)]
    assert raw_api.fixtures_list(tmp_path, 39, 2023) == []


def test_fixture_in_two_batches_is_read_once_from_the_newest(tmp_path):
    rel = "api_football/fixtures_detail/league=39/season=2024"
    old, new = fixture(1), fixture(1)
    old["marker"], new["marker"] = "ancien", "récent"
    store(tmp_path, rel, "aaaaaaaaaaaa", [old, fixture(2)], T1)
    store(tmp_path, rel, "bbbbbbbbbbbb", [new], T2)
    items = {raw_api.fixture_id(i): i for i in raw_api.fixture_details(tmp_path, 39, 2024)}
    assert set(items) == {1, 2} and items[1]["marker"] == "récent"


def test_daily_lineups_are_never_read(tmp_path):
    store(tmp_path, "api_football/daily/2026-10-10/lineups", "x", [fixture(9)], T1)
    assert list(raw_api.fixture_details(tmp_path, 39, 2026)) == []
    assert raw_api.league_seasons(tmp_path) == []


def test_readers_write_nothing(tmp_path):
    before = sorted(p.as_posix() for p in tmp_path.rglob("*"))
    raw_api.fixtures_list(tmp_path, 39, 2024)
    list(raw_api.fixture_details(tmp_path, 39, 2024))
    read_matches(tmp_path, "E0", 2024)
    assert sorted(p.as_posix() for p in tmp_path.rglob("*")) == before


def test_parse_date():
    assert parse_date("16/08/2024") == dt.date(2024, 8, 16)
    assert parse_date("19/08/00") == dt.date(2000, 8, 19)
    assert parse_date("") is None


def test_read_matches_keeps_whole_rows_and_skips_blank_lines(tmp_path):
    csv = "﻿Div,Date,HomeTeam,AwayTeam,FTHG,B365H\r\nE0,16/08/2024,Equipe A,Equipe B,1,1.5\r\n,,,,,\r\n"
    raw_bytes.write_bytes(tmp_path, season_dir(2024), "E0", ".csv", csv.encode("utf-8"), T1)
    raw_bytes.write_bytes(tmp_path, season_dir(2024), "E0", ".csv", csv.replace("Equipe B", "Equipe C").encode(), T2)
    (match,) = read_matches(tmp_path, "E0", 2024)
    assert (match.date, match.home, match.away, match.line) == (dt.date(2024, 8, 16), "Equipe A", "Equipe C", 1)
    assert match.row["B365H"] == "1.5"
