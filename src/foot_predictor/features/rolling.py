"""Moyennes glissantes pondérées (groupe G2) : buts et `xg_proxy`, pour et contre (ADR-0032).

Fonction pure : `compute_rolling(matches, coefficients)` lit une table de matchs (porte
`features/sources.py`) et renvoie une ligne par (match, équipe) pour les championnats des
échelles (top 5 et D2). Aucun accès à la base.

Pour l'équipe e au match du jour J, et une quantité x (buts marqués, buts encaissés,
`xg_proxy` pour, `xg_proxy` contre), sur ses matchs de **championnat** i terminés avant le
jour J et vieux d'au plus A jours (A = 730) :

    poids      w_i = 0,5^((J − j_i) / h)          (demi-vie h en jours : 60, 120 ou 240)
    somme      W   = Σ w_i                          (poids d'information, variable à part)
    moyenne    x̂   = (Σ w_i · x_i + k · μ) / (W + k)

où μ est la moyenne de x par équipe et par match dans le championnat du match, sur les
A jours avant J, et k = 3 le poids a priori (en « matchs »). Quand W → ∞, x̂ tend vers la
moyenne pondérée de l'équipe ; quand W = 0, il n'y a pas d'historique : **la valeur reste
vide** (et W = 0 le dit), jamais μ ni 0 (rapport I.8).

Pourquoi en jours et non en matchs : la pause d'été compte (un match de mai pèse moins en
août qu'un match de la semaine précédente). Pas de remise à zéro à chaque saison (rapport
H.4) : les matchs de la saison précédente restent, avec un poids qui décroît.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from foot_predictor.features import xg_proxy
from foot_predictor.features.leagues import LADDERS

HALF_LIVES = (60, 120, 240)
"""Demi-vies candidates, en jours. Le choix se fait en partie 4, par validation interne à chaque pli."""
MAX_AGE_DAYS = 730
PRIOR_WEIGHT = 3.0

QUANTITIES = ("goals_for", "goals_against", "xgp_for", "xgp_against")


def team_rows(matches: pd.DataFrame, coefficients: xg_proxy.XgProxyCoefficients) -> pd.DataFrame:
    """Une ligne par (match, équipe) de championnat des échelles, avec les quantités à lisser.

    `history` : la ligne alimente les moyennes (match terminé, non exclu, score connu).
    Les quantités d'une ligne qui n'est pas de l'historique sont vidées : un match à venir
    ou exclu ne donne jamais de valeur, même par erreur.
    """
    frame = matches[matches["api_league_id"].isin(list(LADDERS))]
    parts = []
    for side, other in (("home", "away"), ("away", "home")):
        part = pd.DataFrame(
            {
                "match_id": frame["match_id"],
                "match_day": pd.to_datetime(frame["match_day"]),
                "competition_id": frame["competition_id"],
                "team_id": frame[f"{side}_team_id"],
                "is_home": side == "home",
                "goals_for": frame[f"{side}_goals_90"].astype("Float64"),
                "goals_against": frame[f"{other}_goals_90"].astype("Float64"),
                "xgp_for": xg_proxy.apply(coefficients, frame[f"{side}_shots_fd"], frame[f"{side}_sot_fd"]).to_numpy(),
                "xgp_against": xg_proxy.apply(
                    coefficients, frame[f"{other}_shots_fd"], frame[f"{other}_sot_fd"]
                ).to_numpy(),
                "history": (
                    (frame["status"] == "played")
                    & ~frame["excluded"].astype(bool)
                    & frame["home_goals_90"].notna()
                    & frame["away_goals_90"].notna()
                ).to_numpy(),
            }
        )
        parts.append(part)
    rows = pd.concat(parts, ignore_index=True)
    for column in QUANTITIES:
        rows.loc[~rows["history"], column] = pd.NA
    rows["day"] = (rows["match_day"] - pd.Timestamp("2000-01-01")).dt.days.astype(int)
    return rows.sort_values(["team_id", "day", "match_id"], kind="mergesort").reset_index(drop=True)


def league_means(rows: pd.DataFrame, max_age: int = MAX_AGE_DAYS) -> pd.DataFrame:
    """μ par ligne : moyenne par équipe-match de chaque quantité dans le championnat du match,
    sur les `max_age` jours **avant** le jour du match (jour J exclu)."""
    out = pd.DataFrame(index=rows.index)
    # Chaque match compte deux fois (une valeur par équipe) : μ est une moyenne par équipe-match.
    for name, columns in (("goals", ["goals_for", "goals_against"]), ("xgp", ["xgp_for", "xgp_against"])):
        stacked = pd.concat(
            [rows[["competition_id", "day"]].assign(value=rows[c].astype("float64")) for c in columns],
            ignore_index=True,
        ).dropna(subset=["value"])
        means = np.full(len(rows), np.nan)
        for competition, target_index in rows.groupby("competition_id").groups.items():
            hist = stacked[stacked["competition_id"] == competition]
            daily = hist.groupby("day")["value"].agg(["sum", "count"]).sort_index()
            days = daily.index.to_numpy()
            csum = np.concatenate([[0.0], np.cumsum(daily["sum"].to_numpy())])
            ccount = np.concatenate([[0.0], np.cumsum(daily["count"].to_numpy())])
            target_days = rows.loc[target_index, "day"].to_numpy()
            hi = np.searchsorted(days, target_days, side="left")  # jours < J
            lo = np.searchsorted(days, target_days - max_age, side="left")  # jours >= J − A
            count = ccount[hi] - ccount[lo]
            total = csum[hi] - csum[lo]
            with np.errstate(invalid="ignore", divide="ignore"):
                means[rows.index.get_indexer(target_index)] = np.where(count > 0, total / count, np.nan)
        out[name] = means
    return out


def compute_rolling(
    matches: pd.DataFrame,
    coefficients: xg_proxy.XgProxyCoefficients,
    half_lives: tuple[int, ...] = HALF_LIVES,
    max_age: int = MAX_AGE_DAYS,
    prior_weight: float = PRIOR_WEIGHT,
) -> pd.DataFrame:
    """Glissants d'avant-match, une ligne par (match, équipe) de championnat des échelles.

    Colonnes, pour chaque demi-vie h : `goals_for_ewm_h{h}`, `goals_against_ewm_h{h}`,
    `xgp_for_ewm_h{h}`, `xgp_against_ewm_h{h}` (moyennes retirées vers le championnat),
    `goals_weight_h{h}` et `xgp_weight_h{h}` (sommes des poids) ; plus
    `days_since_last_league_match` (ancienneté du dernier match de championnat retenu,
    vide au-delà de `max_age` jours).
    """
    rows = team_rows(matches, coefficients)
    mu = league_means(rows, max_age)
    result = {name: np.full(len(rows), np.nan) for name in _output_columns(half_lives)}
    # Le poids se sépare : 0,5^((J − j)/h) = 0,5^(J/h) · 0,5^(−j/h). Une somme pondérée sur la
    # fenêtre [J − A, J − 1] devient une différence de sommes cumulées des 0,5^(−j/h) · x_j, prises
    # dans l'ordre chronologique. Un historique tronqué à une date en est exactement le préfixe :
    # les valeurs d'avant la coupe sont identiques au bit près (contrôle d'invariance, 3.7).
    # L'échelle 0,5^(−j/h) croît au plus jusqu'à 2^160 environ (j compté depuis 2000) : sans risque.
    for _team, index in rows.groupby("team_id", sort=False).groups.items():
        idx = rows.index.get_indexer(index)
        day = rows["day"].to_numpy()[idx].astype(np.int64)
        history = rows["history"].to_numpy()[idx]
        values = {q: rows[q].to_numpy(dtype="float64", na_value=np.nan)[idx] for q in QUANTITIES}
        hi = np.searchsorted(day, day, side="left")  # premier match du jour J ou après : exclu
        lo = np.searchsorted(day, day - max_age, side="left")  # premier match du jour J − A ou après
        positions = np.where(history, np.arange(len(day)), -1)
        last_valid = np.maximum.accumulate(positions) if len(day) else positions
        previous = np.where(hi > 0, last_valid[np.maximum(hi - 1, 0)], -1)
        gap_last = np.where(previous >= 0, day - day[np.maximum(previous, 0)], np.nan)
        result["days_since_last_league_match"][idx] = np.where(gap_last <= max_age, gap_last, np.nan)
        for h in half_lives:
            scale_past = 0.5 ** (-day / h)
            scale_now = 0.5 ** (day / h)
            for kind, quantities in (("goals", ("goals_for", "goals_against")), ("xgp", ("xgp_for", "xgp_against"))):
                known = history & ~np.isnan(values[quantities[0]]) & ~np.isnan(values[quantities[1]])
                w = np.where(known, scale_past, 0.0)
                cum_w = np.concatenate([[0.0], np.cumsum(w)])
                weight_sum = (cum_w[hi] - cum_w[lo]) * scale_now
                weight_sum = np.where(hi > lo, weight_sum, 0.0)
                result[f"{kind}_weight_h{h}"][idx] = weight_sum
                prior = mu[kind].to_numpy()[idx]
                for q in quantities:
                    cum_x = np.concatenate([[0.0], np.cumsum(w * np.nan_to_num(values[q]))])
                    total = np.where(hi > lo, (cum_x[hi] - cum_x[lo]) * scale_now, 0.0)
                    with np.errstate(invalid="ignore", divide="ignore"):
                        shrunk = (total + prior_weight * prior) / (weight_sum + prior_weight)
                    result[f"{q}_ewm_h{h}"][idx] = np.where(weight_sum > 0, shrunk, np.nan)
    out = rows[["match_id", "team_id", "is_home"]].copy()
    for name, values in result.items():
        out[name] = values
    return out.sort_values(["match_id", "is_home"], ascending=[True, False], kind="mergesort").reset_index(drop=True)


def _output_columns(half_lives: tuple[int, ...]) -> list[str]:
    names = []
    for h in half_lives:
        names += [f"{q}_ewm_h{h}" for q in QUANTITIES]
        names += [f"goals_weight_h{h}", f"xgp_weight_h{h}"]
    return names + ["days_since_last_league_match"]
