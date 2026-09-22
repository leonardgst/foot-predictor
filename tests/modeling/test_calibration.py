"""Tests unitaires de `modeling/calibration.py` sur données synthétiques (pas
de DB) : on construit des probabilités *délibérément sur-confiantes* (la
même pathologie observée sur le Modèle A, cf. `docs/RESULTATS_MODELE.md`
section 5) et on vérifie que Platt scaling / isotonic regression, ajustés sur
un jeu d'entraînement puis appliqués à un jeu de test disjoint, réduisent
mesurablement l'erreur de calibration."""
from __future__ import annotations

import numpy as np

from foot_predictor.modeling.calibration import (
    AWAY,
    DRAW,
    HOME,
    apply_calibrator,
    calibrate_ovr_and_renormalize,
    fit_calibrator,
    fit_isotonic_calibrator,
    fit_ovr_calibrators,
    fit_platt_calibrator,
    mean_absolute_calibration_error,
)


def _make_overconfident_synthetic_data(rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Génère (p_pred, y_true) où `y_true` suit la vraie probabilité `p_true`
    (donc `p_true` est parfaitement calibrée par construction), mais où le
    modèle "observé" `p_pred` est une version sur-confiante de `p_true` :
    poussée vers 0 ou 1 via une transformation du logit par un facteur > 1.
    C'est le pattern typique d'un modèle qui a raison "en moyenne" sur la
    tendance mais exagère sa confiance -- la même famille de biais que celle
    documentée pour le Modèle A."""
    p_true = rng.uniform(0.05, 0.95, n)
    y_true = rng.binomial(1, p_true)

    logit_true = np.log(p_true / (1 - p_true))
    overconfidence_factor = 1.8
    p_pred = 1 / (1 + np.exp(-overconfidence_factor * logit_true))
    return p_pred, y_true


def test_platt_scaling_reduces_calibration_error_on_held_out_data():
    rng = np.random.default_rng(0)
    p_pred_train, y_train = _make_overconfident_synthetic_data(rng, 4000)
    p_pred_test, y_test = _make_overconfident_synthetic_data(rng, 4000)

    error_before = mean_absolute_calibration_error(p_pred_test, y_test)

    calibrator = fit_platt_calibrator(p_pred_train, y_train)
    p_calibrated = apply_calibrator(calibrator, p_pred_test)
    error_after = mean_absolute_calibration_error(p_calibrated, y_test)

    assert error_after < error_before
    # Le facteur de sur-confiance (1.8) est assez marqué pour qu'un gain
    # substantiel (pas juste un epsilon numérique) soit attendu.
    assert error_after < 0.5 * error_before


def test_isotonic_regression_reduces_calibration_error_on_held_out_data():
    rng = np.random.default_rng(1)
    p_pred_train, y_train = _make_overconfident_synthetic_data(rng, 4000)
    p_pred_test, y_test = _make_overconfident_synthetic_data(rng, 4000)

    error_before = mean_absolute_calibration_error(p_pred_test, y_test)

    calibrator = fit_isotonic_calibrator(p_pred_train, y_train)
    p_calibrated = apply_calibrator(calibrator, p_pred_test)
    error_after = mean_absolute_calibration_error(p_calibrated, y_test)

    assert error_after < error_before
    assert error_after < 0.5 * error_before


def test_fit_calibrator_dispatches_on_method_name():
    rng = np.random.default_rng(2)
    p_pred, y_true = _make_overconfident_synthetic_data(rng, 500)

    platt = fit_calibrator("platt", p_pred, y_true)
    isotonic = fit_calibrator("isotonic", p_pred, y_true)

    assert apply_calibrator(platt, p_pred).shape == p_pred.shape
    assert apply_calibrator(isotonic, p_pred).shape == p_pred.shape


def test_fit_calibrator_rejects_unknown_method():
    rng = np.random.default_rng(3)
    p_pred, y_true = _make_overconfident_synthetic_data(rng, 100)

    try:
        fit_calibrator("bogus", p_pred, y_true)
    except ValueError:
        pass
    else:
        raise AssertionError("fit_calibrator aurait dû lever ValueError pour une méthode inconnue")


def test_calibrated_probabilities_stay_within_zero_one_on_held_out_extremes():
    """Régression isotone en particulier peut extrapoler hors [0, 1] sans le
    clipping `out_of_bounds='clip'` -- on vérifie que ce garde-fou tient sur
    des valeurs de test en dehors de la plage d'entraînement."""
    rng = np.random.default_rng(4)
    p_pred_train, y_train = _make_overconfident_synthetic_data(rng, 1000)

    calibrator = fit_isotonic_calibrator(p_pred_train, y_train)
    p_extreme = np.array([0.0, 0.001, 0.5, 0.999, 1.0])
    p_calibrated = apply_calibrator(calibrator, p_extreme)

    assert np.all(p_calibrated >= 0.0)
    assert np.all(p_calibrated <= 1.0)


def _make_synthetic_1x2(rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Simule des triplets (p_home, p_draw, p_away) sommant à 1 (comme
    `outcome_probabilities`) et une issue réelle tirée selon ces probabilités,
    avec la même sur-confiance synthétique que ci-dessus appliquée aux 3
    composantes avant renormalisation (pour ressembler à une sortie de modèle
    plausible plutôt qu'à du bruit non structuré)."""
    raw = rng.dirichlet([3.0, 2.0, 2.5], size=n)  # (n, 3), somme à 1 par ligne
    p_home, p_draw, p_away = raw[:, 0], raw[:, 1], raw[:, 2]

    outcome = np.array(
        [rng.choice([HOME, DRAW, AWAY], p=row) for row in raw]
    )
    return p_home, p_draw, p_away, outcome


def test_ovr_renormalize_always_sums_to_one():
    rng = np.random.default_rng(5)
    p_home_train, p_draw_train, p_away_train, y_train = _make_synthetic_1x2(rng, 3000)
    p_home_test, p_draw_test, p_away_test, y_test = _make_synthetic_1x2(rng, 1000)

    for method in ("platt", "isotonic"):
        calibrators = fit_ovr_calibrators(method, p_home_train, p_draw_train, p_away_train, y_train)
        p_home_c, p_draw_c, p_away_c = calibrate_ovr_and_renormalize(
            calibrators, p_home_test, p_draw_test, p_away_test
        )

        totals = p_home_c + p_draw_c + p_away_c
        np.testing.assert_allclose(totals, 1.0, atol=1e-8)
        assert np.all(p_home_c >= 0.0) and np.all(p_home_c <= 1.0)
        assert np.all(p_draw_c >= 0.0) and np.all(p_draw_c <= 1.0)
        assert np.all(p_away_c >= 0.0) and np.all(p_away_c <= 1.0)


def test_ovr_renormalize_handles_single_row():
    rng = np.random.default_rng(6)
    p_home_train, p_draw_train, p_away_train, y_train = _make_synthetic_1x2(rng, 2000)

    calibrators = fit_ovr_calibrators("platt", p_home_train, p_draw_train, p_away_train, y_train)
    p_home_c, p_draw_c, p_away_c = calibrate_ovr_and_renormalize(
        calibrators, np.array([0.6]), np.array([0.25]), np.array([0.15])
    )

    assert p_home_c.shape == (1,)
    np.testing.assert_allclose(p_home_c + p_draw_c + p_away_c, 1.0, atol=1e-8)
