"""M5 : correction de Dixon-Coles. Comparée à l'ancienne implémentation, ρ retrouvé sur données simulées."""

from __future__ import annotations

import numpy as np
import pytest

from foot_predictor.modeling import distributions as dist
from foot_predictor.modeling.legacy.dixon_coles import tau_correction
from foot_predictor.modeling.models.dependence import M5, dixon_coles_joint, estimate_rho, rho_bounds, tau
from foot_predictor.modeling.models.team import M3
from tests.modeling.synthetic import realistic_rows


def test_vectorized_tau_equals_the_legacy_scalar_version():
    for a in range(3):
        for b in range(3):
            assert tau(a, b, 1.4, 1.1, -0.08) == pytest.approx(tau_correction(a, b, 1.4, 1.1, -0.08))


def test_dixon_coles_joint_is_a_distribution_and_rho_zero_is_independence():
    lh, la = np.array([1.5, 0.8]), np.array([1.1, 2.0])
    joint = dixon_coles_joint(lh, la, -0.1)
    assert joint.sum(axis=(1, 2)) == pytest.approx(1.0)
    independent = dist.independent_joint(dist.fold(dist.poisson_pmf(lh)), dist.fold(dist.poisson_pmf(la)))
    assert dixon_coles_joint(lh, la, 0.0) == pytest.approx(independent)


def test_negative_rho_raises_p_total_zero_and_lowers_p_total_one():
    lh, la = np.array([1.4]), np.array([1.1])
    base = dist.total_from_joint(dixon_coles_joint(lh, la, 0.0))[0]
    corrected = dist.total_from_joint(dixon_coles_joint(lh, la, -0.1))[0]
    assert corrected[0] > base[0] and corrected[1] < base[1]
    assert corrected.sum() == pytest.approx(1.0)


def _sample_dixon_coles(rng, lh, la, rho):
    joint = dixon_coles_joint(lh, la, rho)
    flat = joint.reshape(len(lh), -1)
    draws = np.array([rng.choice(flat.shape[1], p=p / p.sum()) for p in flat])
    return draws // joint.shape[2], draws % joint.shape[2]


def test_rho_is_recovered_on_simulated_dixon_coles_scores():
    rng = np.random.default_rng(0)
    lh, la = rng.uniform(1.0, 2.0, 30_000), rng.uniform(0.7, 1.5, 30_000)
    y_home, y_away = _sample_dixon_coles(rng, lh, la, -0.12)
    assert estimate_rho(y_home, y_away, lh, la) == pytest.approx(-0.12, abs=0.03)
    y_home, y_away = _sample_dixon_coles(rng, lh, la, 0.0)
    assert estimate_rho(y_home, y_away, lh, la) == pytest.approx(0.0, abs=0.03)


def test_rho_bounds_keep_every_tau_positive():
    lh, la = np.array([0.5, 3.0]), np.array([2.5, 0.4])
    low, high = rho_bounds(lh, la)
    for rho in (low + 1e-9, high - 1e-9):
        for a in (0, 1):
            for b in (0, 1):
                assert (tau(a, b, lh, la, rho) > 0).all()


def test_m5_fits_rho_in_the_fold_and_keeps_m3_lambdas():
    rows = realistic_rows(seasons=range(2015, 2019))
    m5 = M5().fit(rows)
    assert m5.bounds_[0] < m5.rho_ < m5.bounds_[1]
    test = rows.drop(columns=["goals_for", "goals_against"])
    m3 = M3().fit(rows).predict(test)
    predicted = m5.predict(test)
    assert predicted.lambda_home == pytest.approx(m3.lambda_home)
    assert predicted.total.sum(axis=1) == pytest.approx(1.0)
    assert abs(m5.rho_) < 0.1  # données simulées indépendantes
