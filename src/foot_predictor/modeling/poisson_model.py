"""Modèle A -- régression de Poisson indépendante (section 4 et 5.1 du
document `docs/MODELE_MATHEMATIQUE.md`).

`GLM(family=Poisson())` de statsmodels plutôt que sklearn : on veut les erreurs
standard et p-values des coefficients pour vérifier pédagogiquement la
cohérence des signes (ex. `own_xg_for_last5` doit avoir un coefficient positif,
`opp_xg_against_last5`... selon convention de nommage -- voir le test de signe
dans tests/modeling/test_poisson_model.py).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm


@dataclass(frozen=True)
class PoissonModel:
    result: sm.GLM
    feature_names: list[str]  # ordre des colonnes de X au moment du fit (hors constante)

    def predict_lambda(self, X: pd.DataFrame) -> np.ndarray:
        X_aligned = X.reindex(columns=self.feature_names, fill_value=0.0)
        X_with_const = sm.add_constant(X_aligned, has_constant="add")
        return np.asarray(self.result.predict(X_with_const))

    def summary(self) -> str:
        return str(self.result.summary())


def fit_poisson_model(X: pd.DataFrame, y: pd.Series) -> PoissonModel:
    """Ajuste y_i ~ Poisson(exp(x_i^T beta)) par maximum de vraisemblance
    (IRLS, natif à statsmodels.GLM) -- section 4.2 du document."""
    feature_names = list(X.columns)
    X_with_const = sm.add_constant(X, has_constant="add")
    model = sm.GLM(y, X_with_const, family=sm.families.Poisson())
    result = model.fit()
    return PoissonModel(result=result, feature_names=feature_names)
