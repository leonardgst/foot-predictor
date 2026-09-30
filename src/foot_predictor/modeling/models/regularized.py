"""M6 : Poisson régularisé par équipe, toutes les variables candidates G0 à G3 (rapport I.4).

Question : **plus de variables sans surapprendre ?** Avec les groupes G2 (moyennes glissantes de
buts et d'`xg_proxy`, pour et contre, de l'équipe et de l'adversaire) et G3 (calendrier), le
modèle compte une trentaine de coefficients, dont beaucoup sont corrélés entre eux (buts et
`xg_proxy`, pour et contre). La régularisation rétrécit les coefficients vers 0 pour limiter la
variance de l'estimation, au prix d'un peu de biais.

**Ridge (L2)** : β̂ = argmin_β (1 / 2n) · D(y, β) + (α / 2) · ‖β‖², où D est la déviance de
Poisson (β₀, la constante, n'est pas pénalisé), avec `sklearn.linear_model.PoissonRegressor`.
**Élastique net** (option) : pénalité α · [L1_wt · ‖β‖₁ + (1 − L1_wt) / 2 · ‖β‖²], avec
`statsmodels` (`GLM.fit_regularized`), constante non pénalisée.

Les variables continues sont **standardisées dans le pli** (`Design`) : sans cela, la pénalité
frapperait différemment des variables d'unités différentes. La **force α** et la **demi-vie** des
glissants (60, 120 ou 240 jours) se choisissent par validation interne (protocole), jamais sur la
saison de test.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import PoissonRegressor

from foot_predictor.modeling.design import Design
from foot_predictor.modeling.models.base import MatchPredictions, Model
from foot_predictor.modeling.models.team import _pair

PENALTIES = ("l2", "elasticnet")


class M6(Model):
    """Poisson par équipe régularisé (ridge, ou élastique net), variables G0 à G3."""

    name = "M6"

    def __init__(
        self,
        groups=("G0", "G1", "G2", "G3"),
        half_life: int | None = 120,
        alpha: float = 1e-3,
        penalty: str = "l2",
        l1_ratio: float = 0.5,
    ) -> None:
        if penalty not in PENALTIES:
            raise ValueError(f"Pénalité inconnue : {penalty} (attendu : {PENALTIES})")
        if alpha < 0:
            raise ValueError("alpha doit être positif ou nul")
        half_life = half_life if "G2" in groups else None
        super().__init__(groups=list(groups), half_life=half_life, alpha=alpha, penalty=penalty, l1_ratio=l1_ratio)
        self.design = Design(tuple(groups), half_life, level="team")
        self.features = tuple(self.design.required())

    def fit(self, rows: pd.DataFrame) -> M6:
        X = self.design.fit_transform(rows)
        y = rows["goals_for"].to_numpy(dtype=float)
        self.columns_ = list(X.columns)
        if self.params["penalty"] == "l2":
            model = PoissonRegressor(alpha=self.params["alpha"], max_iter=3000, tol=1e-8)
            model.fit(X.drop(columns=["const"]).to_numpy(), y)
            self.intercept_, self.coef_ = float(model.intercept_), np.asarray(model.coef_)
        else:
            # statsmodels : pénalité par coefficient ; 0 pour la constante (non pénalisée).
            weights = np.array([0.0 if c == "const" else 1.0 for c in X.columns]) * self.params["alpha"]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = sm.GLM(y, X, family=sm.families.Poisson()).fit_regularized(
                    alpha=weights, L1_wt=self.params["l1_ratio"], maxiter=300
                )
            params = np.asarray(result.params)
            self.intercept_, self.coef_ = float(params[0]), params[1:]
        return self

    def team_lambda(self, rows: pd.DataFrame) -> np.ndarray:
        X = self.design.transform(rows).drop(columns=["const"]).to_numpy()
        return np.exp(self.intercept_ + X @ self.coef_)

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:
        ids, lambda_home, lambda_away = _pair(rows, self.team_lambda(rows))
        return MatchPredictions.independent_poisson(ids, lambda_home, lambda_away)

    def describe(self) -> dict:
        coefficients = dict(zip(self.columns_[1:], getattr(self, "coef_", []), strict=False))
        return super().describe() | {
            "intercept": getattr(self, "intercept_", None),
            "coefficients": {k: float(v) for k, v in coefficients.items()},
            "zero_coefficients": int(sum(abs(v) < 1e-10 for v in coefficients.values())),
            "design": self.design.describe(),
        }
