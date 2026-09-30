"""M6 : Poisson régularisé. α → 0 redonne M3, α croissant rétrécit les coefficients, élastique net. Sans base."""

from __future__ import annotations

import numpy as np
import pytest

from foot_predictor.modeling.models.regularized import M6
from foot_predictor.modeling.models.team import M3
from tests.modeling.synthetic import realistic_rows

ALL = ("G0", "G1", "G2", "G3")


@pytest.fixture(scope="module")
def rows():
    return realistic_rows(seasons=range(2015, 2019))


def test_tiny_penalty_gives_the_unregularized_poisson(rows):
    test = rows.drop(columns=["goals_for", "goals_against"])
    ridge = M6(ALL, half_life=120, alpha=1e-10).fit(rows).predict(test)
    plain = M3(ALL, half_life=120).fit(rows).predict(test)
    assert ridge.lambda_home == pytest.approx(plain.lambda_home, rel=1e-4)


def test_stronger_penalty_shrinks_the_coefficients_towards_zero(rows):
    norms = [np.linalg.norm(M6(ALL, 120, alpha=a).fit(rows).coef_) for a in (1e-4, 1e-2, 1.0)]
    assert norms[0] > norms[1] > norms[2]


def test_huge_penalty_predicts_about_the_mean(rows):
    model = M6(ALL, 120, alpha=1e4).fit(rows)
    lam = model.team_lambda(rows)
    assert lam.mean() == pytest.approx(rows["goals_for"].mean(), rel=0.01) and lam.std() < 0.01


def test_elastic_net_sets_some_coefficients_exactly_to_zero(rows):
    model = M6(ALL, 120, alpha=0.02, penalty="elasticnet", l1_ratio=1.0).fit(rows)
    assert model.describe()["zero_coefficients"] > 0
    predicted = model.predict(rows.drop(columns=["goals_for", "goals_against"]))
    assert predicted.total.sum(axis=1) == pytest.approx(1.0)


def test_half_life_is_ignored_without_g2_and_invalid_settings_are_refused():
    assert M6(("G0", "G1"), half_life=120).params["half_life"] is None
    with pytest.raises(ValueError):
        M6(penalty="l3")
    with pytest.raises(ValueError):
        M6(alpha=-1)


def test_nonlinearity_diagnostic_is_calm_on_a_linear_model_and_detects_a_curve():
    from foot_predictor.modeling.nonlinearity import observed_expected_by_bin

    rng = np.random.default_rng(0)
    x = rng.normal(size=60_000)
    mu_linear = np.exp(0.3 + 0.2 * x)
    _, calm = observed_expected_by_bin(x, rng.poisson(mu_linear), mu_linear)
    assert calm["p_value"] > 0.01
    curved = rng.poisson(np.exp(0.3 + 0.2 * x + 0.15 * x**2))  # courbure que le modèle linéaire ignore
    table, alarm = observed_expected_by_bin(x, curved, mu_linear * curved.sum() / mu_linear.sum())
    assert alarm["p_value"] < 1e-6
    assert table["ratio"].iloc[0] > 1 and table["ratio"].iloc[-1] > 1  # extrémités sous-estimées
