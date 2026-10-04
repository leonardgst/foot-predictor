"""Sources du live (football-data superposé en mémoire) : appariement sans la date, superposition, fraîcheur
par championnat, noms inconnus jamais devinés, cotes de référence. Données synthétiques et fichiers écrits
à la main au format relevé sur le vrai fichier des prochains matchs (sous-étape 5.10)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data.live import FIXTURES_DIR
from foot_predictor.inference import live_sources as L
from foot_predictor.inference import predict as P
from foot_predictor.inference.availability import AVAILABLE, STALE, UNAVAILABLE
from foot_predictor.inference.models import LoadedModel
from foot_predictor.inference.rows import rows_for_day
from tests.inference.test_predict import KW, FakeModel, context, shifted_matches

SEASON = 2023
HEADER = "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,HST,AST,Avg>2.5,Avg<2.5"
FIXTURES_HEADER = "Div,Date,Time,HomeTeam,AwayTeam,Referee,B365>2.5,B365<2.5,Avg>2.5,Avg<2.5"


def name(team_id: int) -> str:
    return f"Club {team_id}"


def maps(matches: pd.DataFrame, missing: set[int] = frozenset()) -> L.TeamMaps:
    teams = set(matches["home_team_id"]) | set(matches["away_team_id"])
    return L.TeamMaps({"E0": 39, "E1": 40}, {name(t): int(t) for t in teams if t not in missing},
                      {int(t): int(t) for t in teams})  # fmt: skip


def london(match_date: pd.Timestamp) -> tuple[str, str]:
    local = match_date.tz_convert("Europe/London")
    return local.strftime("%d/%m/%Y"), local.strftime("%H:%M")


def result_line(match, *, home_goals=None, away_goals=None, date=None) -> str:
    day, time = london(match["match_date"])
    day = date or day
    goals = (home_goals if home_goals is not None else int(match["home_goals_90"]),
             away_goals if away_goals is not None else int(match["away_goals_90"]))  # fmt: skip
    shots = [match[c] for c in ("home_shots_fd", "away_shots_fd", "home_sot_fd", "away_sot_fd")]
    return ",".join([("E0" if match["api_league_id"] == 39 else "E1"), day, time, name(match["home_team_id"]),
                     name(match["away_team_id"]), str(goals[0]), str(goals[1]), *map(str, shots), "1.9", "1.9"])  # fmt: skip


def source(lines: list[str], header: str = HEADER, when: str = "2024-01-01T08:00:00") -> L.SourceFile:
    import csv
    import io

    rows = list(csv.DictReader(io.StringIO("\n".join([header, *lines]))))
    return L.SourceFile(rows, dt.datetime.fromisoformat(when).replace(tzinfo=dt.UTC), f"x__{when}.csv")


def round_robin_matches(seed: int = 1) -> pd.DataFrame:
    """Deux saisons (2022, 2023) d'une échelle anglaise en aller-retour : chaque affiche une fois par saison.

    Même schéma que `tests.features.test_dataset.synthetic_matches`, dont les affiches se répètent
    (clés ambiguës) : ici, un vrai calendrier de championnat, 4 équipes en D1 (39), 4 en D2 (40).
    """
    rng = np.random.default_rng(seed)
    rounds = [((0, 1), (2, 3)), ((0, 2), (1, 3)), ((0, 3), (1, 2))]
    rows, mid = [], 0
    for season in (2022, 2023):
        start = dt.date(season, 8, 6)
        for week in range(6):
            day = start + dt.timedelta(days=7 * week)
            for league, teams in ((39, [1, 2, 3, 4]), (40, [5, 6, 7, 8])):
                for a, b in rounds[week % 3]:
                    home, away = (teams[a], teams[b]) if week < 3 else (teams[b], teams[a])
                    mid += 1
                    goals = rng.integers(0, 4, 2)
                    rows.append({
                        "match_id": mid, "match_date": pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=15),
                        "match_day": day, "competition_id": {39: 1, 40: 2}[league], "api_league_id": league,
                        "competition_kind": "league", "season_year": season, "round": "Regular Season - 1",
                        "home_team_id": home, "away_team_id": away, "home_goals_90": goals[0],
                        "away_goals_90": goals[1], "status": "played", "excluded": False,
                        "home_shots_fd": int(rng.integers(5, 20)), "away_shots_fd": int(rng.integers(5, 20)),
                        "home_sot_fd": int(rng.integers(0, 5)), "away_sot_fd": int(rng.integers(0, 5)),
                        "is_regular_season": True, "origin": "api",
                    })  # fmt: skip
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def frozen():
    """Calendrier figé : les 4 derniers matchs joués de la Ligue 39, saison 2023, repassés « à venir »."""
    original = round_robin_matches()
    scope = original[(original["api_league_id"] == 39) & (original["season_year"] == SEASON)
                     & (original["status"] == "played")]  # fmt: skip
    after_freeze = scope.tail(4)
    table = original.copy()
    table.loc[after_freeze.index, "status"] = "scheduled"
    for column in ("home_goals_90", "away_goals_90", "home_shots_fd", "away_shots_fd", "home_sot_fd", "away_sot_fd"):
        table[column] = pd.to_numeric(table[column]).astype("Int64")
        table.loc[after_freeze.index, column] = pd.NA
    return original, table, original.loc[after_freeze.index]


def test_results_pair_without_the_date_and_rebuild_identical_rows(frozen):
    """Même fonction : avec les résultats de football-data égaux aux vrais, les lignes sont identiques."""
    original, table, played_later = frozen
    lines = [result_line(m) for _, m in played_later.iterrows()]
    live = L.overlay(table, maps(original), SEASON, [], {"E0": source(lines)}, today=dt.date(2024, 6, 30))
    assert live.counts["resultats_superposes"] == 4 and not live.issues
    target_day = played_later["match_day"].max()
    expected = rows_for_day(original, target_day, **KW)
    got = rows_for_day(live.matches, target_day, **KW)
    pd.testing.assert_frame_equal(got, expected, check_dtype=False)
    assert table["status"].eq("scheduled").sum() >= 4  # la table d'origine n'est pas modifiée


def test_a_match_already_played_in_staging_keeps_the_api_values(frozen):
    original, table, _ = frozen
    played = table[(table["api_league_id"] == 39) & (table["status"] == "played")].iloc[0]
    line = result_line(played, home_goals=9, away_goals=9)
    live = L.overlay(table, maps(original), int(played["season_year"]), [], {"E0": source([line])},
                     today=dt.date(2024, 6, 30))  # fmt: skip
    kept = live.matches[live.matches["match_id"] == played["match_id"]].iloc[0]
    assert (kept["home_goals_90"], kept["away_goals_90"]) == (played["home_goals_90"], played["away_goals_90"])


def test_the_date_does_not_enter_the_key_and_the_real_date_replaces_the_frozen_one(frozen):
    original, table, played_later = frozen
    match = played_later.iloc[0]
    moved = (match["match_day"] + dt.timedelta(days=3)).strftime("%d/%m/%Y")
    live = L.overlay(table, maps(original), SEASON, [], {"E0": source([result_line(match, date=moved)])},
                     today=dt.date(2024, 6, 30))  # fmt: skip
    row = live.matches[live.matches["match_id"] == match["match_id"]].iloc[0]
    assert row["status"] == "played" and row["match_day"] == match["match_day"] + dt.timedelta(days=3)


def test_an_ambiguous_key_is_never_resolved_at_random():
    matches = shifted_matches()  # avec le match à venir qui répète une affiche de la saison
    repeated = matches[(matches["api_league_id"] == 39) & (matches["status"] != "played")].iloc[0]
    line = result_line(repeated.fillna(0), home_goals=1, away_goals=0)
    live = L.overlay(matches, maps(matches), SEASON, [], {"E0": source([line])}, today=dt.date(2024, 6, 30))
    assert live.counts["resultats_superposes"] == 0 and "ambigu" in live.issues[0].reason
    assert live.freshness[39].complete_until <= repeated["match_day"] - dt.timedelta(days=1)


def test_play_offs_repeating_a_regular_season_fixture_do_not_make_the_key_ambiguous(frozen):
    original, table, played_later = frozen
    match = played_later.iloc[0]
    play_off = table[table["match_id"] == match["match_id"]].copy()
    play_off["match_id"], play_off["is_regular_season"] = 10_000, False
    play_off["round"] = "Promotion Play-offs - Final"
    with_play_off = pd.concat([table, play_off], ignore_index=True)
    live = L.overlay(with_play_off, maps(original), SEASON, [], {"E0": source([result_line(match)])},
                     today=dt.date(2024, 6, 30))  # fmt: skip
    assert not live.issues and live.counts["resultats_superposes"] == 1
    assert live.matches.set_index("match_id").at[10_000, "status"] == "scheduled"  # le barrage n'est pas touché


def test_kickoff_is_london_time_converted_to_utc():
    assert L.kickoff_utc(dt.date(2026, 10, 10), "15:00") == pd.Timestamp("2026-10-10 14:00", tz="UTC")  # BST
    assert L.kickoff_utc(dt.date(2027, 1, 16), "15:00") == pd.Timestamp("2027-01-16 15:00", tz="UTC")  # GMT
    assert L.kickoff_utc(dt.date(2027, 1, 16), "") is None and L.kickoff_utc(dt.date(2027, 1, 16), "15h") is None
    assert L.season_of(dt.date(2026, 8, 1)) == 2026 and L.season_of(dt.date(2027, 5, 30)) == 2026


def live_context(original, live, today):
    loaded = LoadedModel("essai", FakeModel(), {"version": "essai"}, None)
    return L.with_overlay(context(original, loaded, today=today), live)


def test_league_freshness_makes_a_match_stale_when_an_earlier_result_is_missing(frozen):
    original, table, played_later = frozen
    first, *rest = [m for _, m in played_later.iterrows()]
    lines = [result_line(m) for m in rest[:-1]]  # le premier match d'après le gel manque, le dernier est à prédire
    target = rest[-1]
    live = L.overlay(table, maps(original), SEASON, [], {"E0": source(lines)}, today=target["match_day"])
    assert live.freshness[39].complete_until == first["match_day"] - dt.timedelta(days=1)
    ctx = live_context(original, live, today=target["match_day"])
    (answer,) = P.predict_day(target["match_day"], "live", ctx, match_ids=[target["match_id"]])
    assert answer["status"] == UNAVAILABLE and answer["prediction"] is None
    assert any(v["status"] == STALE for v in answer["availability"]) and "football-data (live)" in answer["reasons"][0]

    complete = L.overlay(table, maps(original), SEASON, [], {"E0": source([result_line(first), *lines])},
                         today=target["match_day"])  # fmt: skip
    ctx = live_context(original, complete, today=target["match_day"])
    (answer,) = P.predict_day(target["match_day"], "live", ctx, match_ids=[target["match_id"]])
    assert (
        answer["status"] == AVAILABLE
        and answer["data_complete_until"] >= (target["match_day"] - dt.timedelta(days=1)).isoformat()
    )


def test_unknown_team_names_are_never_guessed(frozen):
    original, table, played_later = frozen
    target = played_later.iloc[-1]
    unknown = int(target["away_team_id"])
    team_maps = maps(original, missing={unknown})
    fixture = ",".join(["E0", *london(target["match_date"]), name(target["home_team_id"]), name(unknown), "",
                        "1.8", "2.0", "1.85", "1.95"])  # fmt: skip
    live = L.overlay(table, team_maps, SEASON, [source([fixture], FIXTURES_HEADER)], {}, today=target["match_day"])
    assert live.issues and "absente des YAML de rapprochement" in live.issues[0].reason
    assert "football_data_team_ids.yaml" in live.issues[0].reason
    assert int(target["match_id"]) in live.blocked
    ctx = live_context(original, live, today=target["match_day"])
    (answer,) = P.predict_day(target["match_day"], "live", ctx, match_ids=[target["match_id"]])
    assert answer["status"] == UNAVAILABLE and any("absente des YAML" in r for r in answer["reasons"])


def test_an_unusable_result_line_caps_the_league_freshness(frozen):
    original, table, played_later = frozen
    match = played_later.iloc[1]
    team_maps = maps(original, missing={int(match["home_team_id"])})
    live = L.overlay(table, team_maps, SEASON, [], {"E0": source([result_line(match)])}, today=dt.date(2024, 6, 30))
    assert live.freshness[39].complete_until <= match["match_day"] - dt.timedelta(days=1)
    assert live.counts["lignes_inutilisables"] == 1


def test_fixtures_give_the_real_kickoff_and_a_pre_closing_market_reference(frozen):
    original, table, played_later = frozen
    target = played_later.iloc[-1]
    kickoff = pd.Timestamp(dt.datetime.combine(target["match_day"], dt.time(19, 45)), tz="Europe/London")
    fixture = ",".join(["E0", kickoff.strftime("%d/%m/%Y"), "19:45", name(target["home_team_id"]),
                        name(target["away_team_id"]), "", "1.80", "2.00", "1.90", "1.90"])  # fmt: skip
    older = fixture.replace("19:45", "12:30")
    live = L.overlay(table, maps(original), SEASON, [source([older], FIXTURES_HEADER, "2024-01-01T08:00:00"),
                     source([fixture], FIXTURES_HEADER, "2024-01-02T08:00:00")], {}, today=target["match_day"])  # fmt: skip
    row = live.matches[live.matches["match_id"] == target["match_id"]].iloc[0]
    assert row["match_date"] == kickoff.tz_convert("UTC")  # la version la plus récente fait foi
    odds = live.odds.set_index("match_id").loc[int(target["match_id"])]
    assert odds["odds_column"] == "Avg" and odds["p_over"] == pytest.approx(0.5)
    assert odds["version"] == "avant_cloture"


def test_files_are_read_from_the_external_raw_dir_and_versions_change_the_data_version(frozen, tmp_path):
    original, table, played_later = frozen
    lines = "\r\n".join([HEADER, *[result_line(m) for _, m in played_later.iterrows()]]).encode()
    when = dt.datetime(2024, 1, 10, 8, tzinfo=dt.UTC)
    raw_bytes.write_bytes(tmp_path, f"football_data/csv/season={SEASON}", "E0", ".csv", b"\xef\xbb\xbf" + lines, when)
    first = L.load_overlay(table, tmp_path, maps(original), today=dt.date(2024, 1, 15))
    assert first.counts["resultats_superposes"] == 4 and first.freshness[39].last_update == when
    fixture = f"{FIXTURES_HEADER}\r\n".encode()
    raw_bytes.write_bytes(tmp_path, FIXTURES_DIR, "fixtures", ".csv", fixture, when + dt.timedelta(days=1))
    second = L.load_overlay(table, tmp_path, maps(original), today=dt.date(2024, 1, 15))
    assert first.data_version != second.data_version and second.data_version.startswith("fd-")


def test_with_overlay_combines_versions_and_empties_the_rows_cache(frozen):
    original, table, played_later = frozen
    live = L.overlay(table, maps(original), SEASON, [], {}, today=dt.date(2024, 1, 15))
    loaded = LoadedModel("essai", FakeModel(), {"version": "essai"}, None)
    base = context(original, loaded)
    base.rows_cache.rows(played_later.iloc[0]["match_day"])
    ctx = L.with_overlay(base, live)
    assert ctx.data_version == f"v-test+{live.data_version}" and ctx._rows is None
    assert ctx.matches is live.matches and ctx.league_freshness == live.freshness


def test_live_rehearsal_restores_goals_and_elo_after_a_simulated_freeze(tmp_path):
    from foot_predictor.inference.check import freeze_table, run_live_rehearsal

    original = round_robin_matches()
    season = original[(original["season_year"] == SEASON) & (original["api_league_id"] == 39)]
    days = sorted(season["match_day"].unique())
    freeze, today = days[2], days[5]
    frozen_table = freeze_table(original, freeze, SEASON)
    assert frozen_table.loc[frozen_table["match_day"] >= freeze, "home_goals_90"].isna().all()
    for division, league in (("E0", 39), ("E1", 40)):  # comme en vrai : un fichier par division suivie
        lines = [result_line(m) for _, m in original[original["season_year"] == SEASON].iterrows()
                 if m["api_league_id"] == league]  # fmt: skip
        data = "\r\n".join([HEADER, *lines]).encode()
        raw_bytes.write_bytes(tmp_path, f"football_data/csv/season={SEASON}", division, ".csv", data,
                              dt.datetime(2024, 1, 1, tzinfo=dt.UTC))  # fmt: skip
    report = run_live_rehearsal(original, tmp_path, maps(original), freeze=freeze, today=today)
    assert report["score_mismatches"] == 0 and not report["issues"] and report["same_matches"]
    assert report["results_restored"] == 12  # 2 championnats, 3 journées de 2 matchs entre le gel et ce jour
    assert report["goals_and_elo_identical"] and not report["differing_columns"]  # tirs identiques ici
