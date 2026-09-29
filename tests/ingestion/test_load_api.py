"""Chargeur API vers staging, sur un brut synthétique (noms et identifiants fictifs), base de test."""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import text

from foot_predictor.ingestion.load import LoadRefused, check_target, write
from foot_predictor.ingestion.load_api import ApiLoad, match_status, number
from tests.quality.test_raw_check import build_multi, listing_of, profile, synthetic


def detail_with_extras(item: dict) -> dict:
    """Entraîneurs, formation, statistiques d'équipe et scores (temps réglementaire et final)."""
    item = copy.deepcopy(item)
    for lineup, coach in zip(item["lineups"], (9001, 9002), strict=True):
        lineup["coach"] = {"id": coach, "name": f"Entraîneur {coach}"}
        lineup["formation"] = "4-3-3"
    home, away = item["teams"]["home"]["id"], item["teams"]["away"]["id"]
    item["statistics"] = [
        {"team": {"id": home}, "statistics": [{"type": "Ball Possession", "value": "55%"}, {"type": "expected_goals", "value": "1.40"}]},
        {"team": {"id": away}, "statistics": [{"type": "Ball Possession", "value": "45%"}, {"type": "Total Shots", "value": 9}]},
    ]  # fmt: skip
    item["fixture"]["status"]["short"] = "AET"
    item["goals"] = {"home": 2, "away": 1}
    item["score"] = {"fulltime": {"home": 1, "away": 1}, "penalty": {"home": None, "away": None}}
    return item


@pytest.fixture
def raw(tmp_path):
    swapped_home, swapped_away = [51, 52, 53, 54, 55], [61, 62, 63, 64, 65]
    p1 = [
        detail_with_extras(synthetic(1001, "2015-08-15", 1, 2, [11, 12, 0, 501, 801], [21, 22])),
        synthetic(1002, "2015-08-22", 1, 2, [11, (603, 4), 802], [21], home_stats=[11, (603, 4), (603, 5), 802]),
        synthetic(1003, "2015-08-29", 1, 2, [11, (604, 4), (604, 5)], [21]),  # deux numéros dans la composition
        synthetic(1004, "2015-09-05", 1, 2, [11, 605], [21, 605]),  # deux équipes dans le match
        synthetic(
            1005, "2015-09-12", 1, 2, swapped_home, swapped_away, home_stats=swapped_away, away_stats=swapped_home
        ),
        synthetic(1006, "2015-09-19", 1, 2, [11, 606], [21], home_stats=[11, 606, 606]),  # entrée répétée
        synthetic(1007, "2015-09-26", 1, 2, [11, 701], [21]),
    ]
    p3 = [synthetic(3001, "2015-08-15", 3, 4, [501], [31], league=88)]  # 501 : deux équipes le même jour
    raw_dir = tmp_path / "raw"
    builder = build_multi(
        raw_dir, [], p3,
        profiles_p1=[profile(11, "1990-01-01"), profile(701, "1990-01-01"), profile(12, "1995-05-05")],
        profiles_p3=[profile(701, "1993-03-03")],  # 701 : deux dates la même saison, collision
    )  # fmt: skip
    listing = listing_of(p1)
    awarded = copy.deepcopy(listing[-1])
    awarded["fixture"] = {"id": 1099, "date": "2015-10-03T15:00:00+00:00", "status": {"short": "AWD"}}
    upcoming = copy.deepcopy(listing[-1])
    upcoming["fixture"] = {"id": 1100, "date": "2015-10-10T15:00:00+00:00", "status": {"short": "NS"}}
    missing = copy.deepcopy(listing[-1])  # terminé, mais absent des lots : lot incomplet
    missing["fixture"] = {"id": 1098, "date": "2015-10-01T15:00:00+00:00", "status": {"short": "FT"}}
    # Deux versions de la liste : la première (1001 encore « NS ») est remplacée par la seconde.
    older = copy.deepcopy(listing)
    older[0]["fixture"]["status"] = {"short": "NS"}
    builder.fixtures_list(39, older, tier="P1", season=2015)
    builder.fixtures_list(39, listing + [missing, awarded, upcoming], tier="P1", season=2015)
    builder.details(39, p1[:4], tier="P1", season=2015)
    builder.details(39, p1[4:], tier="P1", season=2015)
    builder.profiles(39, [profile(12, "1995-05-15")], season=2016)  # 12 : date corrigée la saison suivante
    builder.queue.close()
    return raw_dir


@pytest.fixture
def loaded(raw, multi_config):
    loader = ApiLoad(raw, multi_config, aliases={802: 801})
    loader.run()
    return loader


def ids_in(loader, table, column):
    index = __import__("foot_predictor.ingestion.load_api", fromlist=["COLUMNS"]).COLUMNS[table].index(column)
    return [row[index] for row in loader.rows.tables[table]]


def test_status_and_numbers():
    assert match_status("AET") == ("played", False, None)
    assert match_status("AWD") == ("cancelled", True, "tapis_vert")
    assert match_status("ABD") == ("cancelled", True, "abandonne")
    assert match_status("NS") == ("scheduled", False, None)
    assert (number("55%"), number("1.40"), number(None), number("n/a")) == (55.0, 1.4, None, None)


