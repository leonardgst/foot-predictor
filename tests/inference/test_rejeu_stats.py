"""Statistiques du rejeu H1 : collecte, mesures, B1 sans fuite, pentes, agrégats seulement."""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from foot_predictor.inference import rejeu_stats as rs
from foot_predictor.inference.__main__ import build_parser
from foot_predictor.modeling import metrics
from foot_predictor.modeling.distributions import poisson_total

LABELS = [str(k) for k in range(10)] + ["10+"]
RESAMPLES = 200


def answer(match_id: int, day: dt.date, *, league: int = 39, season: int = 2021, round_no: int = 1,
           score=(1, 2), status: str = "available", lam=(1.4, 1.2)) -> dict:  # fmt: skip
    total = poisson_total(np.array([lam[0]]), np.array([lam[1]]))[0]
    prediction = {
        "lambda_home": lam[0],
        "lambda_away": lam[1],
        "total_distribution": dict(zip(LABELS, total.tolist(), strict=True)),
    }
    return {
        "match_id": match_id,
        "api_league_id": league,
        "competition": {39: "Premier League", 61: "Ligue 1"}.get(league, str(league)),
        "season": season,
        "round": f"Regular Season - {round_no}",
        "date": day.isoformat(),
        "model_version": f"rejeu-{season}",
        "status": status,
        "prediction": prediction if status == "available" else None,
        "actual_score": None if score is None else {"home": score[0], "away": score[1]},
    }


def synthetic_frame(seasons=(2021, 2022, 2025), rounds=12, per_round=4, seed=5) -> pd.DataFrame:
    """Matchs de deux championnats, tirés d'une loi de Poisson ; l'avantage sur B1 croît avec la journée."""
    rng = np.random.default_rng(seed)
    answers, match_id = [], 1
    for season in seasons:
        for league in (39, 61):
            for round_no in range(1, rounds + 1):
                day = dt.date(season, 8, 1) + dt.timedelta(days=7 * round_no + (league == 61))
                for _ in range(per_round):
                    lam = (float(rng.uniform(0.8, 2.0)), float(rng.uniform(0.6, 1.6)))
                    score = (int(rng.poisson(lam[0])), int(rng.poisson(lam[1])))
                    answers.append(
                        answer(match_id, day, league=league, season=season, round_no=round_no, score=score, lam=lam)
                    )
                    match_id += 1
    frame, skipped = rs.answers_frame(answers)
    assert not skipped
    return frame


