"""M3 (Poisson par équipe) et M4 (binomiale négative) : propriétés théoriques sur données simulées. Sans base."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foot_predictor.modeling import distributions as dist
from foot_predictor.modeling.models.team import M3, M4
from tests.modeling.synthetic import TRUE_HOME, TRUE_STRENGTH, realistic_rows


@pytest.fixture(scope="module")
def rows():
    return realistic_rows(seasons=range(2015, 2020))


def test_m3_reproduces_the_mean_goals_of_each_league_and_side(rows):
    """Score du maximum de vraisemblance : Σ (y − λ̂) = 0 pour la constante, chaque championnat et `is_home`."""
    model = M3(groups=("G0",)).fit(rows)
    fitted = pd.Series(np.asarray(model.result_.fittedvalues), index=rows.index)
    for key, group in rows.groupby("api_league_id"):
        assert fitted[group.index].sum() == pytest.approx(group["goals_for"].sum(), rel=1e-8), key
    home = rows["is_home"]
    assert fitted[home].sum() == pytest.approx(rows.loc[home, "goals_for"].sum(), rel=1e-8)


def test_m3_recovers_the_true_home_advantage_and_elo_effect(rows):
    coef = M3().fit(rows).describe()["diagnostics"]["coefficients"]
    assert coef["is_home"] == pytest.approx(TRUE_HOME, abs=0.05)
    assert coef["z_elo"] > 0 > coef["z_opp_elo"]  # sa force fait marquer, celle de l'adversaire empêche
    assert coef["z_elo"] == pytest.approx(-coef["z_opp_elo"], abs=0.05)  # effet symétrique dans le modèle simulé
    assert TRUE_STRENGTH > 0


def test_m3_clustered_and_naive_standard_errors_are_both_reported(rows):
    diag = M3().fit(rows).describe()["diagnostics"]
    assert set(diag["std_errors_cluster"]) == set(diag["std_errors_naive"])
    assert diag["n_matches"] * 2 == diag["n_rows"]


def test_m3_total_is_poisson_of_the_sum_of_the_two_lambdas(rows):
    model = M3().fit(rows)
    predicted = model.predict(rows.drop(columns=["goals_for", "goals_against"]))
    assert predicted.total == pytest.approx(dist.poisson_total(predicted.lambda_home, predicted.lambda_away))
    assert predicted.joint.shape[1:] == (dist.JOINT_GOALS, dist.JOINT_GOALS)
    home_rows = rows[rows["is_home"]].set_index("match_id")
    assert np.all(predicted.lambda_home > 0) and len(predicted) == len(home_rows)


def test_poisson_data_does_not_justify_the_negative_binomial(rows):
    diag = M4().fit(rows).describe()["diagnostics"]
    assert diag["alpha"] < 0.03
    assert diag["likelihood_ratio"]["p_value"] > 0.01


def test_overdispersed_data_gives_alpha_and_a_significant_likelihood_ratio():
    rows = realistic_rows(seasons=range(2015, 2020), dispersion=0.3)
    m4 = M4().fit(rows)
    diag = m4.describe()["diagnostics"]
    assert diag["alpha"] == pytest.approx(0.3, abs=0.1)
    assert diag["likelihood_ratio"]["p_value"] < 1e-6
    assert M3().fit(rows).describe()["diagnostics"]["cameron_trivedi"]["alpha"] > 0.1
    predicted = m4.predict(rows.drop(columns=["goals_for", "goals_against"]))
    assert predicted.total.sum(axis=1) == pytest.approx(1.0)


def test_m3_can_report_the_negative_binomial_diagnostic_of_its_fold(rows):
    diag = M3(check_dispersion=True).fit(rows).describe()["diagnostics"]
    assert set(diag["negative_binomial"]) == {"alpha", "likelihood_ratio", "converged"}
