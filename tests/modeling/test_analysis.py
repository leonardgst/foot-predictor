"""Analyses des ablations : courbe d'apport lue dans le rapport, figure, libellés des analyses descriptives."""

from __future__ import annotations

import pandas as pd
import pytest

from foot_predictor.modeling import analysis


def _comparison(a, b, mean, replaces=True):
    return {
        "a": a, "b": b,
        "log_loss": {"pooled": {"mean": mean, "low": mean - 0.001, "high": mean + 0.001}, "positive_folds": 4},
        "decision": {"b_replaces_a": replaces},
    }  # fmt: skip


REPORT = {
    "pooled": {"G0": {"log_loss": 1.90}, "G1": {"log_loss": 1.89}, "G2": {"log_loss": 1.88}},
    "comparisons": [
        _comparison("B0", "G0", 0.004), _comparison("B0", "G1", 0.013), _comparison("B0", "G2", 0.022),
        _comparison("G0", "G1", 0.009), _comparison("G1", "G2", 0.009, replaces=False),
    ],
}  # fmt: skip


def test_contribution_table_reads_cumulative_and_step_gains():
    table = analysis.contribution_table(REPORT, "B0", [("G0", "G0"), ("G1", "+ G1"), ("G2", "+ G2")])
    assert table["cumulative"].tolist() == pytest.approx([0.004, 0.013, 0.022])
    assert pd.isna(table.loc[0, "step"]) and table.loc[1, "step"] == pytest.approx(0.009)
    assert table["retained"].tolist()[1:] == [True, False]


def test_plot_contribution_writes_a_small_png(tmp_path):
    table = analysis.contribution_table(REPORT, "B0", [("G0", "G0"), ("G1", "+ G1"), ("G2", "+ G2")])
    path = analysis.plot_contribution(table, tmp_path / "courbe.png")
    assert path.read_bytes()[:4] == b"\x89PNG" and path.stat().st_size < 200_000


def test_round_buckets_and_league_formats():
    context = pd.DataFrame(
        {"round_number": [1, 6, 15, 30, None], "api_league_id": [61, 61, 39, 140, 78], "season_year": [2022, 2023, 2023, 2023, 2023]},
        index=[1, 2, 3, 4, 5],
    )  # fmt: skip
    assert analysis.round_bucket(context).tolist()[:4] == ["1-5", "6-10", "11-19", "20-99"]
    assert pd.isna(analysis.round_bucket(context).iloc[4])
    assert analysis.league_format(context).tolist()[:3] == ["Ligue 1, 20 clubs", "Ligue 1, 18 clubs", "Premier League"]


def test_closed_doors_effect_reads_fold_coefficients():
    report = {"folds": [{"name": "2021-22", "models": {"M": {"fitted": {"diagnostics": {
        "coefficients": {"is_home": 0.25, "home_x_closed": -0.15},
        "std_errors_cluster": {"is_home": 0.01, "home_x_closed": 0.05}}}}}}]}  # fmt: skip
    effect = analysis.closed_doors_effect(report, "M").iloc[0]
    assert effect["home_ratio_closed"] == pytest.approx(pytest.approx(2.718281828**0.10))
    assert effect["home_x_closed_low"] == pytest.approx(-0.15 - 0.098)
