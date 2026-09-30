"""M1 (linéaire) et M2 (Poisson sur le total), matrice des variables, diagnostics de dispersion. Sans base."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foot_predictor.modeling import diagnostics
from foot_predictor.modeling.design import Design
from foot_predictor.modeling.models.base import match_frame
from foot_predictor.modeling.models.total import M1, M2, discretized_normal
from tests.modeling.synthetic import realistic_rows


@pytest.fixture(scope="module")
def rows():
    return realistic_rows(seasons=range(2015, 2019))


def _league_sums(model, rows):
    matches = match_frame(rows)
    totals = matches["home_goals_for"] + matches["away_goals_for"]
    fitted = pd.Series(np.asarray(model.result_.fittedvalues), index=matches.index)
    league = matches["home_api_league_id"]
    return totals.groupby(league).sum(), fitted.groupby(league).sum()


def test_m2_with_league_effects_reproduces_each_league_total_exactly(rows):
    """Équations du maximum de vraisemblance d'un Poisson à lien log avec constante et indicatrices :
    Σ (t − μ̂) = 0 dans chaque modalité ; le modèle redonne la moyenne empirique de chaque championnat."""
    model = M2(groups=("G0",)).fit(rows)
    observed, fitted = _league_sums(model, rows)
    assert fitted.to_numpy() == pytest.approx(observed.to_numpy(), rel=1e-8)


def test_m1_residuals_also_sum_to_zero_by_league(rows):
    model = M1(groups=("G0",)).fit(rows)
    observed, fitted = _league_sums(model, rows)
    assert fitted.to_numpy() == pytest.approx(observed.to_numpy(), rel=1e-8)


def test_m1_predicts_a_valid_distribution_and_reports_its_flaws(rows):
    model = M1().fit(rows)
    predicted = model.predict(rows.drop(columns=["goals_for", "goals_against"]))
    assert predicted.total.sum(axis=1) == pytest.approx(1.0)
    assert (predicted.extra["negative_mass"] > 0).all()  # une loi normale met toujours de la masse sous 0
    lower = predicted.lambda_home * 2 - 1.2816 * predicted.extra["predicted_sd"]  # intervalle symétrique à 80 %
    assert predicted.extra["interval80_below_zero"] == pytest.approx((lower < 0).astype(float))
    diag = model.describe()["diagnostics"]
    assert 0 < diag["r2"] < 0.2 and diag["sigma"] > 1


def test_discretized_normal_folds_negative_mass_into_zero():
    probs = discretized_normal(np.array([0.2]), np.array([1.0]))
    assert probs.sum() == pytest.approx(1.0)
    from scipy.stats import norm

    assert probs[0, 0] == pytest.approx(norm.cdf(0.3))  # P(N < 0,5), négatifs compris
    assert probs[0, 1] == pytest.approx(norm.cdf(1.3) - norm.cdf(0.3))


def test_m2_on_poisson_data_is_not_overdispersed(rows):
    diag = M2().fit(rows).describe()["diagnostics"]
    assert diag["pearson_dispersion"] == pytest.approx(1.0, abs=0.1)
    assert abs(diag["cameron_trivedi"]["t"]) < 3


def test_cameron_trivedi_detects_overdispersion_and_underdispersion():
    rng = np.random.default_rng(0)
    mu = rng.uniform(1, 3, 20_000)
    over = rng.poisson(mu * rng.gamma(2.0, 0.5, mu.size))  # Var = μ + 0,5 μ²
    assert diagnostics.cameron_trivedi(over, mu)["alpha"] == pytest.approx(0.5, abs=0.08)
    assert diagnostics.cameron_trivedi(over, mu)["p_value"] < 1e-6
    under = np.round(mu).astype(int)  # variance quasi nulle
    assert diagnostics.cameron_trivedi(under, mu)["alpha"] < 0
    assert diagnostics.pearson_dispersion(under, mu, 1) < 0.2


def test_likelihood_ratio_at_the_boundary_halves_the_p_value():
    result = diagnostics.likelihood_ratio_boundary(-100.0, -98.0)
    assert result["lr"] == pytest.approx(4.0)
    from scipy.stats import chi2

    assert result["p_value"] == pytest.approx(0.5 * chi2.sf(4.0, 1))
    assert diagnostics.likelihood_ratio_boundary(-100.0, -100.5)["p_value"] == 0.5


def test_design_learns_its_scaling_on_training_rows_only(rows):
    train, test = rows[rows["season_year"] < 2018], rows[rows["season_year"] == 2018].copy()
    design = Design(("G0", "G1")).fit(train)
    mean, std = design.scale_["z_elo"]
    assert mean == pytest.approx(train["elo_pre"].mean()) and std == pytest.approx(train["elo_pre"].std(ddof=0))
    test["elo_pre"] += 1000  # un test très différent ne change pas la standardisation apprise
    assert design.transform(test)["z_elo"].mean() > 5


def test_constant_training_column_is_dropped_not_estimated(rows):
    design = Design(("G0",)).fit(rows[rows["season_year"] < 2019])  # aucun huis clos avant 2020
    assert "behind_closed_doors" in design.dropped_ and "home_x_closed" in design.dropped_
    assert "behind_closed_doors" not in design.transform(rows).columns


def test_design_refuses_an_unknown_league_and_a_missing_half_life(rows):
    design = Design(("G0",)).fit(rows[rows["api_league_id"] == 39])
    with pytest.raises(ValueError):
        design.transform(rows[rows["api_league_id"] == 140])
    with pytest.raises(ValueError):
        Design(("G0", "G2"))
