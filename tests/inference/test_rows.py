"""Lignes d'inférence : même fonction que l'entraînement, un jour à la fois, aucune fuite, aucun remplissage."""

from __future__ import annotations

import numpy as np
import pandas as pd

from foot_predictor.features.dataset import build_frame
from foot_predictor.inference.rows import POST_MATCH_COLUMNS, RowsCache, history_for_day, rows_for_day
from tests.features.test_dataset import COEF, PARAMS, synthetic_matches

KW = {"elo_params": PARAMS, "coefficients": COEF, "periods": None}


def reference(matches: pd.DataFrame) -> pd.DataFrame:
    """Le « jeu d'entraînement » synthétique : build_frame sur toute l'histoire."""
    return build_frame(matches, PARAMS, COEF)


def played_days(matches):
    return sorted(matches.loc[matches["status"] == "played", "match_day"].unique())


def test_a_rows_equal_the_training_rows_bit_for_bit_on_every_day():
    matches = synthetic_matches()
    full = reference(matches).drop(columns=list(POST_MATCH_COLUMNS))
    for day in played_days(matches):
        rows = rows_for_day(matches, day, **KW)
        expected = full[full["match_day"] == day].reset_index(drop=True)
        if expected.empty:
            assert rows.empty or rows["match_day"].ne(day).all()
            continue
        pd.testing.assert_frame_equal(rows.reset_index(drop=True), expected, check_dtype=True)


def test_b_fictitious_goals_and_later_matches_change_nothing():
    matches = synthetic_matches()
    day = played_days(matches)[5]
    base = rows_for_day(matches, day, **KW)
    changed = matches.copy()
    on_day = changed["match_day"] == day
    changed.loc[on_day, ["home_goals_90", "away_goals_90", "home_sot_fd"]] = [9, 7, 30]  # vrais résultats du jour J
    later = changed["match_day"] > day
    changed.loc[later, ["home_goals_90", "away_goals_90"]] = 5  # matchs postérieurs
    pd.testing.assert_frame_equal(rows_for_day(changed, day, **KW), base)


def test_b_targets_are_emptied_of_their_own_statistics():
    matches = synthetic_matches()
    day = played_days(matches)[3]
    targets = matches.loc[matches["match_day"] == day, "match_id"]
    history = history_for_day(matches, day, targets)
    target = history["match_id"].isin(targets)
    assert (history.loc[target, ["home_goals_90", "away_goals_90"]] == 0).all().all()
    assert history.loc[target, "home_shots_fd"].isna().all() and (history["match_day"] <= day).all()


def test_c_a_team_without_history_keeps_empty_rolling_values():
    matches = synthetic_matches()
    first_day = played_days(matches)[0]
    rows = rows_for_day(matches, first_day, **KW)
    assert len(rows) > 0 and rows["goals_for_ewm_h60"].isna().all()
    assert (rows["goals_weight_h60"] == 0).all()  # l'absence d'information se dit, elle ne se remplit pas


def test_an_upcoming_match_gets_rows_as_if_it_had_been_played():
    matches = synthetic_matches()
    upcoming = matches[matches["status"] != "played"].iloc[0]
    rows = rows_for_day(matches, upcoming["match_day"], [upcoming["match_id"]], **KW)
    assert set(rows["match_id"]) == {upcoming["match_id"]} and len(rows) == 2
    assert not any(c in rows.columns for c in POST_MATCH_COLUMNS)
    assert np.isfinite(rows["elo_pre"]).all()


def test_cup_matches_get_no_rows():
    matches = synthetic_matches()
    cup = matches[matches["competition_kind"] == "cup"].iloc[0]
    assert rows_for_day(matches, cup["match_day"], [cup["match_id"]], **KW).empty


def test_cache_reuses_a_day_and_distinguishes_data_versions(monkeypatch):
    matches = synthetic_matches()
    day = played_days(matches)[2]
    calls = []
    import foot_predictor.inference.rows as module

    real = module.rows_for_day
    monkeypatch.setattr(module, "rows_for_day", lambda m, d, **k: calls.append(d) or real(m, d, **KW))
    cache = RowsCache(matches, "v1")
    first, second = cache.rows(day), cache.rows(day)
    assert len(calls) == 1 and first is second and len(cache.timings) == 1
    RowsCache(matches, "v2").rows(day)
    assert len(calls) == 2


def test_check_compare_day_reports_identity_and_detects_a_difference():
    from foot_predictor.inference.check import compare_day

    matches = synthetic_matches()
    dataset = reference(matches)
    day = played_days(matches)[4]
    assert compare_day(matches, dataset, day, **KW)["identical"]
    tampered = dataset.copy()
    tampered.loc[tampered["match_day"] == day, "elo_pre"] += 1.0
    result = compare_day(matches, tampered, day, **KW)
    assert not result["identical"] and result["differing_columns"] == ["elo_pre"]
