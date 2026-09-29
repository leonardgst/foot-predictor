"""Chargeur football-data : appariement aux matchs API, matchs hors couverture, scellé des scores."""

from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data.download import season_dir
from foot_predictor.ingestion.load_api import COLUMNS, ApiLoad
from foot_predictor.ingestion.load_external import ExternalLoad
from tests.quality.test_raw_check import build_multi, synthetic

STAMP = dt.datetime(2026, 9, 29, tzinfo=dt.UTC)
HEADER = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\r\n"


def write_csv(directory, division, season, lines):
    raw_bytes.write_bytes(directory, season_dir(season), division, ".csv", (HEADER + "".join(lines)).encode(), STAMP)


@pytest.fixture
def loaded(tmp_path, multi_config):
    raw = tmp_path / "raw"
    p1 = [synthetic(1001, "2015-08-15", 1, 2, [11], [21]), synthetic(1002, "2015-08-22", 2, 1, [21], [11])]
    for item in p1:
        item["score"] = {"fulltime": {"home": 0, "away": 0}}  # score au temps réglementaire de l'API
    build_multi(raw, p1, []).queue.close()
    external = tmp_path / "externe"
    write_csv(
        external, "E0", 2015,
        [
            "E0,16/08/2015,Club Un,Club Deux,0,0\r\n",  # un jour d'écart (heure locale) : apparié
            "E0,22/08/2015,Club Deux,Club Un,1,0\r\n",  # apparié ; score différent de l'API (0-0)
            "E0,29/08/2015,Club Un,Club Deux,2,2\r\n",  # aucun match API : non apparié, jamais créé
        ],
    )  # fmt: skip
    write_csv(external, "E0", 2014, ["E0,16/08/2014,Club Un,Ancien Club,3,1\r\n"])  # hors couverture API
    api = ApiLoad(raw, multi_config)
    api.run()
    external_load = ExternalLoad(
        api, external, {"E0": 39}, teams={"Club Un": 1, "Club Deux": 2}, hors_api={"Ancien Club"},
        seasons=range(2014, 2016),
    )  # fmt: skip
    external_load.run()
    return api, external_load


def table(api, name):
    return [dict(zip(COLUMNS[name], row, strict=True)) for row in api.rows.tables[name]]


def test_covered_season_is_matched_never_created(loaded):
    api, external = loaded
    assert external.rates[("E0", 2015)] == (2, 3)
    assert [(u.date, u.reason) for u in external.unmatched] == [(dt.date(2015, 8, 29), "aucun match API à ± 1 jour")]
    mappings = {m["source_ref"]: m["match_id"] for m in table(api, "match_source_mapping")}
    fixture_of = {m["id"]: m["api_fixture_id"] for m in table(api, "match")}
    assert {ref: fixture_of[mid] for ref, mid in mappings.items() if ref.startswith("E0:2015")} == {
        "E0:2015:1": 1001,
        "E0:2015:2": 1002,
    }


def test_scores_compared_before_the_seal_only(loaded):
    _, external = loaded
    assert external.counts["scores_compared"] == 2
    assert external.score_mismatches == {("E0", 2015): 1}


def test_uncovered_season_creates_hors_api_match_and_team(loaded):
    api, external = loaded
    teams = {t["name"]: t for t in table(api, "team")}
    assert teams["Ancien Club"]["origin"] == "hors_api" and teams["Ancien Club"]["api_team_id"] is None
    (created,) = [m for m in table(api, "match") if m["origin"] == "hors_api"]
    assert (created["home_goals"], created["away_goals"], created["home_goals_90"]) == (3, 1, 3)
    assert created["api_fixture_id"] is None and created["status"] == "played"
    team_api = {t["id"]: t["api_team_id"] for t in table(api, "team")}
    assert team_api[created["home_team_id"]] == 1  # le même club que dans l'API : continuité (Elo)
    season = next(s for s in table(api, "season") if s["id"] == created["season_id"])
    assert season["year"] == 2014 and season["label"] == "2014-2015"
    assert external.counts["matches_hors_api"] == 1
    assert len([tm for tm in table(api, "team_match") if tm["match_id"] == created["id"]]) == 2


