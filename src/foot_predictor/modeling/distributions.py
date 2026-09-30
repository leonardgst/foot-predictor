"""Lois discrètes du nombre de buts : par équipe, jointe, total (ADR-0009).

Convention commune à tous les modèles (`modeling/models/`) : la **loi du total** d'un match
est un vecteur de 11 probabilités, P(T = k) pour k de 0 à 9 et P(T ≥ 10) en dernière case
(`TOTAL_CATEGORIES`). Les calculs internes se font sur un support plus large
(`SUPPORT` buts par équipe), puis la queue est **repliée** dans la dernière case : aucune
probabilité n'est perdue ni inventée.

Si Y_dom ~ Poisson(λ_dom) et Y_ext ~ Poisson(λ_ext) sont indépendants,
T = Y_dom + Y_ext ~ Poisson(λ_dom + λ_ext). Avec une dépendance (Dixon-Coles), on passe par
la loi jointe P(Y_dom = a, Y_ext = b), puis P(T = k) = Σ_{a+b=k} P(a, b).
"""

from __future__ import annotations

import numpy as np
from scipy.stats import nbinom, poisson

K_MAX = 10
"""Dernière case de la loi du total : « 10 buts et plus »."""
TOTAL_CATEGORIES = K_MAX + 1
SUPPORT = 26
"""Buts par équipe calculés exactement (0 à 25) avant repli ; la masse au-delà est < 1e-12 pour λ ≤ 5."""
JOINT_GOALS = K_MAX + 1
"""Loi jointe du score sur 0..9 et « 10 et plus » pour chaque équipe (score exact, 1N2)."""


def fold(pmf: np.ndarray, k_max: int = K_MAX) -> np.ndarray:
    """Replie une loi (n, m) sur 0..k_max : la dernière case reçoit P(X ≥ k_max) = 1 − P(X < k_max).

    La dernière case se calcule par complément, pour que chaque ligne somme exactement à 1,
    queue au-delà du support comprise.
    """
    pmf = np.atleast_2d(np.asarray(pmf, dtype=float))
    head = pmf[:, :k_max]
    tail = np.clip(1.0 - head.sum(axis=1, keepdims=True), 0.0, None)
    return np.hstack([head, tail])


def poisson_pmf(lam: np.ndarray, support: int = SUPPORT) -> np.ndarray:
    """P(Y = y) pour y de 0 à support − 1, une ligne par valeur de λ."""
    lam = np.asarray(lam, dtype=float).reshape(-1, 1)
    return poisson.pmf(np.arange(support), lam)


def negbin_pmf(mu: np.ndarray, alpha: float, support: int = SUPPORT) -> np.ndarray:
    """Binomiale négative de moyenne μ et de variance μ + α μ² (paramétrisation NB2).

    En notation scipy : n = 1/α, p = n / (n + μ).
    """
    mu = np.asarray(mu, dtype=float).reshape(-1, 1)
    n = 1.0 / alpha
    return nbinom.pmf(np.arange(support), n, n / (n + mu))


def total_from_independent(home: np.ndarray, away: np.ndarray, k_max: int = K_MAX) -> np.ndarray:
    """Loi du total de deux comptages indépendants (convolution ligne par ligne), repliée sur 0..k_max."""
    home, away = np.atleast_2d(home), np.atleast_2d(away)
    total = np.array([np.convolve(h, a)[: home.shape[1]] for h, a in zip(home, away, strict=True)])
    return fold(total, k_max)


def poisson_total(lambda_home: np.ndarray, lambda_away: np.ndarray, k_max: int = K_MAX) -> np.ndarray:
    """Loi du total de deux Poisson indépendants : Poisson(λ_dom + λ_ext), repliée."""
    lam = np.asarray(lambda_home, dtype=float) + np.asarray(lambda_away, dtype=float)
    return fold(poisson_pmf(lam, support=k_max + 1), k_max)


def total_from_joint(joint: np.ndarray, k_max: int = K_MAX) -> np.ndarray:
    """Loi du total à partir de lois jointes (n, G, G) : P(T = k) = Σ_{a+b=k} P(a, b), repliée."""
    joint = np.asarray(joint, dtype=float)
    n, g, _ = joint.shape
    total = np.zeros((n, 2 * g - 1))
    for a in range(g):
        total[:, a : a + g] += joint[:, a, :]
    return fold(total, k_max)


def independent_joint(home: np.ndarray, away: np.ndarray) -> np.ndarray:
    """Loi jointe de deux comptages indépendants : P(a, b) = P_dom(a) · P_ext(b)."""
    return np.einsum("na,nb->nab", np.atleast_2d(home), np.atleast_2d(away))


def outcome_probabilities(joint: np.ndarray) -> np.ndarray:
    """(P(1), P(N), P(2)) de chaque loi jointe : domicile gagne (a > b), nul, extérieur gagne (a < b).

    Les trois masses sont calculées séparément puis normalisées par la masse totale (une loi
    tronquée somme à un peu moins de 1). Sur une loi repliée, « 10 et plus » contre « 10 et
    plus » compte comme un nul : cas négligeable.
    """
    joint = np.asarray(joint, dtype=float)
    lower = np.tril(np.ones(joint.shape[1:]), k=-1)
    home = (joint * lower).sum(axis=(1, 2))
    away = (joint * lower.T).sum(axis=(1, 2))
    draw = np.trace(joint, axis1=1, axis2=2)
    mass = home + draw + away
    return np.column_stack([home, draw, away]) / mass[:, None]
