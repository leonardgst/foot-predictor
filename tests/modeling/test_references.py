"""Références B0, B1 et marché : propriétés théoriques, marge retirée, exécution avec un marché. Sans base."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from scipy.stats import poisson

from foot_predictor.modeling import experiment, protocol
from foot_predictor.modeling.models import market
from foot_predictor.modeling.models.references import B0, B1
from tests.modeling.test_protocol import synthetic_rows


def test_b0_reproduces_the_training_mean_and_predicts_poisson_of_twice_it():
    data = synthetic_rows()
    fold = protocol.Fold(2021)
    b0 = protocol.select_and_fit(B0, [{}], data, fold, "top5").model
    train = data[data["season_year"].between(2015, 2020) & (data["api_league_id"] == 39)]
    assert b0.mu_ == pytest.approx(train["goals_for"].mean())
    predicted, _ = protocol.predict_fold(protocol.FitResult(b0, {}, 0), data, fold)
    assert predicted.total[0, :10] == pytest.approx(poisson.pmf(np.arange(10), 2 * b0.mu_))
    assert np.allclose(predicted.total, predicted.total[0])  # la même loi pour tous les matchs


def test_b1_uses_the_league_and_side_means_of_the_last_seasons():
    data = synthetic_rows()
    fold = protocol.Fold(2021)
    b1 = protocol.select_and_fit(B1, [{"window": 2}], data, fold, "top5").model
    recent = data[data["season_year"].between(2019, 2020) & (data["api_league_id"] == 39)]
    assert b1.means_[(39, True)] == pytest.approx(recent.loc[recent["is_home"], "goals_for"].mean())
    assert b1.means_[(39, False)] == pytest.approx(recent.loc[~recent["is_home"], "goals_for"].mean())


def test_b1_refuses_an_empty_window():
    with pytest.raises(ValueError):
        B1(window=0)


def test_market_probability_removes_the_margin():
    odds = market.market_probabilities(
        pd.DataFrame({"match_id": [1, 2], "version": "avant_cloture", "odds_over_2_5": [1.9, 1.5],
                      "odds_under_2_5": [1.9, 2.6]})
    )  # fmt: skip
    assert odds["p_over"].tolist() == pytest.approx([0.5, (1 / 1.5) / (1 / 1.5 + 1 / 2.6)])
    assert market.probabilities(odds, "avant_cloture", [2, 1]).tolist() == pytest.approx(odds["p_over"][::-1].tolist())


SPEC = """
name: marche
folds: [2021, 2022]
seed: 3
n_resamples: 200
models:
  - {id: B0, model: b0}
  - {id: B1, model: b1, grid: {window: [1, 3]}}
  - {id: marche, model: market, params: {version: avant_cloture}}
comparisons:
  - [B0, B1]
  - [B0, marche]
"""


def test_market_is_compared_on_the_over_2_5_event_only(tmp_path):
    data = synthetic_rows(matches_per_season=60)
    ids = np.sort(data["match_id"].unique())[::2]  # la moitié des matchs a une cote
    odds = market.market_probabilities(
        pd.DataFrame({"match_id": ids, "version": "avant_cloture", "odds_over_2_5": 1.9, "odds_under_2_5": 1.9})
    )
    path = tmp_path / "marche.yaml"
    path.write_text(SPEC, encoding="utf-8")
    report = experiment.run_experiment(
        path, reports_dir=tmp_path, predictions_dir=tmp_path, data=data, manifest={}, odds=odds,
        now=dt.datetime(2026, 9, 30, tzinfo=dt.UTC),
    )  # fmt: skip
    assert report["status"] == "ok", report.get("error")
    fold = report["folds"][0]
    assert 0 < fold["over_2_5_matches"] < fold["intersection"]
    assert fold["excluded_without_odds"] == fold["intersection"] - fold["over_2_5_matches"]
    assert set(report["metrics"]["marche"]["2021-22"]) == {"over_2_5_subset"}  # jamais de log-loss du total
    assert report["metrics"]["marche"]["2021-22"]["over_2_5_subset"]["brier"] == pytest.approx(0.25)  # p = 0,5
    assert "brier_over_2_5_subset" in report["comparisons"][1] and "log_loss" not in report["comparisons"][1]
