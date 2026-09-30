"""Diagnostics des modèles de comptage : dispersion (φ, test de Cameron-Trivedi), rapport de vraisemblance.

**Dispersion.** Sous une loi de Poisson, Var(Y | x) = E(Y | x) = μ. On mesure l'écart par :

- φ = χ²_Pearson / ddl = Σ (y − μ̂)² / μ̂ / (n − p) : 1 sous Poisson ; > 1 surdispersion ;
  < 1 sous-dispersion ;
- le **test de Cameron et Trivedi** (1990) : sous l'alternative Var(Y) = μ + α μ² (binomiale
  négative NB2), la régression auxiliaire sans constante
  ((y − μ̂)² − y) / μ̂ = α · μ̂ + ε
  donne un α̂ et sa statistique t. α > 0 : surdispersion ; α < 0 : sous-dispersion ; t proche de
  0 : la loi de Poisson suffit.

**Rapport de vraisemblance** Poisson contre binomiale négative : LR = 2 (ℓ_NB − ℓ_Poisson). Le
paramètre α = 0 est au **bord** de son domaine (α ≥ 0) : la loi de LR sous H0 est un mélange
½ χ²₀ + ½ χ²₁, d'où p = ½ · P(χ²₁ > LR).
"""

from __future__ import annotations

import numpy as np
from scipy.stats import chi2, norm


def pearson_dispersion(y, mu, n_params: int) -> float:
    """φ = Σ (y − μ)² / μ / (n − p)."""
    y, mu = np.asarray(y, dtype=float), np.asarray(mu, dtype=float)
    return float(((y - mu) ** 2 / mu).sum() / (len(y) - n_params))


def cameron_trivedi(y, mu) -> dict:
    """Régression auxiliaire ((y − μ)² − y) / μ = α μ + ε (sans constante) : α̂, t, p bilatérale."""
    y, mu = np.asarray(y, dtype=float), np.asarray(mu, dtype=float)
    z = ((y - mu) ** 2 - y) / mu
    alpha = float((mu * z).sum() / (mu * mu).sum())
    residual = z - alpha * mu
    se = float(np.sqrt((residual**2).sum() / (len(y) - 1) / (mu * mu).sum()))
    t = alpha / se
    return {"alpha": alpha, "t": float(t), "p_value": float(2 * norm.sf(abs(t)))}


def likelihood_ratio_boundary(loglik_restricted: float, loglik_full: float) -> dict:
    """LR = 2 (ℓ_complet − ℓ_restreint), p-valeur au bord : ½ · P(χ²₁ > LR)."""
    lr = max(0.0, 2.0 * (loglik_full - loglik_restricted))
    return {"lr": float(lr), "p_value": float(0.5 * chi2.sf(lr, 1)) if lr > 0 else 0.5}
