"""Métriques du total : cas exacts (loi parfaite, uniforme, Poisson connu), cas limites, refus des lois invalides."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import poisson

from foot_predictor.modeling import distributions as dist
from foot_predictor.modeling import metrics as m

K = dist.TOTAL_CATEGORIES


def perfect(totals) -> np.ndarray:
    probs = np.zeros((len(totals), K))
    probs[np.arange(len(totals)), np.minimum(totals, K - 1)] = 1.0
    return probs


def uniform(n: int) -> np.ndarray:
    return np.full((n, K), 1.0 / K)


# ------------------------------------------------------------------------------ lois


def test_poisson_total_is_poisson_of_the_sum_and_folds_the_tail():
    probs = dist.poisson_total(np.array([1.2]), np.array([1.6]))
    assert probs.shape == (1, K) and probs.sum() == pytest.approx(1.0, abs=1e-12)
    assert probs[0, :10] == pytest.approx(poisson.pmf(np.arange(10), 2.8))
    assert probs[0, 10] == pytest.approx(poisson.sf(9, 2.8))  # P(T ≥ 10)


def test_convolution_of_independent_poissons_equals_poisson_total():
    home, away = dist.poisson_pmf([1.3, 0.4]), dist.poisson_pmf([1.1, 2.5])
    assert dist.total_from_independent(home, away) == pytest.approx(dist.poisson_total([1.3, 0.4], [1.1, 2.5]))
    joint = dist.independent_joint(home, away)
    assert dist.total_from_joint(joint) == pytest.approx(dist.poisson_total([1.3, 0.4], [1.1, 2.5]))


def test_outcome_probabilities_of_a_symmetric_joint():
    joint = dist.independent_joint(dist.poisson_pmf([1.4]), dist.poisson_pmf([1.4]))
    p_home, p_draw, p_away = dist.outcome_probabilities(joint)[0]
    assert p_home == pytest.approx(p_away) and p_home + p_draw + p_away == pytest.approx(1.0)


# ------------------------------------------------------------------------------ règles de score


def test_perfect_forecast_has_zero_loss_everywhere():
    totals = np.array([0, 2, 3, 7, 12])
    probs = perfect(totals)
    assert m.log_loss_by_match(probs, totals) == pytest.approx(0.0)
    assert m.rps_by_match(probs, totals) == pytest.approx(0.0)
    assert m.brier_over_by_match(probs, totals) == pytest.approx(0.0)


def test_uniform_log_loss_is_log_of_the_number_of_categories():
    totals = np.array([0, 4, 10, 15])
    assert m.log_loss_by_match(uniform(4), totals) == pytest.approx(math.log(K))


def test_poisson_log_loss_equals_minus_log_pmf():
    lam, totals = 2.8, np.array([0, 1, 3, 9])
    probs = dist.poisson_total(np.full(4, 1.5), np.full(4, 1.3))
    assert m.log_loss_by_match(probs, totals) == pytest.approx(-poisson.logpmf(totals, lam))


def test_ten_goals_or_more_fall_in_the_last_category():
    probs = dist.poisson_total([1.5], [1.3])
    assert m.log_loss_by_match(probs, [14]) == pytest.approx(-math.log(poisson.sf(9, 2.8)))


def test_rps_hand_computed_case():
    # Loi sur 0 et 1 seulement (moitié-moitié), total observé 1 : F = (0,5 ; 1 ; …), O = (0 ; 1 ; …).
    probs = np.zeros((1, K))
    probs[0, :2] = 0.5
    assert m.rps_by_match(probs, [1]) == pytest.approx(0.25 / 7)
    # Plus loin du résultat : même loi, 5 buts observés. Écarts (0,5 ; 1 ; 1 ; 1 ; 1) puis 0.
    assert m.rps_by_match(probs, [5]) == pytest.approx((0.25 + 4) / 7)


def test_brier_of_over_2_5_and_binary_log_loss():
    probs = dist.poisson_total([1.5], [1.3])
    p_over = 1 - poisson.cdf(2, 2.8)
    assert m.prob_over(probs) == pytest.approx([p_over])
    assert m.brier_over_by_match(probs, [3]) == pytest.approx([(p_over - 1) ** 2])
    assert m.brier_over_by_match(probs, [2]) == pytest.approx([p_over**2])
    assert m.log_loss_binary_by_match([0.7, 0.7], [1, 0]) == pytest.approx([-math.log(0.7), -math.log(0.3)])


def test_zero_probability_on_the_observed_total_is_refused():
    with pytest.raises(m.ZeroProbabilityError):
        m.log_loss_by_match(perfect(np.array([2])), [3])
    with pytest.raises(m.ZeroProbabilityError):
        m.log_loss_binary_by_match([1.0], [0])


@pytest.mark.parametrize(
    "bad",
    [np.full((1, K), 0.2), np.array([[np.nan] + [0.1] * (K - 1)]), np.array([[-0.1, 1.1] + [0.0] * (K - 2)])],
)
def test_invalid_distributions_are_refused(bad):
    with pytest.raises(ValueError):
        m.log_loss_by_match(bad, [0])


def test_negative_total_is_refused():
    with pytest.raises(ValueError):
        m.log_loss_by_match(uniform(1), [-1])


def test_mae_rmse_are_descriptive_numbers():
    assert m.mae_rmse([2.0, 3.0], [1, 5]) == pytest.approx((1.5, math.sqrt(2.5)))


# ------------------------------------------------------------------------------ calibration


def test_calibration_of_a_calibrated_forecast():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.2, 0.8, 200_000)
    outcome = rng.uniform(size=p.size) < p
    table = m.calibration_table(p, outcome)
    assert len(table) == 10 and table["n"].sum() == p.size
    assert m.calibration_mean_abs_gap(table) < 0.005
    intercept, slope = m.calibration_slope_intercept(p, outcome)
    assert intercept == pytest.approx(0.0, abs=0.03) and slope == pytest.approx(1.0, abs=0.03)


def test_overconfident_forecast_has_a_slope_below_one():
    rng = np.random.default_rng(1)
    true_p = rng.uniform(0.3, 0.7, 100_000)
    outcome = rng.uniform(size=true_p.size) < true_p
    logit = np.log(true_p / (1 - true_p))
    overconfident = 1 / (1 + np.exp(-2 * logit))  # logits doublés
    _, slope = m.calibration_slope_intercept(overconfident, outcome)
    assert slope == pytest.approx(0.5, abs=0.05)


def test_randomized_pit_is_uniform_for_the_true_distribution():
    rng = np.random.default_rng(2)
    lam = rng.uniform(2.0, 3.5, 50_000)
    totals = rng.poisson(lam)
    probs = dist.poisson_total(lam / 2, lam / 2)
    histogram = m.pit_histogram(m.randomized_pit(probs, totals, rng))
    assert histogram == pytest.approx(np.full(10, 0.1), abs=0.01)


def test_randomized_pit_bounds():
    probs = perfect(np.array([3]))
    value = m.randomized_pit(probs, [3], np.random.default_rng(3))[0]
    assert 0.0 <= value <= 1.0


# ------------------------------------------------------------------------------ intervalle


def test_interval_of_poisson_2_8_matches_the_adr_0009_table():
    """ADR-0009 : pour λ = 2,8, [q10 ; q90] = [1 ; 5] et couverture réelle 87,4 %."""
    probs = dist.poisson_total([1.4], [1.4])
    lo, hi = m.prediction_interval(probs)
    assert (lo[0], hi[0]) == (1, 5)
    assert m.announced_coverage(probs, lo, hi)[0] == pytest.approx(poisson.cdf(5, 2.8) - poisson.cdf(0, 2.8))
    assert round(100 * m.announced_coverage(probs, lo, hi)[0], 1) == 87.4


def test_observed_coverage_matches_announced_for_the_true_distribution():
    rng = np.random.default_rng(4)
    lam = rng.uniform(2.0, 3.5, 60_000)
    totals = rng.poisson(lam)
    result = m.coverage(dist.poisson_total(lam / 2, lam / 2), totals)
    assert abs(result["gap"]) < 0.01


# ------------------------------------------------------------------------------ score exact, 1N2


def test_exact_score_and_1x2_brier():
    joint = dist.independent_joint(dist.poisson_pmf([1.5]), dist.poisson_pmf([1.1]))
    assert m.exact_score_log_loss_by_match(joint, [2], [1]) == pytest.approx(
        [-(poisson.logpmf(2, 1.5) + poisson.logpmf(1, 1.1))]
    )
    outcome = dist.outcome_probabilities(joint)
    assert m.brier_1x2_by_match([[1.0, 0.0, 0.0]], [2], [1]) == pytest.approx([0.0])
    assert m.brier_1x2_by_match(outcome, [0], [0])[0] == pytest.approx(
        outcome[0, 0] ** 2 + (1 - outcome[0, 1]) ** 2 + outcome[0, 2] ** 2
    )


def test_negative_binomial_has_mean_mu_and_variance_mu_plus_alpha_mu2():
    pmf = dist.negbin_pmf([1.4], alpha=0.2, support=80)[0]
    k = np.arange(80)
    mean = (pmf * k).sum()
    assert mean == pytest.approx(1.4) and (pmf * (k - mean) ** 2).sum() == pytest.approx(1.4 + 0.2 * 1.4**2)


def test_fold_keeps_all_the_mass_in_the_last_category():
    folded = dist.fold(dist.poisson_pmf([6.0], support=12))
    assert folded.sum() == pytest.approx(1.0) and folded[0, -1] == pytest.approx(poisson.sf(9, 6.0))


def test_constant_forecast_has_an_undefined_slope_and_the_global_gap_as_intercept():
    outcome = np.array([1, 0, 0, 0] * 50, dtype=float)  # fréquence observée 0,25
    intercept, slope = m.calibration_slope_intercept(np.full(200, 0.5), outcome)
    assert np.isnan(slope) and intercept == pytest.approx(math.log(0.25 / 0.75))
