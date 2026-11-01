"""M7 : boosting à perte de Poisson. Mêmes variables que M3, structure non linéaire. Sans base."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_poisson_deviance

from foot_predictor.modeling import protocol
from foot_predictor.modeling.models import MODELS
from foot_predictor.modeling.models.boosting import M7
from foot_predictor.modeling.models.regularized import M6
from foot_predictor.modeling.models.team import M3
from tests.modeling.synthetic import realistic_rows, with_composition

H1 = ("G0", "G1", "G2")
TARGETS = ["goals_for", "goals_against"]


@pytest.fixture(scope="module")
def rows():
    return realistic_rows(seed=5, rounds=38)


def _split(rows, last_train=2022):
    train = rows[rows["season_year"] <= last_train]
    test = rows[rows["season_year"] > last_train]
    return train, test


def _with_curved_goals(rows: pd.DataFrame, seed: int = 11) -> pd.DataFrame:
    """Rejoue les buts avec un effet de l'écart d'Elo qui n'est PAS linéaire dans log λ (courbure symétrique)."""
    rng = np.random.default_rng(seed)
    frame = rows.copy()
    z = (frame["elo_pre"] - frame["opp_elo_pre"]) / 140.0
    mean = np.exp(0.1 + 0.3 * frame["is_home"] + 0.5 * (z**2 - 1.0))
    frame["goals_for"] = rng.poisson(mean.to_numpy())
    goals = frame.set_index(["match_id", "team_id"])["goals_for"]
    index = pd.MultiIndex.from_arrays([frame["match_id"], frame["opp_team_id"]])
    frame["goals_against"] = goals.reindex(index).to_numpy()
    return frame


def test_m7_is_registered_and_predicts_a_complete_law_for_every_test_match(rows):
    assert MODELS["m7"] is M7
    train, test = _split(rows)
    predicted = M7(H1, half_life=120).fit(train).predict(test.drop(columns=TARGETS))
    assert len(predicted) == test["match_id"].nunique()
    assert np.isfinite(predicted.total).all() and np.allclose(predicted.total.sum(axis=1), 1.0)
    assert (predicted.lambda_home > 0).all() and (predicted.lambda_away > 0).all()


def test_on_log_linear_data_m7_is_close_to_the_poisson_glm(rows):
    """Aucune courbure à trouver : le boosting ne doit pas être loin du modèle vrai (ni mieux, ni bien pire)."""
    train, test = _split(rows)
    plain = test.drop(columns=TARGETS)
    lam_glm = M3(H1, half_life=120).fit(train).team_lambda(plain)
    lam_gbm = M7(H1, half_life=120).fit(train).team_lambda(plain)
    assert np.corrcoef(lam_glm, lam_gbm)[0, 1] > 0.9
    dev_glm = mean_poisson_deviance(test["goals_for"], lam_glm)
    dev_gbm = mean_poisson_deviance(test["goals_for"], lam_gbm)
    assert dev_gbm < dev_glm * 1.02


def test_m7_finds_a_curvature_that_the_log_linear_models_cannot(rows):
    curved = _with_curved_goals(rows)
    train, test = _split(curved)
    plain = test.drop(columns=TARGETS)
    dev_glm = mean_poisson_deviance(test["goals_for"], M3(H1, half_life=120).fit(train).team_lambda(plain))
    dev_ridge = mean_poisson_deviance(test["goals_for"], M6(H1, 120, alpha=1e-3).fit(train).team_lambda(plain))
    dev_gbm = mean_poisson_deviance(test["goals_for"], M7(H1, half_life=120).fit(train).team_lambda(plain))
    assert dev_gbm < dev_glm * 0.97
    assert dev_gbm < dev_ridge * 0.97


def test_the_fit_is_deterministic(rows):
    train, test = _split(rows)
    plain = test.drop(columns=TARGETS)
    first = M7(H1, half_life=120).fit(train).team_lambda(plain)
    second = M7(H1, half_life=120).fit(train).team_lambda(plain)
    assert np.array_equal(first, second)


def test_more_iterations_fit_the_training_rows_more_closely(rows):
    train, _ = _split(rows)
    deviance = [
        mean_poisson_deviance(train["goals_for"], M7(H1, 120, max_iter=n).fit(train).team_lambda(train))
        for n in (10, 100, 400)
    ]
    assert deviance[0] > deviance[1] > deviance[2]


def test_invalid_settings_are_refused_and_half_life_is_ignored_without_g2():
    for bad in ({"max_depth": 0}, {"max_iter": 0}, {"min_samples_leaf": 0}, {"learning_rate": 0.0},
                {"learning_rate": 1.5}, {"l2_regularization": -1.0}):  # fmt: skip
        with pytest.raises(ValueError):
            M7(**bad)
    assert M7(("G0", "G1"), half_life=120).params["half_life"] is None


def test_the_xi_quality_group_is_read_and_starts_training_in_2016():
    """D3 (ADR-0047) : G5 apprend dès 2016-17, pour M7 comme pour M6 ; rien ne change sans groupe H2."""
    frame = with_composition(realistic_rows(seed=3, rounds=22), quality_effect=0.12)
    model = M7((*H1, "G5"), half_life=120)
    assert model.first_training_season == 2016 and "xi_quality" in model.features
    assert M6((*H1, "G5"), 120).first_training_season == 2016
    assert M6(("G0", "G1", "G2", "G3"), 120).first_training_season is None
    assert M7(H1, 120).first_training_season is None
    fitted = model.fit(frame[frame["season_year"] < 2024])
    assert "z_xi_quality" in fitted.describe()["columns"]
    assert fitted.describe()["design"]["first_training_season"] == 2016


def test_train_from_is_a_window_control_for_m6_and_m7_and_never_changes_an_h1_description():
    for make in (M6, M7):
        assert make(H1, 120, train_from=2016).first_training_season == 2016
        assert make((*H1, "G5"), 120, train_from=2015).first_training_season == 2016
        assert make((*H1, "G4"), 120, train_from=2016).first_training_season == 2017
        assert make(H1, 120).first_training_season is None
        assert make(H1, 120, train_from=2016).params["train_from"] == 2016
        assert "train_from" not in make(H1, 120).params
    assert "train_from" not in M6(("G0", "G1", "G2", "G3"), 120).params


def test_a_gain_in_xi_quality_is_used_when_it_matters():
    frame = with_composition(realistic_rows(seed=3, rounds=30), quality_effect=0.3)
    train, test = frame[frame["season_year"] < 2024], frame[frame["season_year"] == 2024]
    plain = test.drop(columns=TARGETS)
    with_g5 = M7((*H1, "G5"), 120).fit(train).team_lambda(plain)
    without = M7(H1, 120).fit(train).team_lambda(plain)
    assert mean_poisson_deviance(test["goals_for"], with_g5) < mean_poisson_deviance(test["goals_for"], without)


def test_the_protocol_chooses_among_candidates_without_reading_the_test_season(rows):
    grid = [{"groups": H1, "half_life": 120, "max_iter": n} for n in (20, 150)]
    features = M7(**grid[0]).features
    result = protocol.select_and_fit(M7, grid, rows, protocol.Fold(2021), "top5", features)
    assert result.params in grid and len(result.inner_scores) == 2
    assert result.model.n_rows_ > 0 and result.run_in_rows == 0
