"""Modèle B -- Dixon-Coles hybride (section 5.2 de docs/MODELE_MATHEMATIQUE.md),
implémenté à la main (esprit pédagogique du projet, cf. README).

    lambda_home = exp(alpha_H - beta_A + gamma + x_home^T delta)
    lambda_away = exp(alpha_A - beta_H + x_away^T delta)
    P(y_home=a, y_away=b) = tau_{lambda,mu}(a,b) * Poisson(a; lambda_home) * Poisson(b; lambda_away)

Choix d'implémentation à propos de `x^T delta` : le document note ce terme
`x_m` (indexé par match, un seul vecteur), mais les deux équations partagent la
même famille de features que le Modèle A (section 2), qui elle est spécifique
à la perspective (bloc "own" vs bloc "adversaire" inversés). On réutilise donc
ici exactement les x_i de dataset.py (own_*, opp_*, one-hot championnat), MOINS
la colonne `is_home` -- qui devient inutile puisque l'avantage du terrain est
désormais porté par le paramètre `gamma`, dédié et estimé, plutôt que par un
coefficient de régression. C'est l'interprétation qui prolonge le plus
naturellement le Modèle A ("nos features ajoutées EN PLUS des forces
latentes"), documentée ici pour qu'elle puisse être révisée si besoin.

Identifiabilité (cf. section 5.2, "Limites") : un décalage constant c ajouté à
TOUS les alpha et TOUS les beta laisse lambda_home et lambda_away inchangés
(le décalage s'annule dans alpha_H - beta_A comme dans alpha_A - beta_H). Une
seule contrainte suffit : l'attaque de l'équipe de référence (la plus petite
team_id vue à l'entraînement) est fixée à alpha = 0, toutes les autres alpha et
tous les beta (y compris celui de l'équipe de référence) restent libres.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

DELTA_EXCLUDED_COLUMNS = {"is_home"}


def tau_correction(a: int, b: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    """Fonction de correction basse-score de Dixon & Coles (1997), section 5.2
    du document. Non triviale seulement pour (a,b) in {(0,0),(1,0),(0,1),(1,1)}."""
    if a == 0 and b == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if a == 0 and b == 1:
        return 1.0 + lambda_home * rho
    if a == 1 and b == 0:
        return 1.0 + lambda_away * rho
    if a == 1 and b == 1:
        return 1.0 - rho
    return 1.0


@dataclass(frozen=True)
class MatchArrays:
    match_id: np.ndarray
    home_team_id: np.ndarray
    away_team_id: np.ndarray
    match_date: pd.Series
    y_home: np.ndarray
    y_away: np.ndarray
    x_home: np.ndarray  # (n_matches, d) -- bloc de features perspective domicile, sans is_home
    x_away: np.ndarray  # (n_matches, d) -- bloc de features perspective extérieur, sans is_home
    delta_feature_names: list[str]


def prepare_match_arrays(X: pd.DataFrame, y: pd.Series, meta: pd.DataFrame) -> MatchArrays:
    """Regroupe les lignes empilées (une par (match, équipe), section 2.4) en
    une ligne par match, séparant les deux perspectives -- réutilisé pour fit
    ET pour predict."""
    delta_feature_names = [c for c in X.columns if c not in DELTA_EXCLUDED_COLUMNS]

    df = meta.reset_index(drop=True).copy()
    df["y"] = y.reset_index(drop=True).values
    for col in delta_feature_names:
        df[col] = X[col].reset_index(drop=True).values

    home = df[df["is_home"]].set_index("match_id")
    away = df[~df["is_home"]].set_index("match_id")
    joined = home.join(away, lsuffix="_home", rsuffix="_away", how="inner")

    return MatchArrays(
        match_id=joined.index.to_numpy(),
        home_team_id=joined["team_id_home"].to_numpy(),
        away_team_id=joined["team_id_away"].to_numpy(),
        match_date=joined["match_date_home"],
        y_home=joined["y_home"].to_numpy(dtype=float),
        y_away=joined["y_away"].to_numpy(dtype=float),
        x_home=joined[[f"{c}_home" for c in delta_feature_names]].to_numpy(dtype=float),
        x_away=joined[[f"{c}_away" for c in delta_feature_names]].to_numpy(dtype=float),
        delta_feature_names=delta_feature_names,
    )


@dataclass
class DixonColesModel:
    team_ids: list[int]  # ordre = index utilisé par alpha_full / beta_full
    reference_team_id: int
    alpha: dict[int, float]
    beta: dict[int, float]
    gamma: float
    delta: np.ndarray
    delta_feature_names: list[str]
    rho: float
    xi: float
    reference_date: dt.datetime
    n_unseen_teams_at_predict: int = field(default=0, compare=False)

    def _team_strength(self, team_id: int) -> tuple[float, float]:
        alpha = self.alpha.get(team_id)
        beta = self.beta.get(team_id)
        if alpha is None or beta is None:
            self.n_unseen_teams_at_predict += 1
            return 0.0, 0.0
        return alpha, beta

    def predict_match_lambdas(self, arrays: MatchArrays) -> tuple[np.ndarray, np.ndarray]:
        n = len(arrays.home_team_id)
        alpha_h = np.empty(n)
        beta_h = np.empty(n)
        alpha_a = np.empty(n)
        beta_a = np.empty(n)
        for i in range(n):
            alpha_h[i], beta_h[i] = self._team_strength(int(arrays.home_team_id[i]))
            alpha_a[i], beta_a[i] = self._team_strength(int(arrays.away_team_id[i]))

        lambda_home = np.exp(alpha_h - beta_a + self.gamma + arrays.x_home @ self.delta)
        lambda_away = np.exp(alpha_a - beta_h + arrays.x_away @ self.delta)
        return lambda_home, lambda_away


def _time_decay_weights(match_date: pd.Series, reference_date: dt.datetime, xi: float) -> np.ndarray:
    delta_days = (reference_date - match_date).dt.total_seconds() / 86400.0
    delta_days = np.clip(delta_days.to_numpy(dtype=float), 0.0, None)
    return np.exp(-xi * delta_days)


def _unpack(params: np.ndarray, n_teams: int, n_delta: int, ref_idx: int) -> tuple:
    alpha_free = params[: n_teams - 1]
    beta_full = params[n_teams - 1 : 2 * n_teams - 1]
    gamma = params[2 * n_teams - 1]
    delta = params[2 * n_teams : 2 * n_teams + n_delta]
    rho = params[2 * n_teams + n_delta]
    alpha_full = np.insert(alpha_free, ref_idx, 0.0)
    return alpha_full, beta_full, gamma, delta, rho


def _negative_log_likelihood(
    params: np.ndarray,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    x_home: np.ndarray,
    x_away: np.ndarray,
    y_home: np.ndarray,
    y_away: np.ndarray,
    weights: np.ndarray,
    n_teams: int,
    n_delta: int,
    ref_idx: int,
) -> float:
    alpha_full, beta_full, gamma, delta, rho = _unpack(params, n_teams, n_delta, ref_idx)

    lambda_home = np.exp(alpha_full[home_idx] - beta_full[away_idx] + gamma + x_home @ delta)
    lambda_away = np.exp(alpha_full[away_idx] - beta_full[home_idx] + x_away @ delta)

    tau = np.ones_like(lambda_home)
    m00 = (y_home == 0) & (y_away == 0)
    m10 = (y_home == 1) & (y_away == 0)
    m01 = (y_home == 0) & (y_away == 1)
    m11 = (y_home == 1) & (y_away == 1)
    tau[m00] = 1.0 - lambda_home[m00] * lambda_away[m00] * rho
    tau[m10] = 1.0 + lambda_away[m10] * rho
    tau[m01] = 1.0 + lambda_home[m01] * rho
    tau[m11] = 1.0 - rho
    tau = np.clip(tau, 1e-10, None)  # garde-fou numérique pendant l'optimisation

    log_poisson_home = y_home * np.log(lambda_home) - lambda_home - gammaln(y_home + 1)
    log_poisson_away = y_away * np.log(lambda_away) - lambda_away - gammaln(y_away + 1)
    log_lik = np.log(tau) + log_poisson_home + log_poisson_away

    return float(-np.sum(weights * log_lik))


def fit_dixon_coles(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    meta_train: pd.DataFrame,
    xi: float,
    reference_date: dt.datetime | None = None,
) -> DixonColesModel:
    """Estimation par MLE pondéré dans le temps (scipy.optimize, L-BFGS-B).
    `xi` est un hyperparamètre fourni par l'appelant (voir
    modeling/run_comparison.py pour la recherche de sa valeur sur le train
    set) -- pas ré-estimé conjointement avec les autres paramètres."""
    arrays = prepare_match_arrays(X_train, y_train, meta_train)
    reference_date = reference_date or arrays.match_date.max()

    team_ids = sorted(set(arrays.home_team_id.tolist()) | set(arrays.away_team_id.tolist()))
    n_teams = len(team_ids)
    team_index = {tid: i for i, tid in enumerate(team_ids)}
    ref_idx = 0  # équipe de référence = plus petite team_id (team_ids est trié)
    reference_team_id = team_ids[ref_idx]

    home_idx = np.array([team_index[t] for t in arrays.home_team_id])
    away_idx = np.array([team_index[t] for t in arrays.away_team_id])
    weights = _time_decay_weights(arrays.match_date, reference_date, xi)

    n_delta = arrays.x_home.shape[1]
    n_params = (n_teams - 1) + n_teams + 1 + n_delta + 1

    x0 = np.zeros(n_params)
    x0[2 * n_teams - 1] = np.log(1.3)  # gamma initial ~ avantage terrain typique

    bounds = [(None, None)] * (n_params - 1) + [(-0.99, 0.99)]  # rho borné

    result = minimize(
        _negative_log_likelihood,
        x0,
        args=(home_idx, away_idx, arrays.x_home, arrays.x_away, arrays.y_home, arrays.y_away, weights, n_teams, n_delta, ref_idx),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 500},
    )

    alpha_full, beta_full, gamma, delta, rho = _unpack(result.x, n_teams, n_delta, ref_idx)

    return DixonColesModel(
        team_ids=team_ids,
        reference_team_id=reference_team_id,
        alpha={tid: float(alpha_full[i]) for i, tid in enumerate(team_ids)},
        beta={tid: float(beta_full[i]) for i, tid in enumerate(team_ids)},
        gamma=float(gamma),
        delta=delta,
        delta_feature_names=arrays.delta_feature_names,
        rho=float(rho),
        xi=xi,
        reference_date=reference_date,
    )
