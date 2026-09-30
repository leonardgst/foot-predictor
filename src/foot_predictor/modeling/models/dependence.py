"""M5 : dépendance entre les deux équipes, correction de Dixon et Coles (1997) sur les λ de M3.

Question du rapport (I.2, I.4) : **la corrélation change-t-elle la loi du total sur les petites
valeurs (0, 1, 2) ?**

Sous M3, Y_dom et Y_ext sont indépendants : P(a, b) = p_dom(a) · p_ext(b). Dixon et Coles
corrigent les quatre scores les plus bas par un facteur τ :

    τ(0, 0) = 1 − λ_dom λ_ext ρ      τ(0, 1) = 1 + λ_dom ρ
    τ(1, 0) = 1 + λ_ext ρ            τ(1, 1) = 1 − ρ          τ = 1 ailleurs,

    P_DC(a, b) = τ(a, b) · p_dom(a) · p_ext(b).

Les corrections se compensent : Σ τ(a, b) p_dom(a) p_ext(b) = 1 pour des marges de Poisson,
donc P_DC est une loi, et les moyennes restent proches. ρ < 0 rend 0-0 et 1-1 **plus**
probables (et 1-0, 0-1 moins) : P(T = 0) monte, P(T = 1) baisse, P(T = 2) bouge peu.

**Estimation en deux temps, dans le pli** : (1) M3 par maximum de vraisemblance (λ) ; (2) ρ
maximise Σ_m log τ(y_dom, y_ext ; λ̂_dom, λ̂_ext, ρ) sur les matchs d'apprentissage, sous la
contrainte τ > 0 pour tous ces matchs. Le Dixon-Coles d'origine estime tout ensemble ; les λ
bougeant très peu avec ρ, les deux temps donnent pratiquement le même ρ, plus simplement.
Matière réutilisée : `modeling/legacy/dixon_coles.tau_correction` (même formule, testée contre
la version vectorisée ci-dessous).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from foot_predictor.modeling import distributions as dist
from foot_predictor.modeling.models.base import MatchPredictions, Model, match_frame
from foot_predictor.modeling.models.team import M3


def tau(a, b, lambda_home, lambda_away, rho) -> np.ndarray:
    """Facteur de Dixon-Coles, vectorisé (a, b entiers ; λ tableaux)."""
    a, b = np.asarray(a), np.asarray(b)
    lambda_home, lambda_away = np.asarray(lambda_home, dtype=float), np.asarray(lambda_away, dtype=float)
    result = np.ones(np.broadcast(a, b, lambda_home).shape)
    result = np.where((a == 0) & (b == 0), 1 - lambda_home * lambda_away * rho, result)
    result = np.where((a == 0) & (b == 1), 1 + lambda_home * rho, result)
    result = np.where((a == 1) & (b == 0), 1 + lambda_away * rho, result)
    return np.where((a == 1) & (b == 1), 1 - rho, result)


def rho_bounds(lambda_home: np.ndarray, lambda_away: np.ndarray) -> tuple[float, float]:
    """Intervalle de ρ où τ > 0 pour tous les matchs : max(−1/λ_dom, −1/λ_ext) < ρ < min(1/(λ_dom λ_ext), 1)."""
    low = max(np.max(-1 / lambda_home), np.max(-1 / lambda_away))
    high = min(np.min(1 / (lambda_home * lambda_away)), 1.0)
    return float(low), float(high)


def estimate_rho(y_home, y_away, lambda_home, lambda_away) -> float:
    """ρ̂ = argmax Σ log τ(y_dom, y_ext ; λ_dom, λ_ext, ρ), à λ fixés."""
    low, high = rho_bounds(lambda_home, lambda_away)
    margin = 1e-6 * (high - low)

    def negative_loglik(rho: float) -> float:
        return -float(np.log(tau(y_home, y_away, lambda_home, lambda_away, rho)).sum())

    result = minimize_scalar(negative_loglik, bounds=(low + margin, high - margin), method="bounded")
    return float(result.x)


def dixon_coles_joint(lambda_home, lambda_away, rho) -> np.ndarray:
    """Loi jointe corrigée sur 0..9 et « 10 et plus » pour chaque équipe."""
    home = dist.fold(dist.poisson_pmf(lambda_home))
    away = dist.fold(dist.poisson_pmf(lambda_away))
    joint = dist.independent_joint(home, away)
    for a in (0, 1):
        for b in (0, 1):
            joint[:, a, b] *= tau(a, b, lambda_home, lambda_away, rho)
    return joint


class M5(Model):
    """M3 (Poisson par équipe) + correction de Dixon-Coles, ρ estimé dans le pli."""

    name = "M5"

    def __init__(self, groups=("G0", "G1"), half_life: int | None = None) -> None:
        super().__init__(groups=list(groups), half_life=half_life)
        self.base = M3(groups, half_life)
        self.features = self.base.features

    def fit(self, rows: pd.DataFrame) -> M5:
        self.base.fit(rows)
        lam = self.base.team_lambda(rows)
        matches = match_frame(rows[["match_id", "is_home", "goals_for"]].assign(lam=lam))
        self.rho_ = estimate_rho(
            matches["home_goals_for"].to_numpy(), matches["away_goals_for"].to_numpy(),
            matches["home_lam"].to_numpy(), matches["away_lam"].to_numpy(),
        )  # fmt: skip
        self.bounds_ = rho_bounds(matches["home_lam"].to_numpy(), matches["away_lam"].to_numpy())
        return self

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:
        matches = match_frame(rows[["match_id", "is_home"]].assign(lam=self.base.team_lambda(rows)))
        lambda_home, lambda_away = matches["home_lam"].to_numpy(), matches["away_lam"].to_numpy()
        joint = dixon_coles_joint(lambda_home, lambda_away, self.rho_)
        return MatchPredictions(
            matches.index.to_numpy(), lambda_home, lambda_away, dist.total_from_joint(joint),
            joint.sum(axis=2), joint.sum(axis=1), joint,
        )  # fmt: skip

    def describe(self) -> dict:
        return super().describe() | {
            "rho": getattr(self, "rho_", None),
            "rho_bounds": getattr(self, "bounds_", None),
            "base": self.base.describe().get("diagnostics", {}).get("coefficients", {}),
        }
