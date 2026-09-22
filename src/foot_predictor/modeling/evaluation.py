"""Métriques d'évaluation communes aux modèles A et B, sur la distribution
jointe du score exact -- cf. docs/MODELE_MATHEMATIQUE.md section 4.3 (produit
de deux Poisson) et 5.2 (correction Dixon-Coles).

Toutes les métriques opèrent au niveau MATCH (pas au niveau ligne) : chaque
match donne un couple (lambda_home, lambda_away) et un score réel (y_home,
y_away), et une matrice de probabilités jointes sur les scores 0..MAX_GOALS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from scipy.stats import poisson

MAX_GOALS = 10

MatrixFn = Callable[[float, float], np.ndarray]


def to_match_level(meta: pd.DataFrame, y: pd.Series, lambda_hat: np.ndarray) -> pd.DataFrame:
    """Recombine les lignes (match, équipe) empilées (section 2.4) en une ligne
    par match, avec (lambda_home, lambda_away, y_home, y_away)."""
    df = meta.reset_index(drop=True).copy()
    df["y"] = y.reset_index(drop=True).values
    df["lambda_hat"] = np.asarray(lambda_hat)

    home = df[df["is_home"]].set_index("match_id")
    away = df[~df["is_home"]].set_index("match_id")
    joined = home.join(away, lsuffix="_home", rsuffix="_away", how="inner")

    return pd.DataFrame(
        {
            "match_id": joined.index,
            "lambda_home": joined["lambda_hat_home"].astype(float).values,
            "lambda_away": joined["lambda_hat_away"].astype(float).values,
            "y_home": joined["y_home"].astype(int).values,
            "y_away": joined["y_away"].astype(int).values,
        }
    ).reset_index(drop=True)


def independent_poisson_matrix(
    lambda_home: float, lambda_away: float, max_goals: int = MAX_GOALS
) -> np.ndarray:
    """P(a,b) = Poisson(a; lambda_home) * Poisson(b; lambda_away) -- Modèle A,
    section 4.3/5.1 du document. Ligne = buts domicile, colonne = buts extérieur."""
    goals = np.arange(max_goals + 1)
    p_home = poisson.pmf(goals, lambda_home)
    p_away = poisson.pmf(goals, lambda_away)
    return np.outer(p_home, p_away)


def dixon_coles_matrix(
    lambda_home: float,
    lambda_away: float,
    rho: float,
    tau_fn: Callable[[int, int, float, float, float], float],
    max_goals: int = MAX_GOALS,
) -> np.ndarray:
    """Matrice de Modèle A corrigée par tau sur les 4 cases basses, puis
    renormalisée (la correction ne préserve pas exactement la somme à 1) --
    section 5.2 du document."""
    matrix = independent_poisson_matrix(lambda_home, lambda_away, max_goals)
    for a in (0, 1):
        for b in (0, 1):
            matrix[a, b] *= tau_fn(a, b, lambda_home, lambda_away, rho)
    return matrix / matrix.sum()


@dataclass(frozen=True)
class MatchPredictions:
    matches: pd.DataFrame  # match_id, lambda_home, lambda_away, y_home, y_away
    matrices: list[np.ndarray]  # une matrice (max_goals+1, max_goals+1) par match, même ordre


def compute_predictions(matches: pd.DataFrame, matrix_fn: MatrixFn) -> MatchPredictions:
    matrices = [matrix_fn(row.lambda_home, row.lambda_away) for row in matches.itertuples()]
    return MatchPredictions(matches=matches, matrices=matrices)


def log_loss_exact_score(predictions: MatchPredictions, max_goals: int = MAX_GOALS) -> float:
    """-log P(y_home, y_away) moyenné sur les matchs (scores au-delà de
    max_goals, extrêmement rares, sont plafonnés à max_goals)."""
    losses = []
    for row, matrix in zip(predictions.matches.itertuples(), predictions.matrices):
        a = min(int(row.y_home), max_goals)
        b = min(int(row.y_away), max_goals)
        losses.append(-np.log(max(matrix[a, b], 1e-12)))
    return float(np.mean(losses))


def outcome_probabilities(matrix: np.ndarray) -> tuple[float, float, float]:
    """(P(victoire domicile), P(nul), P(victoire extérieur)) dérivées de la
    matrice jointe -- lecture directe, pas une sortie séparée du modèle."""
    n = matrix.shape[0]
    rows_idx, cols_idx = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    p_home = matrix[rows_idx > cols_idx].sum()
    p_draw = matrix[rows_idx == cols_idx].sum()
    p_away = matrix[rows_idx < cols_idx].sum()
    return float(p_home), float(p_draw), float(p_away)


def brier_score_1x2(predictions: MatchPredictions) -> float:
    """Brier multi-classe (1N2) : moyenne de Σ_k (p_k - o_k)² sur les 3 issues."""
    scores = []
    for row, matrix in zip(predictions.matches.itertuples(), predictions.matrices):
        p_home, p_draw, p_away = outcome_probabilities(matrix)
        if row.y_home > row.y_away:
            outcome = (1.0, 0.0, 0.0)
        elif row.y_home == row.y_away:
            outcome = (0.0, 1.0, 0.0)
        else:
            outcome = (0.0, 0.0, 1.0)
        scores.append((p_home - outcome[0]) ** 2 + (p_draw - outcome[1]) ** 2 + (p_away - outcome[2]) ** 2)
    return float(np.mean(scores))


def calibration_table_home_win(predictions: MatchPredictions, n_bins: int = 10) -> pd.DataFrame:
    """Fréquence observée de victoire à domicile vs probabilité prédite,
    regroupée par tranche de probabilité (tableau de calibration demandé)."""
    p_home_pred = []
    actual_home_win = []
    for row, matrix in zip(predictions.matches.itertuples(), predictions.matrices):
        p_home, _, _ = outcome_probabilities(matrix)
        p_home_pred.append(p_home)
        actual_home_win.append(1 if row.y_home > row.y_away else 0)

    df = pd.DataFrame({"p_pred": p_home_pred, "actual": actual_home_win})
    df["bin"] = pd.cut(df["p_pred"], bins=np.linspace(0, 1, n_bins + 1), include_lowest=True)
    table = (
        df.groupby("bin", observed=True)
        .agg(n=("actual", "size"), mean_predicted=("p_pred", "mean"), observed_frequency=("actual", "mean"))
        .reset_index()
    )
    return table


def low_score_bias_table(
    predictions: MatchPredictions, scores: tuple[tuple[int, int], ...] = ((0, 0), (1, 0), (0, 1), (1, 1))
) -> pd.DataFrame:
    """Compare, pour chaque score bas documenté (Dixon & Coles 1997), la
    probabilité moyenne prédite à la fréquence réellement observée sur le test
    set -- vérifie sur nos données le biais supposé du Modèle A (section 4.3)."""
    n = len(predictions.matches)
    rows = []
    for a, b in scores:
        predicted = [matrix[a, b] for matrix in predictions.matrices]
        observed = sum(
            1
            for row in predictions.matches.itertuples()
            if int(row.y_home) == a and int(row.y_away) == b
        )
        rows.append(
            {
                "score": f"{a}-{b}",
                "mean_predicted_prob": float(np.mean(predicted)),
                "observed_frequency": observed / n,
            }
        )
    return pd.DataFrame(rows)
