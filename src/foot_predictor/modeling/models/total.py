"""M1 et M2 : modèles du **total** T = Y_dom + Y_ext, étapes pédagogiques (rapport I.4 ; ADR-0009).

Ni l'un ni l'autre n'est candidat au choix final (ADR-0009, ADR-0037) : ils montrent pourquoi il
faut une loi de comptage (M1 → M2), puis pourquoi il faut décomposer par équipe (M2 → M3).

**M1, régression linéaire (moindres carrés ordinaires).** T_m = x_mᵀ β + ε_m. Sous les hypothèses
de Gauss-Markov (linéarité, exogénéité E[ε | x] = 0, homoscédasticité Var(ε | x) = σ², absence de
corrélation des erreurs), β̂ = (XᵀX)⁻¹ Xᵀ T est le meilleur estimateur linéaire sans biais. La loi
prédictive est normale : T ~ N(x ᵀβ̂, σ̂² + se(x ᵀβ̂)²) (variance de prédiction = bruit + incertitude
sur β). Pour obtenir une loi du total, on la **discrétise** : P(T = k) = Φ((k + ½ − μ)/s) −
Φ((k − ½ − μ)/s), la masse sous −½ étant rabattue sur 0 et celle au-dessus de 9,5 sur « 10 et
plus ». Ce que M1 rate, et que le rapport chiffre : une masse de probabilité sur des totaux
négatifs, une variance supposée constante alors que celle d'un comptage croît avec sa moyenne, un
intervalle symétrique, une loi continue pour un nombre entier.

**M2, GLM de Poisson sur le total.** T_m ~ Poisson(μ_m), log μ_m = x_mᵀ β (lien log), β estimé
par maximum de vraisemblance (IRLS). La déviance D = 2 Σ [t log(t/μ̂) − (t − μ̂)] mesure l'écart au
modèle saturé ; la dispersion (φ, test de Cameron-Trivedi) dit si Var(T) = E(T) est plausible.

λ domicile et λ extérieur ne sont pas définis pour un modèle du total : ils valent μ/2 chacun
(par convention, pour l'interface commune ; E[T] = μ reste exact).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm
from statsmodels.stats.diagnostic import het_breuschpagan

from foot_predictor.modeling import diagnostics
from foot_predictor.modeling import distributions as dist
from foot_predictor.modeling.design import Design
from foot_predictor.modeling.models.base import MatchPredictions, Model, match_frame

Z_80 = norm.ppf(0.90)
"""Quantile de la loi normale pour un intervalle symétrique à 80 % (μ ± 1,28 s)."""


def match_totals(rows: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    matches = match_frame(rows)
    return matches, (matches["home_goals_for"] + matches["away_goals_for"]).to_numpy(dtype=float)


def discretized_normal(mean: np.ndarray, sd: np.ndarray, k_max: int = dist.K_MAX) -> np.ndarray:
    """Loi normale discrétisée sur 0..k_max : masse sous −½ rabattue sur 0, au-dessus de k_max − ½ sur « k_max et plus »."""
    mean, sd = np.asarray(mean, dtype=float)[:, None], np.asarray(sd, dtype=float)[:, None]
    edges = np.arange(k_max) + 0.5  # bornes supérieures des cases 0..k_max−1
    cdf = norm.cdf((edges - mean) / sd)
    head = np.diff(np.hstack([np.zeros((len(mean), 1)), cdf]), axis=1)
    return np.hstack([head, 1.0 - cdf[:, -1:]])


class M1(Model):
    """Moindres carrés ordinaires sur le total, loi prédictive normale discrétisée."""

    name = "M1"

    def __init__(self, groups=("G0", "G1")) -> None:
        super().__init__(groups=list(groups))
        self.design = Design(tuple(groups), level="match")
        self.features = tuple(self.design.required())

    def fit(self, rows: pd.DataFrame) -> M1:
        matches, totals = match_totals(rows)
        X = self.design.fit_transform(matches)
        self.result_ = sm.OLS(totals, X).fit()
        fitted = self.result_.fittedvalues.to_numpy()
        residuals = totals - fitted
        bp_stat, bp_p, _, _ = het_breuschpagan(residuals, X)
        quintile = pd.qcut(fitted, 5, labels=False, duplicates="drop")
        var_by_q = pd.Series(residuals).groupby(quintile).var()
        self.diagnostics_ = {
            "n_matches": int(len(totals)),
            "r2": float(self.result_.rsquared),
            "r2_adjusted": float(self.result_.rsquared_adj),
            "sigma": float(np.sqrt(self.result_.scale)),
            "breusch_pagan_p": float(bp_p),
            "residual_variance_by_fitted_quintile": [float(v) for v in var_by_q],
            "fitted_min": float(fitted.min()),
            "fitted_below_zero": int((fitted < 0).sum()),
            "coefficients": {k: float(v) for k, v in self.result_.params.items()},
            "conf_int_95": {k: [float(a), float(b)] for k, (a, b) in self.result_.conf_int().iterrows()},
        }
        return self

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:
        matches = match_frame(rows)
        X = self.design.transform(matches)
        prediction = self.result_.get_prediction(X)
        mean = np.asarray(prediction.predicted_mean)
        se_mean = np.asarray(prediction.se_mean)
        sd = np.sqrt(self.result_.scale + se_mean**2)  # intervalle de prédiction : bruit + incertitude sur β
        total = discretized_normal(mean, sd)
        extra = {
            "negative_mass": norm.cdf((-0.5 - mean) / sd),  # probabilité d'un total « négatif », rabattue sur 0
            "interval80_below_zero": (mean - Z_80 * sd < 0).astype(float),  # borne basse symétrique < 0
            "predicted_sd": sd,
        }
        return MatchPredictions(matches.index.to_numpy(), mean / 2, mean / 2, total, extra=extra)

    def describe(self) -> dict:
        return super().describe() | {"diagnostics": getattr(self, "diagnostics_", {})}


class M2(Model):
    """GLM de Poisson sur le total (lien log), loi prédictive Poisson(μ)."""

    name = "M2"

    def __init__(self, groups=("G0", "G1")) -> None:
        super().__init__(groups=list(groups))
        self.design = Design(tuple(groups), level="match")
        self.features = tuple(self.design.required())

    def fit(self, rows: pd.DataFrame) -> M2:
        matches, totals = match_totals(rows)
        X = self.design.fit_transform(matches)
        self.result_ = sm.GLM(totals, X, family=sm.families.Poisson()).fit()
        mu = self.result_.fittedvalues.to_numpy()
        self.diagnostics_ = {
            "n_matches": int(len(totals)),
            "deviance": float(self.result_.deviance),
            "df_resid": float(self.result_.df_resid),
            "pearson_dispersion": diagnostics.pearson_dispersion(totals, mu, X.shape[1]),
            "cameron_trivedi": diagnostics.cameron_trivedi(totals, mu),
            "loglik": float(self.result_.llf),
            "coefficients": {k: float(v) for k, v in self.result_.params.items()},
            "std_errors": {k: float(v) for k, v in self.result_.bse.items()},
        }
        return self

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:
        matches = match_frame(rows)
        mu = np.asarray(self.result_.predict(self.design.transform(matches)))
        total = dist.fold(dist.poisson_pmf(mu, support=dist.K_MAX + 1))
        return MatchPredictions(matches.index.to_numpy(), mu / 2, mu / 2, total)

    def describe(self) -> dict:
        return super().describe() | {"diagnostics": getattr(self, "diagnostics_", {})}