def with_b1(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["lambda_b1_home"], out["lambda_b1_away"] = 1.4, 1.1
    return out


def test_round_number():
    assert rs.round_number("Regular Season - 12") == 12.0
    assert rs.round_number("Regular Season - 3 ") == 3.0
    assert np.isnan(rs.round_number("Quarter-finals")) and np.isnan(rs.round_number(None))


def test_answers_frame_keeps_scored_predictions_and_counts_the_rest():
    day = dt.date(2022, 5, 1)
    answers = [
        answer(1, day),
        answer(2, day, status="unavailable"),
        answer(3, day, score=None),
        answer(4, day, status="out_of_scope", score=None),
    ]
    frame, skipped = rs.answers_frame(answers)
    assert frame["match_id"].tolist() == [1]
    assert dict(skipped) == {"unavailable": 1, "sans_score": 1, "out_of_scope": 1}
    row = frame.iloc[0]
    assert (row["home_goals"], row["away_goals"], row["match_day"]) == (1, 2, day)
    assert pytest.approx(sum(row[rs.P_COLUMNS]), abs=1e-12) == 1.0


def test_measures_match_the_protocol_metrics():
    frame = with_b1(synthetic_frame())
    out = rs.measures(frame)
    probs, totals = frame[rs.P_COLUMNS].to_numpy(float), (frame["home_goals"] + frame["away_goals"]).to_numpy(float)
    assert out["log_loss"].mean() == pytest.approx(metrics.log_loss_by_match(probs, totals).mean())
    assert out["rps"].mean() == pytest.approx(metrics.rps_by_match(probs, totals).mean())
    assert out["brier_over"].mean() == pytest.approx(metrics.brier_over_by_match(probs, totals).mean())
    assert np.allclose(out[["p_home", "p_draw", "p_away"]].sum(axis=1), 1.0)
    first = out.iloc[0]
    assert first["hit_over"] == ((first["p_over"] > 0.5) == (first["total"] > 2.5))
    assert out["delta_b1"].equals(out["log_loss_b1"] - out["log_loss"])
    assert set(out["period"]) == {"validation", "scelle"}
    assert (out.loc[out["season_year"] == 2025, "period"] == "scelle").all()


def test_measures_without_b1_leave_the_gap_empty():
    out = rs.measures(synthetic_frame())
    assert out["delta_b1"].isna().all()
    assert rs.summarize(out, RESAMPLES)["b1"] is None


def test_exactly_one_winner_per_match():
    out = rs.measures(synthetic_frame())
    # Le résultat réel est classé dans une seule des trois issues, et la part de bons vainqueurs est une fréquence.
    assert 0.0 <= out["hit_1x2"].mean() <= 1.0
    assert (out["brier_1x2"] >= 0).all() and (out["brier_1x2"] <= 2).all()


def test_progress_runs_from_first_to_last_round_and_completes_the_current_season():
    frame = synthetic_frame(seasons=(2021, 2022), rounds=12)
    # La saison 2022, la dernière, n'a que 6 journées jouées : elle prend le nombre de journées de la précédente.
    frame = frame[~((frame["season_year"] == 2022) & (frame["round"].map(rs.round_number) > 6))]
    out = rs.add_progress(frame)
    old = out[out["season_year"] == 2021]
    assert old["progress"].min() == 0.0 and old["progress"].max() == 1.0
    current = out[out["season_year"] == 2022]
    assert current["n_rounds"].unique().tolist() == [12.0]
    assert current["progress"].max() == pytest.approx(5 / 11)
    assert out.loc[out["round_no"] == 1, "tranche"].unique().tolist() == ["1-5"]
    assert set(out.loc[out["round_no"] == 11, "tranche"]) == {"11-19"}


def test_progress_uses_the_fallback_when_there_is_no_previous_season():
    out = rs.add_progress(synthetic_frame(seasons=(2026,), rounds=5))
    assert out.loc[out["api_league_id"] == 61, "n_rounds"].unique().tolist() == [34.0]
    assert out.loc[out["api_league_id"] == 39, "n_rounds"].unique().tolist() == [38.0]


def test_tranche_labels():
    assert [rs.tranche_label(r) for r in (1, 5, 6, 19, 20, 29, 30, 38)] == [
        "1-5",
        "1-5",
        "6-10",
        "11-19",
        "20-29",
        "20-29",
        "30+",
        "30+",
    ]
    assert rs.tranche_label(float("nan")) is None


def test_slope_interval_recovers_the_slope_and_is_deterministic():
    rng = np.random.default_rng(1)
    x = rng.uniform(0, 1, 600)
    y = 2.0 - 0.5 * x + rng.normal(0, 0.3, 600)
    blocks = rng.integers(0, 40, 600)
    first = rs.slope_interval(x, y, blocks, n_resamples=500)
    again = rs.slope_interval(x, y, blocks, n_resamples=500)
    assert first == again
    assert first["slope"] == pytest.approx(np.polyfit(x, y, 1)[0])
    assert first["low"] < -0.5 < first["high"] or abs(first["slope"] + 0.5) < 0.2
    assert first["low"] < first["slope"] < first["high"]
    assert first["n"] == 600 and first["n_blocks"] <= 40


def test_slope_interval_without_variation_in_x_is_none():
    assert rs.slope_interval(np.full(50, 0.3), np.arange(50.0), np.arange(50) % 5, n_resamples=50) is None


def test_trend_slope_needs_enough_matches():
    frame = rs.add_progress(rs.measures(with_b1(synthetic_frame(seasons=(2021,), rounds=3, per_round=2))))
    assert rs.trend_slope(frame, "log_loss", (), RESAMPLES) is None


def test_report_is_aggregated_and_coherent():
    frame = rs.add_progress(rs.measures(with_b1(synthetic_frame())))
    report = rs.build_report(frame, dt.date(2026, 11, 7), "load_run-7", {"unavailable": 2}, RESAMPLES)
    n = len(frame)
    assert sum(r["n"] for r in report["by_season"]) == n
    assert sum(r["n"] for r in report["by_league_season"]) == n
    assert [r["n"] for r in report["overall"]] == [
        int((frame["period"] == "validation").sum()),
        int((frame["period"] == "scelle").sum()),
        n,
    ]
    # Par championnat : validation, scellé, puis tout, dans cet ordre.
    assert [(r["group"]["api_league_id"], r["group"]["period"]) for r in report["by_league"]] == [
        (league, period) for league in (39, 61) for period in ("validation", "scelle", "tout")
    ]
    assert len(report["by_league_season"]) == 6
    # La saison 2025, la dernière, n'a que 12 journées sur 38 (ou 34) : elle sort des tranches et des pentes.
    assert report["trend_seasons"] == [2021, 2022]
    assert {(p["api_league_id"], p["season_year"]) for p in report["partial_seasons"]} == {(39, 2025), (61, 2025)}
    assert report["slope_summary"]["n_groups"] == 4
    kinds = [r["group"]["kind"] for r in report["slopes"]]
    assert kinds.count("tous") == 1 and kinds.count("championnat") == 2 and kinds.count("saison") == 4
    assert sum(r["n"] for r in report["tranches"]["tous"]) == int(frame["season_year"].isin([2021, 2022]).sum())
    # Agrégats seulement : aucune clé de match, aucun score.
    text = json.dumps(report)
    assert '"match_id"' not in text and "home_goals" not in text and "actual_score" not in text


def test_render_has_every_section_and_the_reading_rules():
    frame = rs.add_progress(rs.measures(with_b1(synthetic_frame())))
    markdown = rs.render(rs.build_report(frame, dt.date(2026, 11, 7), "load_run-7", {}, RESAMPLES))
    for heading in (
        "## Toutes saisons",
        "## Par championnat",
        "## Par saison",
        "## Par saison et par championnat",
        "## Lecture",
    ):
        assert heading in markdown
    assert "Premier League" in markdown and "Ligue 1" in markdown and "2025-26" in markdown
    assert "Seules 2025-26 et 2026-27 sont vierges" in markdown
    assert "ne prouve rien seul" in markdown


def test_b1_is_computed_without_looking_at_the_day_itself():
    """L'écart à B1 d'un match ne dépend pas des buts de ce match ni de ceux des jours suivants."""
    frame = synthetic_frame(seasons=(2021, 2022), rounds=4, per_round=2)
    rows = []
    for _, r in frame.iterrows():
        rows.append(
            {
                "match_id": int(r["match_id"]),
                "api_league_id": int(r["api_league_id"]),
                "season_year": int(r["season_year"]),
                "match_day": r["match_day"],
                "status": "played",
                "is_regular_season": True,
                "home_goals_90": float(r["home_goals"]),
                "away_goals_90": float(r["away_goals"]),
            }
        )
    matches = pd.DataFrame(rows)
    base = rs.add_b1(frame, matches)
    last_day = frame["match_day"].max()
    altered = matches.copy()
    altered.loc[altered["match_day"] == last_day, ["home_goals_90", "away_goals_90"]] = 9.0
    changed = rs.add_b1(frame, altered)
    assert base[["lambda_b1_home", "lambda_b1_away"]].equals(changed[["lambda_b1_home", "lambda_b1_away"]])


class FakeContext:
    def __init__(self, matches: pd.DataFrame):
        self.matches = matches


def test_collect_replays_each_played_day_of_the_scope_once():
    day1, day2 = dt.date(2022, 1, 8), dt.date(2022, 1, 15)
    matches = pd.DataFrame(
        {
            "match_day": [day1, day1, day2, dt.date(2020, 5, 1), day2],
            "api_league_id": [39, 39, 61, 39, 2],
            "competition_id": [1, 1, 5, 1, 9],
            "is_regular_season": [True, True, True, True, False],
            "status": ["played", "played", "played", "played", "played"],
            "season_year": [2021, 2021, 2021, 2019, 2021],
        }
    )
    calls = []

    def fake_predict(day, mode, context, competition_ids, horizon):
        calls.append((day, mode, tuple(competition_ids), horizon))
        return [answer(len(calls), day, league=39)]

    frame, excluded = rs.collect(FakeContext(matches), since_season=2021, predict=fake_predict)
    assert calls == [(day1, "replay", (1, 5), "H1"), (day2, "replay", (1, 5), "H1")]
    assert len(frame) == 2 and not excluded


def test_command_is_declared():
    args = build_parser().parse_args(["rejeu-stats", "--since-season", "2026", "--resamples", "50"])
    assert (args.command, args.since_season, args.resamples, args.from_file) == ("rejeu-stats", 2026, 50, None)


def test_tranches_are_listed_in_round_order():
    frame = rs.add_progress(rs.measures(with_b1(synthetic_frame(seasons=(2021,), rounds=38, per_round=2))))
    report = rs.build_report(frame, dt.date(2026, 11, 7), "load_run-7", {}, RESAMPLES)
    assert [r["group"]["tranche"] for r in report["tranches"]["tous"]] == ["1-5", "6-10", "11-19", "20-29", "30+"]


def test_a_gap_over_too_few_days_has_no_interval():
    one_league = synthetic_frame(seasons=(2021,), rounds=3, per_round=4).query("api_league_id == 39")
    frame = rs.measures(with_b1(one_league))
    few = rs.delta_interval(frame, RESAMPLES)
    assert few["low"] is None and few["high"] is None and few["n_blocks"] < rs.MIN_BLOCKS
    many = rs.delta_interval(rs.measures(with_b1(synthetic_frame(seasons=(2021,), rounds=12))), RESAMPLES)
    assert many["low"] is not None and many["low"] < many["mean"] < many["high"]
    assert "pas d'intervalle" in rs._delta({"delta": few})


def test_a_season_in_progress_is_flagged_and_left_out_of_the_trend():
    frame = rs.add_progress(rs.measures(with_b1(synthetic_frame(seasons=(2021, 2022), rounds=38, per_round=1))))
    assert frame["season_complete"].all()
    short = frame[~((frame["season_year"] == 2022) & (frame["round_no"] > 8))]
    flagged = rs.add_progress(short)
    assert flagged.loc[flagged["season_year"] == 2022, "season_complete"].eq(False).all()
    assert flagged.loc[flagged["season_year"] == 2021, "season_complete"].all()
    markdown = rs.render(rs.build_report(flagged, dt.date(2026, 11, 7), "load_run-7", {"excluded": 2}, RESAMPLES))
    assert "Saisons terminées seulement" in markdown and "2022-23" in markdown and "8 journées sur 38" in markdown
    assert "2 exclu(s) du jeu" in markdown