def test_source_mappings(loaded):
    api, _ = loaded
    assert {m["source_ref"] for m in table(api, "competition_source_mapping")} == {"E0"}
    assert {m["source_ref"] for m in table(api, "team_source_mapping")} == {"Club Un", "Club Deux", "Ancien Club"}
    assert all(m["source_name"] == "football_data" for m in table(api, "match_source_mapping"))


# --- Tirs de football-data (ADR-0029) : sans réseau et sans base -------------------------------

SHOTS_HEADER = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,HST,AST\r\n"


def shots_by_match(api) -> dict[int, dict[bool, tuple]]:
    """match_id -> {domicile?: (tirs, tirs cadrés)} depuis les lignes de team_match_stats_external."""
    side = {tm["id"]: (tm["match_id"], tm["is_home"]) for tm in table(api, "team_match")}
    out: dict[int, dict[bool, tuple]] = {}
    for row in table(api, "team_match_stats_external"):
        assert row["source"] == "football_data"
        match_id, is_home = side[row["team_match_id"]]
        out.setdefault(match_id, {})[is_home] = (row["shots"], row["shots_on_target"])
    return out


def test_old_file_without_shot_columns_gives_empty_values(loaded):
    """Colonnes absentes d'un ancien fichier : une ligne par équipe, valeurs vides, jamais 0."""
    api, external = loaded
    shots = shots_by_match(api)
    assert len(shots) == 3  # 2 matchs appariés + 1 match hors API ; le non apparié n'a rien
    assert all(values == {True: (None, None), False: (None, None)} for values in shots.values())
    assert external.counts["fd_shots_rows"] == 6
    assert external.counts["fd_shots_rows_incomplete"] == 6


@pytest.fixture
def loaded_with_shots(tmp_path, multi_config):
    raw = tmp_path / "raw"
    p1 = [synthetic(1001, "2015-08-15", 1, 2, [11], [21]), synthetic(1002, "2015-08-22", 2, 1, [21], [11])]
    build_multi(raw, p1, []).queue.close()
    external = tmp_path / "externe"
    rows = [
        "E0,15/08/2015,Club Un,Club Deux,0,0,14,9,6,3\r\n",  # complet
        "E0,22/08/2015,Club Deux,Club Un,1,0,11,,x,2\r\n",  # tirs extérieur vide, cadrés domicile illisible
    ]
    raw_bytes.write_bytes(external, season_dir(2015), "E0", ".csv", (SHOTS_HEADER + "".join(rows)).encode(), STAMP)
    raw_bytes.write_bytes(
        external, season_dir(2014), "E0", ".csv",
        (SHOTS_HEADER + "E0,16/08/2014,Club Un,Ancien Club,3,1,7,5,4,0\r\n").encode(), STAMP,
    )  # fmt: skip
    api = ApiLoad(raw, multi_config)
    api.run()
    external_load = ExternalLoad(
        api, external, {"E0": 39}, teams={"Club Un": 1, "Club Deux": 2}, hors_api={"Ancien Club"},
        seasons=range(2014, 2016),
    )  # fmt: skip
    external_load.run()
    return api, external_load


def test_shots_follow_the_home_and_away_sides(loaded_with_shots):
    api, _ = loaded_with_shots
    fixture_match = {m["api_fixture_id"]: m["id"] for m in table(api, "match") if m["api_fixture_id"]}
    shots = shots_by_match(api)
    assert shots[fixture_match[1001]] == {True: (14, 6), False: (9, 3)}


def test_empty_or_unreadable_values_stay_empty_never_zero(loaded_with_shots):
    api, external = loaded_with_shots
    fixture_match = {m["api_fixture_id"]: m["id"] for m in table(api, "match") if m["api_fixture_id"]}
    assert shots_by_match(api)[fixture_match[1002]] == {True: (11, None), False: (None, 2)}
    assert external.counts["fd_shots_rows_incomplete"] == 2


def test_hors_api_match_gets_its_shots(loaded_with_shots):
    """Un 0 lu dans le fichier reste un 0 : seule l'absence donne une valeur vide."""
    api, _ = loaded_with_shots
    (created,) = [m for m in table(api, "match") if m["origin"] == "hors_api"]
    assert shots_by_match(api)[created["id"]] == {True: (7, 4), False: (5, 0)}
