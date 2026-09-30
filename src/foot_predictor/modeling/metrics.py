"""Métriques du total de buts, fonctions pures sur des lois discrètes (ADR-0009, rapport I.6).

Entrées communes :

- `probs` : tableau (n, 11) de la loi du total, P(T = k) pour k de 0 à 9 et P(T ≥ 10) en
  dernière case (`distributions.TOTAL_CATEGORIES`) ; chaque ligne est une loi (≥ 0, somme 1) ;
- `totals` : nombres de buts observés (entiers ≥ 0) ; un total de 10 ou plus tombe dans la
  dernière case.

Les fonctions `*_by_match` renvoient la perte de chaque match : c'est ce que le bootstrap
apparie match par match (`modeling/bootstrap.py`). La moyenne est la métrique.

| Rôle (ADR-0009) | Métrique |
|---|---|
| principale | log-loss du total : −log P̂(T = t) |
| secondaires | RPS du total (0 à 6 et « 7 et plus ») ; Brier de P(T > 2,5) |
| diagnostics | calibration de P(T ≥ 3) par décile, pente et ordonnée ; PIT randomisé ; couverture de [q10 ; q90] ; log-loss par équipe, du score exact ; Brier du 1N2 |
| descriptives | MAE et RMSE de E[T], jamais pour sélectionner |

Une probabilité **nulle** sur le total observé donne une perte infinie : elle est refusée
explicitement (`ZeroProbabilityError`), jamais remplacée par un plancher silencieux.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SUM_TOLERANCE = 1e-6
RPS_CATEGORIES = 8
"""RPS sur 0, 1, …, 6 et « 7 et plus » (8 catégories)."""


class ZeroProbabilityError(ValueError):
    """Une loi prédite donne une probabilité nulle au résultat observé : perte infinie."""


def _check(probs: np.ndarray) -> np.ndarray:
    probs = np.atleast_2d(np.asarray(probs, dtype=float))
    if np.isnan(probs).any():
        raise ValueError("Loi prédite avec une valeur vide : aucune métrique sur une prédiction incomplète.")
    if (probs < -1e-12).any():
        raise ValueError("Loi prédite avec une probabilité négative.")
    sums = probs.sum(axis=1)
    if np.abs(sums - 1.0).max() > SUM_TOLERANCE:
        raise ValueError(f"Loi prédite qui ne somme pas à 1 (écart maximal {np.abs(sums - 1).max():.2e}).")
    return probs


def categories(totals, n_categories: int) -> np.ndarray:
    """Indice de case de chaque total : min(t, n_categories − 1)."""
    totals = np.asarray(totals)
    if (totals < 0).any():
        raise ValueError("Total de buts négatif.")
    return np.minimum(totals.astype(int), n_categories - 1)


def collapse(probs: np.ndarray, n_categories: int) -> np.ndarray:
    """Regroupe les dernières cases : (n, K) → (n, n_categories), la dernière case recevant le reste."""
    probs = np.atleast_2d(probs)
    return np.hstack([probs[:, : n_categories - 1], probs[:, n_categories - 1 :].sum(axis=1, keepdims=True)])


# ------------------------------------------------------------------------------ règles de score


def log_loss_by_match(probs, totals) -> np.ndarray:
    """−log P̂(T = t) pour chaque match (logarithme népérien)."""
    probs = _check(probs)
    index = categories(totals, probs.shape[1])
    p = probs[np.arange(len(probs)), index]
    if (p <= 0).any():
        raise ZeroProbabilityError(
            f"{int((p <= 0).sum())} match(s) dont le total observé a une probabilité prédite nulle : perte infinie."
        )
    return -np.log(p)


def rps_by_match(probs, totals, n_categories: int = RPS_CATEGORIES) -> np.ndarray:
    """RPS : Σ_k (F̂(k) − 1{t ≤ k})² / (K − 1), sur K catégories ordonnées (0 à 6, « 7 et plus »).

    F̂ est la fonction de répartition prédite ; la dernière catégorie ne compte pas (F = 1 des
    deux côtés). Le RPS récompense une loi « proche » du résultat : prédire 3 quand il y a 4
    buts coûte moins que prédire 0.
    """
    probs = collapse(_check(probs), n_categories)
    observed = np.zeros_like(probs)
    observed[np.arange(len(probs)), categories(totals, n_categories)] = 1.0
    diff = np.cumsum(probs, axis=1)[:, :-1] - np.cumsum(observed, axis=1)[:, :-1]
    return (diff**2).sum(axis=1) / (n_categories - 1)


def prob_over(probs, threshold: float = 2.5) -> np.ndarray:
    """P̂(T > seuil) = Σ_{k > seuil} P̂(T = k)."""
    probs = _check(probs)
    return probs[:, np.arange(probs.shape[1]) > threshold].sum(axis=1)


def brier_binary_by_match(p, outcome) -> np.ndarray:
    """(p − o)² pour un événement binaire (o ∈ {0, 1})."""
    return (np.asarray(p, dtype=float) - np.asarray(outcome, dtype=float)) ** 2


def log_loss_binary_by_match(p, outcome) -> np.ndarray:
    """−[o log p + (1 − o) log(1 − p)] ; une probabilité de 0 ou 1 contredite est refusée."""
    p, outcome = np.asarray(p, dtype=float), np.asarray(outcome, dtype=float)
    q = np.where(outcome == 1, p, 1 - p)
    if (q <= 0).any():
        raise ZeroProbabilityError(f"{int((q <= 0).sum())} événement(s) observé(s) de probabilité prédite nulle.")
    return -np.log(q)


def brier_over_by_match(probs, totals, threshold: float = 2.5) -> np.ndarray:
    """Brier de P̂(T > 2,5) : (P̂(T > 2,5) − 1{t > 2,5})²."""
    return brier_binary_by_match(prob_over(probs, threshold), np.asarray(totals) > threshold)


def expected_total(probs) -> np.ndarray:
    """E[T] approché par la loi repliée (la case « 10 et plus » compte pour 10) : descriptif seulement."""
    probs = _check(probs)
    return probs @ np.arange(probs.shape[1])


def mae_rmse(expected, totals) -> tuple[float, float]:
    """MAE et RMSE de E[T] : descriptifs, jamais pour sélectionner (ADR-0009)."""
    error = np.asarray(expected, dtype=float) - np.asarray(totals, dtype=float)
    return float(np.abs(error).mean()), float(np.sqrt((error**2).mean()))


# ------------------------------------------------------------------------------ calibration


def calibration_table(p, outcome, n_bins: int = 10) -> pd.DataFrame:
    """Probabilité moyenne prédite et fréquence observée par décile de p (classes d'effectifs égaux).

    Colonnes : `bin`, `n`, `p_mean`, `observed`, `gap` (observé − prédit).
    """
    p, outcome = np.asarray(p, dtype=float), np.asarray(outcome, dtype=float)
    order = np.argsort(p, kind="mergesort")
    bins = np.empty(len(p), dtype=int)
    bins[order] = np.arange(len(p)) * n_bins // max(len(p), 1)
    frame = pd.DataFrame({"bin": bins, "p": p, "o": outcome})
    table = frame.groupby("bin").agg(n=("p", "size"), p_mean=("p", "mean"), observed=("o", "mean")).reset_index()
    table["gap"] = table["observed"] - table["p_mean"]
    return table


def calibration_mean_abs_gap(table: pd.DataFrame) -> float:
    """Écart absolu moyen par décile |observé − prédit| (règle de décision, critère iii)."""
    return float(table["gap"].abs().mean())


def calibration_slope_intercept(p, outcome) -> tuple[float, float]:
    """Régression logistique de o sur logit(p) : (ordonnée, pente). Parfait : (0, 1).

    Pente < 1 : prédictions trop extrêmes (surconfiance) ; > 1 : trop prudentes.
    """
    import statsmodels.api as sm

    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    outcome = np.asarray(outcome, dtype=float)
    logit = np.log(p / (1 - p))
    if np.ptp(logit) < 1e-9:
        # Prévision constante (B0) : pente indéfinie ; l'ordonnée est l'écart global en log-odds.
        rate = np.clip(outcome.mean(), 1e-12, 1 - 1e-12)
        return float(np.log(rate / (1 - rate)) - logit[0]), float("nan")
    design = sm.add_constant(logit, has_constant="add")
    result = sm.GLM(outcome, design, family=sm.families.Binomial()).fit()
    intercept, slope = result.params
    return float(intercept), float(slope)


def randomized_pit(probs, totals, rng: np.random.Generator) -> np.ndarray:
    """PIT randomisé d'une loi discrète : F̂(t − 1) + U · P̂(T = t), U uniforme sur [0, 1].

    Pour un modèle bien calibré, les valeurs sont uniformes sur [0, 1] (histogramme plat).
    """
    probs = _check(probs)
    index = categories(totals, probs.shape[1])
    cdf = np.cumsum(probs, axis=1)
    below = np.where(index > 0, cdf[np.arange(len(probs)), np.maximum(index - 1, 0)], 0.0)
    return below + rng.uniform(size=len(probs)) * probs[np.arange(len(probs)), index]


def pit_histogram(pit, n_bins: int = 10) -> np.ndarray:
    """Effectifs relatifs du PIT par classe de largeur 1/n_bins (uniforme : 1/n_bins partout)."""
    counts, _ = np.histogram(np.asarray(pit), bins=n_bins, range=(0.0, 1.0))
    return counts / max(len(pit), 1)


# ------------------------------------------------------------------------------ intervalle


def prediction_interval(probs, lower: float = 0.10, upper: float = 0.90) -> tuple[np.ndarray, np.ndarray]:
    """[q_lower ; q_upper] de la loi discrète : plus petits k tels que F̂(k) ≥ lower, puis ≥ upper.

    La borne 10 veut dire « 10 et plus ».
    """
    cdf = np.cumsum(_check(probs), axis=1)
    lo = (cdf < lower - 1e-12).sum(axis=1)
    hi = (cdf < upper - 1e-12).sum(axis=1)
    return lo, np.minimum(hi, cdf.shape[1] - 1)


def announced_coverage(probs, lo, hi) -> np.ndarray:
    """P̂(T ∈ [lo ; hi]) : la couverture annoncée de chaque intervalle (ADR-0009)."""
    probs = _check(probs)
    k = np.arange(probs.shape[1])
    inside = (k >= np.asarray(lo)[:, None]) & (k <= np.asarray(hi)[:, None])
    return (probs * inside).sum(axis=1)


def coverage(probs, totals, lower: float = 0.10, upper: float = 0.90) -> dict:
    """Couverture observée de [q10 ; q90] contre la moyenne des couvertures annoncées.

    Critère (ADR-0009) : `observed − announced` à ±3 points.
    """
    lo, hi = prediction_interval(probs, lower, upper)
    index = categories(totals, np.atleast_2d(probs).shape[1])
    inside = (index >= lo) & (index <= hi)
    announced = announced_coverage(probs, lo, hi)
    return {
        "observed": float(inside.mean()),
        "announced": float(announced.mean()),
        "gap": float(inside.mean() - announced.mean()),
        "mean_width": float((hi - lo).mean()),
    }


# ------------------------------------------------------------------------------ score, 1N2


def exact_score_log_loss_by_match(joint, home_goals, away_goals) -> np.ndarray:
    """−log P̂(Y_dom = a, Y_ext = b) ; la dernière ligne et la dernière colonne valent « G − 1 et plus »."""
    joint = np.asarray(joint, dtype=float)
    g = joint.shape[1]
    a = np.minimum(np.asarray(home_goals, dtype=int), g - 1)
    b = np.minimum(np.asarray(away_goals, dtype=int), g - 1)
    p = joint[np.arange(len(joint)), a, b]
    if (p <= 0).any():
        raise ZeroProbabilityError(f"{int((p <= 0).sum())} score(s) observé(s) de probabilité prédite nulle.")
    return -np.log(p)


def brier_1x2_by_match(outcome_probs, home_goals, away_goals) -> np.ndarray:
    """Brier multi-classe du 1N2 : Σ_k (p_k − o_k)² sur les trois issues (définition des résultats antérieurs)."""
    home_goals, away_goals = np.asarray(home_goals), np.asarray(away_goals)
    observed = np.column_stack([home_goals > away_goals, home_goals == away_goals, home_goals < away_goals])
    return ((np.asarray(outcome_probs, dtype=float) - observed) ** 2).sum(axis=1)
