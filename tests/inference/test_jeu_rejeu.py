"""Jeu de données du rejeu H1 : lignes, fusion, mise à jour incrémentale, garde de modèle, tracé live (ADR-0054)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.inference import jeu_rejeu as jr
from foot_predictor.inference import rejeu_stats as rs
from foot_predictor.inference.__main__ import build_parser
from foot_predictor.modeling.distributions import poisson_total

LABELS = [str(k) for k in range(10)] + ["10+"]
TEAMS = {1: "Arsenal", 2: "Chelsea", 3: "Lyon", 4: "Lille"}
VARIABLES = ("is_home", "api_league_id", "elo_pre", "opp_elo_pre", "goals_for_ewm_h240")


def availability(home_elo: float, away_elo: float) -> list[dict]:
    rows = []
    for side, elo, opp in (("domicile", home_elo, away_elo), ("exterieur", away_elo, home_elo)):
        values = {"is_home": side == "domicile", "api_league_id": 39, "elo_pre": elo, "opp_elo_pre": opp}
        values["goals_for_ewm_h240"] = 1.0 + elo / 2000
        rows += [{"variable": v, "side": side, "status": "present", "value": values[v]} for v in VARIABLES]
    return rows


def answer(match: pd.Series, *, model: str | None = None, score="auto", status="available") -> dict:
    lam = (1.4 + match["match_id"] / 100, 1.1)
    total = poisson_total(np.array([lam[0]]), np.array([lam[1]]))[0]
    if score == "auto":
        score = {"home": int(match["home_goals_90"]), "away": int(match["away_goals_90"])}
    return {
        "match_id": int(match["match_id"]),
        "api_league_id": int(match["api_league_id"]),
        "competition": "Premier League",
        "season": int(match["season_year"]),
        "round": f"Regular Season - {int(match['match_id'])}",
        "date": match["match_day"].isoformat(),
        "kickoff_utc": f"{match['match_day'].isoformat()}T15:00:00+00:00",
        "home_team": TEAMS[int(match["home_team_id"])],
        "away_team": TEAMS[int(match["away_team_id"])],
        "model_version": model or f"rejeu-{int(match['season_year'])}",
        "data_version": "load_run-7+fd-test",
        "status": status,
        "availability": availability(1500.0 + match["match_id"], 1480.0),
        "prediction": None
        if status != "available"
        else {
            "lambda_home": lam[0],
            "lambda_away": lam[1],
            "total_distribution": dict(zip(LABELS, total.tolist(), strict=True)),
            "interval": {"low": 1, "high": 5, "announced_coverage": 0.8123456789012345},
        },
        "actual_score": score,
    }


def matches_table(rows: list[tuple]) -> pd.DataFrame:
    """rows : (match_id, jour, domicile, extérieur, buts dom., buts ext., statut)."""
    return pd.DataFrame(
        [
            {
                "match_id": mid,
                "match_day": day,
                "api_league_id": 39,
                "competition_id": 1,
                "is_regular_season": True,
                "status": status,
                "season_year": 2021,
                "home_team_id": home,
                "away_team_id": away,
                "api_fixture_id": 900 + mid if mid % 2 else np.nan,
                "home_goals_90": hg,
                "away_goals_90": ag,
            }
            for mid, day, home, away, hg, ag, status in rows
        ]
    )


class FakeContext:
    def __init__(self, matches: pd.DataFrame):
        self.matches = matches
        self.team_names = TEAMS
        self.data_version = "load_run-7+fd-test"


class Replayer:
    """Remplace `predict_day` : une réponse par match joué du jour ; garde la trace des jours demandés."""

    def __init__(self, context: FakeContext, model: str | None = None, unscored=()):
        self.context, self.model, self.unscored, self.days = context, model, set(unscored), []

    def __call__(self, day, mode, context, competition_ids, horizon):
        assert (mode, horizon) == ("replay", "H1")
        self.days.append(day)
        part = self.context.matches[self.context.matches["match_day"] == day]
        return [
            answer(m, model=self.model, score=None if m["match_id"] in self.unscored else "auto")
            for _, m in part.iterrows()
        ]


D1, D2, D3 = dt.date(2021, 8, 14), dt.date(2021, 8, 21), dt.date(2021, 8, 28)
FIRST = [(1, D1, 1, 2, 2, 1, "played"), (2, D1, 3, 4, 0, 0, "played"), (3, D2, 2, 1, 1, 3, "played")]


def run(context, path, **kwargs):
    replayer = kwargs.pop("predict", None) or Replayer(context)
    found = jr.update(context, kwargs.pop("journal", []), path, predict=replayer, **kwargs)
    return found, replayer


# ------------------------------------------------------------------------------ lignes


def test_answers_frame_gives_one_row_with_variables_of_both_sides_and_counts_the_rest():
    context = FakeContext(matches_table(FIRST))
    part = context.matches
    answers = [
        answer(part.iloc[0]),
        answer(part.iloc[1], status="unavailable"),
        answer(part.iloc[2], score=None),
    ]
    frame, skipped = jr.answers_frame(answers)
    assert len(frame) == 1 and dict(skipped) == {"unavailable": 1, "sans_score": 1}
    row = frame.iloc[0]
    assert (row["home_team"], row["away_team"], row["season"], row["match_day"]) == (
        "Arsenal",
        "Chelsea",
        "2021-22",
        D1,
    )
    assert (row["home_goals"], row["away_goals"]) == (2, 1)
    # les variables : celles des deux lignes du modèle ; ni `is_home` ni `api_league_id`, qui ont leur colonne
    assert row["home_elo_pre"] == 1501.0 and row["away_elo_pre"] == 1480.0
    assert row["home_opp_elo_pre"] == row["away_elo_pre"] and row["away_opp_elo_pre"] == row["home_elo_pre"]
    assert not {"home_is_home", "away_is_home", "home_api_league_id", "away_api_league_id"} & set(frame.columns)
    assert pytest.approx(row[rs.P_COLUMNS].sum(), abs=1e-12) == 1.0
    assert (row["interval_low"], row["interval_high"]) == (1, 5)


def test_pending_days_are_the_days_of_the_matches_missing_from_the_file():
    context = FakeContext(matches_table(FIRST))
    scope = jr.keyed_scope(context)
    assert jr.pending_days(scope, set()) == [D1, D2]
    done = {(D1, 39, "Arsenal", "Chelsea"), (D1, 39, "Lyon", "Lille")}
    assert jr.pending_days(scope, done) == [D2]
    assert jr.pending_days(scope, done | {(D2, 39, "Chelsea", "Arsenal")}) == []


def test_merge_replaces_a_row_with_the_same_key_and_sorts_by_day():
    context = FakeContext(matches_table(FIRST))
    old, _ = jr.answers_frame(Replayer(context)(D2, "replay", context, [1], "H1"))
    new, _ = jr.answers_frame(Replayer(context)(D1, "replay", context, [1], "H1"))
    old = old.drop(columns=["match_id"])
    changed = new.copy()
    changed["home_goals"] = 9
    merged = jr.merge(pd.concat([old, new.drop(columns=["match_id"])], ignore_index=True), changed)
    assert merged["match_day"].tolist() == [D1, D1, D2]
    assert "match_id" not in merged.columns
    assert merged[merged["match_day"] == D1]["home_goals"].tolist() == [9, 9]
    assert merged[merged["match_day"] == D2]["home_goals"].tolist() == [1]


def test_models_may_not_change_inside_a_season():
    context = FakeContext(matches_table(FIRST))
    part = context.matches
    old, _ = jr.answers_frame([answer(part.iloc[0])])
    same, _ = jr.answers_frame([answer(part.iloc[1])])
    other, _ = jr.answers_frame([answer(part.iloc[1], model="rejeu-autre")])
    jr.check_models(old, same)
    jr.check_models(pd.DataFrame(), other)
    with pytest.raises(jr.ModelChanged, match="2021-22"):
        jr.check_models(old, other)


def test_traced_keys_match_by_api_fixture_then_by_internal_id_and_only_before_kickoff():
    context = FakeContext(matches_table(FIRST))
    scope = jr.keyed_scope(context)  # matchs 1 et 3 : identifiant API 901 et 903 ; match 2 : sans identifiant API
    day = dt.datetime(2021, 8, 14, tzinfo=dt.UTC)

    def entry(match_id, fixture, created):
        return {
            "match_id": match_id, "api_fixture_id": fixture, "match_day": D1, "kickoff_utc": day + dt.timedelta(hours=15),
            "created_at": day + dt.timedelta(hours=created), "model_version": "m",
            "total_distribution": dict.fromkeys(LABELS, 1 / 11),
        }  # fmt: skip

    rows = [
        entry(77, 901, 9),  # identifiant interne périmé, identifiant API bon : apparié au match 1
        entry(2, None, 10),  # sans identifiant API : apparié par l'identifiant interne (match 2)
        entry(3, 903, 18),  # écrit après le coup d'envoi : ne compte pas
    ]
    assert jr.traced_keys(scope, rows) == {(D1, 39, "Arsenal", "Chelsea"), (D1, 39, "Lyon", "Lille")}
    assert jr.traced_keys(scope, []) == set()


def test_derived_columns_listed_for_the_reader_are_exactly_those_recomputed():
    context = FakeContext(matches_table(FIRST))
    frame, _ = jr.answers_frame([answer(m) for _, m in context.matches.iterrows()])
    frame["lambda_b1_home"], frame["lambda_b1_away"] = 1.4, 1.1
    base = set(frame.columns)
    out = jr.with_derived(frame.drop(columns=["match_id"]), set())
    assert set(out.columns) - base == set(jr.DERIVED)
    assert list(out.columns[: len(jr.IDENTITY)]) == jr.IDENTITY
    assert out["traced_live"].dtype == bool and not out["traced_live"].any()


# ------------------------------------------------------------------------------ fichier et mise à jour


def test_first_run_writes_every_played_match_with_variables_predictions_score_and_measures(tmp_path):
    context = FakeContext(matches_table([(0, dt.date(2021, 8, 7), 1, 2, 1, 1, "played"), *FIRST]))
    path = tmp_path / "jeu.csv"
    found, replayer = run(context, path, max_days=0)
    assert replayer.days == [dt.date(2021, 8, 7), D1, D2]
    assert (found["added"], found["total"], found["written"]) == (4, 4, True)
    csv = pd.read_csv(path)
    assert len(csv) == 4 and "match_id" not in csv.columns
    for column in (
        "home_elo_pre",
        "away_goals_for_ewm_h240",
        "lambda_home",
        "p10",
        "home_goals",
        "log_loss",
        "delta_b1",
    ):
        assert column in csv.columns
    assert csv["delta_b1"].isna().sum() == 1  # le premier jour n'a aucun historique pour B1
    assert path.with_suffix(".meta.json").exists()
    assert not path.with_name("jeu.csv.tmp").exists()


def test_a_second_run_without_new_result_replays_nothing_and_keeps_the_file(tmp_path):
    context = FakeContext(matches_table(FIRST))
    path = tmp_path / "jeu.csv"
    run(context, path, max_days=0)
    before = path.read_bytes()
    found, replayer = run(context, path)
    assert replayer.days == [] and found["added"] == 0 and found["total"] == 3
    assert path.read_bytes() == before  # relecture exacte : floats, bool, texte


def test_a_new_result_replays_only_its_day_and_adds_one_row(tmp_path):
    path = tmp_path / "jeu.csv"
    run(FakeContext(matches_table(FIRST)), path, max_days=0)
    first = pd.read_csv(path)
    grown = FakeContext(matches_table([*FIRST, (4, D3, 4, 3, 2, 2, "played")]))
    found, replayer = run(grown, path)
    assert replayer.days == [D3]
    assert (found["added"], found["total"]) == (1, 4)
    second = pd.read_csv(path)
    assert second["match_day"].tolist() == sorted(second["match_day"])
    old = second[second["match_day"] < str(D3)].drop(columns=["season_complete", "n_rounds", "progress"])
    assert old.equals(first.drop(columns=["season_complete", "n_rounds", "progress"]))  # lignes anciennes inchangées


def test_a_match_without_score_stays_pending_until_its_result_arrives(tmp_path):
    path = tmp_path / "jeu.csv"
    context = FakeContext(matches_table(FIRST))
    run(context, path, max_days=0, predict=Replayer(context, unscored={3}))
    assert len(pd.read_csv(path)) == 2
    found, replayer = run(context, path)  # le score est arrivé
    assert replayer.days == [D2] and found["added"] == 1 and found["total"] == 3


def test_too_many_days_are_refused_without_writing(tmp_path):
    path = tmp_path / "jeu.csv"
    with pytest.raises(jr.TooManyDays, match="--max-days 0"):
        run(FakeContext(matches_table(FIRST)), path, max_days=1)
    assert not path.exists()


def test_a_changed_model_stops_the_update_unless_everything_is_rebuilt(tmp_path):
    path = tmp_path / "jeu.csv"
    context = FakeContext(matches_table(FIRST))
    run(context, path, max_days=0)
    grown = FakeContext(matches_table([*FIRST, (4, D3, 4, 3, 2, 2, "played")]))
    before = path.read_bytes()
    with pytest.raises(jr.ModelChanged):
        run(grown, path, predict=Replayer(grown, model="rejeu-autre"))
    assert path.read_bytes() == before
    found, replayer = run(grown, path, rebuild=True, max_days=0, predict=Replayer(grown, model="rejeu-autre"))
    assert replayer.days == [D1, D2, D3] and found["total"] == 4
    assert set(pd.read_csv(path)["model_version"]) == {"rejeu-autre"}


def test_traced_live_is_refreshed_on_each_run(tmp_path):
    path = tmp_path / "jeu.csv"
    context = FakeContext(matches_table(FIRST))
    run(context, path, max_days=0)
    assert not pd.read_csv(path)["traced_live"].any()
    day = dt.datetime(2021, 8, 14, tzinfo=dt.UTC)
    journal = [
        {
            "match_id": 1, "api_fixture_id": 901, "match_day": D1, "kickoff_utc": day + dt.timedelta(hours=15),
            "created_at": day + dt.timedelta(hours=8), "model_version": "m",
            "total_distribution": dict.fromkeys(LABELS, 1 / 11),
        }
    ]  # fmt: skip
    run(context, path, journal=journal)
    csv = pd.read_csv(path)
    assert csv.loc[csv["home_team"] == "Arsenal", "traced_live"].tolist() == [True]
    assert csv["traced_live"].sum() == 1


def test_command_is_declared():
    args = build_parser().parse_args(["jeu-rejeu", "--rebuild", "--max-days", "0", "--output", "x.csv"])
    assert (args.command, args.rebuild, args.max_days, args.output) == ("jeu-rejeu", True, 0, "x.csv")
    default = build_parser().parse_args(["jeu-rejeu"])
    assert (default.rebuild, default.max_days, default.output) == (False, jr.DEFAULT_MAX_DAYS, None)
