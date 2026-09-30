"""Jeu synthétique proche du jeu réel, tiré d'un modèle **connu**, pour tester les modèles M1 à M6.

Pour chaque match, la « force » s de chaque équipe est tirée une fois par saison ; l'Elo avant
match vaut 1500 + 100 · s + bruit. Les buts suivent

    log λ_e = a_ligue + 0,25 · domicile + 0,25 · (s_e − s_adv) + ρ-lien nul,

donc Y ~ Poisson(λ) indépendants (sauf `dependence` > 0, qui ajoute un choc commun). Les colonnes
G2 et G3 sont des variables bruitées, corrélées à la force, avec leurs noms réels.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from foot_predictor.modeling.design import HALF_LIVES

LEAGUE_LEVEL = {39: 0.35, 140: 0.25, 78: 0.40, 135: 0.30, 61: 0.28, 40: 0.20}
TRUE_HOME = 0.25
TRUE_STRENGTH = 0.25


def realistic_rows(
    seed: int = 0,
    seasons=range(2015, 2025),
    leagues=(39, 140),
    teams_per_league: int = 12,
    rounds: int = 22,
    dispersion: float = 0.0,
    dependence: float = 0.0,
) -> pd.DataFrame:
    """Lignes (match, équipe) ; `dispersion` > 0 : Poisson-Gamma (surdispersion) ; `dependence` : choc commun."""
    rng = np.random.default_rng(seed)
    rows, mid = [], 0
    for season in seasons:
        for league in leagues:
            strength = rng.normal(0, 1, teams_per_league)
            teams = [league * 100 + t for t in range(teams_per_league)]
            for r in range(rounds):
                order = rng.permutation(teams_per_league)
                day = dt.date(season, 8, 10) + dt.timedelta(days=7 * r)
                for i in range(0, teams_per_league, 2):
                    h, a = order[i], order[i + 1]
                    mid += 1
                    diff = strength[h] - strength[a]
                    lam = np.exp(
                        LEAGUE_LEVEL[league] + np.array([TRUE_HOME, 0.0]) + TRUE_STRENGTH * np.array([diff, -diff])
                    )
                    if dispersion:
                        lam = lam * rng.gamma(1 / dispersion, dispersion, 2)
                    if dependence:
                        lam = lam * np.exp(dependence * rng.normal())
                    goals = rng.poisson(lam)
                    for side, (me, opp) in enumerate(((h, a), (a, h))):
                        rec = {
                            "match_id": mid, "team_id": teams[me], "opp_team_id": teams[opp],
                            "is_home": side == 0, "season_year": season, "api_league_id": league,
                            "eval_population": league in (39, 140, 78, 135, 61),
                            "goals_for": int(goals[side]), "goals_against": int(goals[1 - side]),
                            "match_day": day, "match_date": pd.Timestamp(day, tz="UTC"),
                            "round": f"Regular Season - {r + 1}",
                            "behind_closed_doors": int(season == 2020 and r < 10),
                            "elo_pre": 1500 + 100 * strength[me] + rng.normal(0, 30),
                            "opp_elo_pre": 1500 + 100 * strength[opp] + rng.normal(0, 30),
                            "rest_days": float(rng.integers(3, 9)), "opp_rest_days": float(rng.integers(3, 9)),
                            "matches_last_14d": int(rng.integers(1, 4)), "opp_matches_last_14d": int(rng.integers(1, 4)),
                            "european_match_last_4d": bool(rng.random() < 0.1),
                            "opp_european_match_last_4d": bool(rng.random() < 0.1),
                        }  # fmt: skip
                        for h_life in HALF_LIVES:
                            noise = rng.normal(0, 0.1, 4)
                            rec[f"goals_for_ewm_h{h_life}"] = np.exp(0.3 + 0.2 * strength[me] + noise[0])
                            rec[f"goals_against_ewm_h{h_life}"] = np.exp(0.3 - 0.2 * strength[me] + noise[1])
                            rec[f"xgp_for_ewm_h{h_life}"] = np.exp(0.3 + 0.2 * strength[me] + noise[2])
                            rec[f"xgp_against_ewm_h{h_life}"] = np.exp(0.3 - 0.2 * strength[me] + noise[3])
                        rows.append(rec)
    frame = pd.DataFrame(rows)
    # Colonnes de l'adversaire pour G2 : celles de la ligne de l'adversaire dans le même match.
    g2 = [c for c in frame.columns if "_ewm_h" in c]
    opp = frame[["match_id", "team_id", *g2]].rename(columns={"team_id": "opp_team_id", **{c: f"opp_{c}" for c in g2}})
    return frame.merge(opp, on=["match_id", "opp_team_id"], how="left")