def test_entities_come_from_api_ids_only(loaded):
    players = set(ids_in(loaded, "player", "api_player_id"))
    assert 0 not in players  # identifiant 0 : joueur inconnu, non créé
    assert 802 not in players and 801 in players  # alias appliqué
    assert {603} <= players  # « deux numéros » résolu (2b) : créé
    assert not {604, 605, 701} & players  # non résolu, deux équipes, deux naissances : jamais une entrée gardée
    assert 501 not in players  # « même jour » dans ses deux seuls matchs
    assert set(ids_in(loaded, "coach", "api_coach_id")) == {9001, 9002}
    listed = [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1098, 1099, 1100, 3001]
    assert sorted(ids_in(loaded, "match", "api_fixture_id")) == listed
    statuses = dict(
        zip(ids_in(loaded, "match", "api_fixture_id"), ids_in(loaded, "match", "status_short"), strict=True)
    )
    assert statuses[1001] == "AET"  # la dernière version de la liste l'emporte


def test_collisions_and_unknowns_are_counted(loaded):
    c = loaded.counts
    assert c["lineup_unknown_entries"] == 1  # l'identifiant 0 de 1001
    assert c["collision_entries_resolved_2b"] == 1
    assert c["lineup_entries_excluded"] == 2 + 2 + 2 + 1  # 604 ×2, 605 ×2, 501 (un match P1, un P3), 701
    assert c["matches_excluded_tapis_vert"] == 1
    assert c["collision_ids_same_day"] == 1 and c["collision_ids_birth"] == 1
    # Critères de révision de l'ADR-0020 (la ligue 39 fait partie du top 5).
    assert c["top5_matches_with_excluded_entry"] == 4  # 1001 (501), 1003 (604), 1004 (605), 1007 (701)
    assert c["top5_matches_detailed"] == 7


def test_scores_birth_dates_and_team_from_lineup(loaded):
    cols = __import__("foot_predictor.ingestion.load_api", fromlist=["COLUMNS"]).COLUMNS
    match = {
        row[cols["match"].index("api_fixture_id")]: dict(zip(cols["match"], row, strict=True))
        for row in loaded.rows.tables["match"]
    }
    assert (match[1001]["home_goals"], match[1001]["home_goals_90"]) == (2, 1)  # final contre temps réglementaire
    assert match[1099]["excluded"] and match[1099]["exclusion_reason"] == "tapis_vert"
    assert match[1100]["status"] == "scheduled"
    player = {
        row[cols["player"].index("api_player_id")]: dict(zip(cols["player"], row, strict=True))
        for row in loaded.rows.tables["player"]
    }
    assert player[12]["birth_date"] == "1995-05-15"  # la plus récente en cas de correction
    assert player[11]["birth_date"] == "1990-01-01"
    # Statistiques inversées : l'équipe vient de la composition.
    team_of = {row[0]: row[cols["team"].index("api_team_id")] for row in loaded.rows.tables["team"]}  # interne -> API
    stats = [
        dict(zip(cols["player_match_stats"], row, strict=True)) for row in loaded.rows.tables["player_match_stats"]
    ]
    inv = {v: k for k, v in loaded.player_ids.items()}
    swapped = {inv[s["player_id"]]: team_of[s["team_id"]] for s in stats if inv[s["player_id"]] in range(51, 66)}
    assert all(team == (1 if pid < 60 else 2) for pid, team in swapped.items())
    tms = [dict(zip(cols["team_match_stats"], row, strict=True)) for row in loaded.rows.tables["team_match_stats"]]
    assert sorted(t["possession_pct"] for t in tms) == [45.0, 55.0]
    assert [t["expected_goals"] for t in tms if t["expected_goals"] is not None] == [1.4]


@pytest.mark.db
def test_write_is_deterministic_and_guarded(_test_engine, raw, multi_config):
    database = _test_engine.url.database
    try:
        first = ApiLoad(raw, multi_config, aliases={802: 801})
        first.run()
        prints_1 = write(_test_engine, first.rows, database)
        second = ApiLoad(raw, multi_config, aliases={802: 801})
        second.run()
        prints_2 = write(_test_engine, second.rows, database)
        assert prints_1 == prints_2
        assert prints_1["match"]["rows"] == 11 and prints_1["lineup"]["rows"] == first.counts["lineup"]
        with _test_engine.connect() as connection:
            xg = (
                connection.execute(text("SELECT xg_for FROM staging.team_match WHERE xg_for IS NOT NULL"))
                .scalars()
                .all()
            )
            assert [float(x) for x in xg] == [1.4]
            assert connection.execute(text("SELECT count(*) FROM staging.player WHERE api_player_id = 0")).scalar() == 0

        with pytest.raises(LoadRefused, match="confirmée"):
            write(_test_engine, first.rows, "autre_base")
        with _test_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO raw.source_ingestion_log (source_name, status) VALUES ('essai', 'ok')")
            )
        try:
            with _test_engine.connect() as connection, pytest.raises(LoadRefused, match="ancienne base"):
                check_target(connection, database)
        finally:
            with _test_engine.begin() as connection:
                connection.execute(text("DELETE FROM raw.source_ingestion_log WHERE source_name = 'essai'"))
    finally:
        with _test_engine.begin() as connection:
            connection.execute(
                text("TRUNCATE staging.competition, staging.team, staging.player, staging.coach CASCADE")
            )
