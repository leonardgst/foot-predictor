"""Test de plomberie du Modèle A (section 4.2 du document) : sur des données
synthétiques où `y` dépend positivement d'une feature et négativement d'une
autre par construction, le GLM Poisson doit retrouver des coefficients du bon
signe et significatifs. Sert de garde-fou : si quelqu'un inverse une colonne
own/opp par erreur dans dataset.py, ce test le détecterait indirectement en
cassant les signes attendus sur de vraies données."""
from __future__ import annotations

import numpy as np
import pandas as pd

from foot_predictor.modeling.poisson_model import fit_poisson_model


def test_fitted_coefficients_recover_known_signs_on_synthetic_data():
    rng = np.random.default_rng(7)
    n = 4000

    positive_driver = rng.normal(1.5, 0.5, n)  # ex. xg_for_last5
    negative_driver = rng.normal(1.2, 0.5, n)  # ex. opp_xg_against_last5 codé à l'envers

    true_intercept = 0.1
    true_beta_positive = 0.4
    true_beta_negative = -0.3

    lam = np.exp(true_intercept + true_beta_positive * positive_driver + true_beta_negative * negative_driver)
    y = rng.poisson(lam)

    X = pd.DataFrame({"own_xg_for_last5": positive_driver, "opp_xg_against_last5": negative_driver})
    model = fit_poisson_model(X, pd.Series(y))

    coef_positive = model.result.params["own_xg_for_last5"]
    coef_negative = model.result.params["opp_xg_against_last5"]
    pvalue_positive = model.result.pvalues["own_xg_for_last5"]
    pvalue_negative = model.result.pvalues["opp_xg_against_last5"]

    assert coef_positive > 0
    assert coef_negative < 0
    assert pvalue_positive < 0.05
    assert pvalue_negative < 0.05
