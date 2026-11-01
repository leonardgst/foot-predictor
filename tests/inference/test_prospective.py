"""Évaluation du journal prospectif H1 (ADR-0052) : traçage, appariement, B1 sans fuite, agrégats seulement."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.inference import prospective as pr
from foot_predictor.modeling.distributions import poisson_total

LABELS = [str(k) for k in range(10)] + ["10+"]


def distribution(lam: float = 2.7) -> dict:
    return dict(zip(LABELS, poisson_total(np.array([lam / 2]), np.array([lam / 2]))[0].tolist(), strict=True))


def row(match_id: int, day: dt.date, *, before: bool = True, fixture: int | None = None) -> dict:
    kickoff = pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=15)
    created = kickoff - pd.Timedelta(hours=5 if before else -2)
    return {
        "match_id": match_id,
        "api_fixture_id": fixture,
        "match_day": day,
        "kickoff_utc": kickoff,
        "created_at": created,
        "model_version": "essai",
        "total_distribution": distribution(),
    }


def history_matches(n_days: int = 10, per_day: int = 2) -> pd.DataFrame:
    """Matchs de la ligue 39 : des saisons passées (buts connus) puis `n_days` jours joués de la saison 2026."""
    rows, match_id = [], 1
    rng = np.random.default_rng(3)
    for season in (2023, 2024, 2025):
        for k in range(30):
            day = dt.date(season, 8, 1) + dt.timedelta(days=k)
            rows.append(_match(match_id, day, season, int(rng.integers(0, 4)), int(rng.integers(0, 3))))
            match_id += 1
    for k in range(n_days):
        day = dt.date(2026, 10, 1) + dt.timedelta(days=k)
        for _ in range(per_day):
            rows.append(_match(match_id, day, 2026, int(rng.integers(0, 4)), int(rng.integers(0, 3))))
            match_id += 1
    return pd.DataFrame(rows)


def _match(match_id: int, day: dt.date, season: int, home: int, away: int) -> dict:
    return {
        "match_id": match_id,
        "api_fixture_id": 9_000_000 + match_id,
        "match_day": day,
        "season_year": season,
        "api_league_id": 39,
        "is_regular_season": True,
        "status": "played",
        "home_goals_90": home,
        "away_goals_90": away,
    }


def journal_for(matches: pd.DataFrame, since: dt.date) -> list[dict]:
    recent = matches[matches["match_day"] >= since]
    return [row(int(m.match_id), m.match_day, fixture=int(m.api_fixture_id)) for m in recent.itertuples()]


def test_tracing_counts_days_and_separates_the_predictions_written_after_kickoff():
    day1, day2 = dt.date(2026, 10, 23), dt.date(2026, 10, 24)
    frame = pr.prediction_frame([row(1, day1), row(2, day1), row(3, day2), row(4, day2, before=False)])
    trace = pr.tracing(frame)
    assert trace["predictions"] == 4 and trace["before_kickoff"] == 3 and trace["after_or_unknown"] == 1
    assert trace["journees"] == 2 and trace["days"] == {"2026-10-23": 2, "2026-10-24": 1}
    assert pr.tracing(pd.DataFrame())["journees"] == 0


def test_results_are_matched_by_api_fixture_then_by_match_id_and_never_guessed():
    matches = history_matches(n_days=1, per_day=1)
    played = matches.iloc[-1]
    unplayed = matches.iloc[0:1].copy()
    unplayed["status"], unplayed["match_id"], unplayed["api_fixture_id"] = "scheduled", 777, 9_000_777
    unplayed["home_goals_90"] = unplayed["away_goals_90"] = np.nan
    table = pd.concat([matches, unplayed], ignore_index=True)
    frame = pr.prediction_frame(
        [
            row(999_999, dt.date(2026, 10, 1), fixture=int(played["api_fixture_id"])),  # par l'identifiant API
            row(int(played["match_id"]), dt.date(2026, 10, 1), fixture=None),  # par l'identifiant interne
            row(777, dt.date(2026, 10, 2), fixture=9_000_777),  # pas joué : aucun résultat
            row(888, dt.date(2026, 10, 2), fixture=None),  # inconnu : aucun résultat
        ]
    )
    total = float(played["home_goals_90"] + played["away_goals_90"])
    got = pr.attach_results(frame, table)["total"].tolist()
    assert got[0] == got[1] == total and np.isnan(got[2]) and np.isnan(got[3])


def test_b1_only_uses_matches_played_before_the_day():
    matches = history_matches(n_days=3, per_day=2)
    day = dt.date(2026, 10, 2)
    frame = pr.prediction_frame(
        [row(int(m.match_id), m.match_day) for m in matches[matches["match_day"] == day].itertuples()]
    )
    base = pr.b1_lambdas(matches, frame)
    changed = matches.copy()
    changed.loc[changed["match_day"] >= day, ["home_goals_90", "away_goals_90"]] = 9  # le jour même et après
    pd.testing.assert_frame_equal(pr.b1_lambdas(changed, frame), base)  # aucun effet : pas de fuite
    changed.loc[changed["match_day"] < day, "home_goals_90"] += 1  # la veille : effet
    assert not pr.b1_lambdas(changed, frame).equals(base)
    assert pr.b1_distribution(base).shape == (len(frame), pr.N_CATEGORIES)


def test_evaluate_gives_aggregates_and_waits_for_eight_journees_before_any_conclusion():
    matches = history_matches(n_days=10, per_day=3)
    short = pr.evaluate(journal_for(matches, dt.date(2026, 10, 7)), matches, dt.date(2026, 10, 31))  # 4 jours
    assert short["tracing"]["journees"] == 4 and not short["enough_journees"] and not short["conclusion_allowed"]
    assert short["with_result"] == 12 and short["scores"]["n"] == 12
    assert short["b1"]["n"] == 12 and short["b1"]["difference"]["n_blocks"] == 4
    full = pr.evaluate(journal_for(matches, dt.date(2026, 10, 1)), matches, dt.date(2026, 10, 31))  # 10 jours
    assert full["enough_journees"] and full["conclusion_allowed"]
    text = pr.render(short)
    assert "moins de 8 journées, aucune conclusion" in text and "Journées tracées : 4" in text
    assert "moins de 8 journées" not in pr.render(full)


def test_the_report_never_contains_a_match_level_value():
    matches = history_matches(n_days=2, per_day=2)
    report = pr.evaluate(journal_for(matches, dt.date(2026, 10, 1)), matches, dt.date(2026, 10, 31))
    text = repr(report)
    assert "match_id" not in text and "home_goals" not in text and "total_distribution" not in text
    assert set(report["scores"]) >= {"n", "log_loss", "rps", "coverage"}


def test_matches_without_result_are_counted_not_scored():
    matches = history_matches(n_days=2, per_day=2)
    matches.loc[matches["match_day"] == dt.date(2026, 10, 2), "status"] = "scheduled"
    report = pr.evaluate(journal_for(matches, dt.date(2026, 10, 1)), matches, dt.date(2026, 10, 31))
    assert report["with_result"] == 2 and report["without_result"] == 2


def test_an_empty_journal_gives_a_zero_report():
    report = pr.evaluate([], history_matches(1, 1), dt.date(2026, 10, 31))
    assert report["tracing"]["journees"] == 0 and report["with_result"] == 0 and report["b1"] is None
    assert "Journées tracées : 0" in pr.render(report)


@pytest.mark.parametrize("n", [3, 8])
def test_the_journee_threshold_is_the_e2_criterion(n):
    days = [dt.date(2026, 10, 1) + dt.timedelta(days=k) for k in range(n)]
    trace = pr.tracing(pr.prediction_frame([row(i, d) for i, d in enumerate(days)]))
    assert (trace["journees"] >= pr.JOURNEES_REQUIRED) == (n >= 8)
