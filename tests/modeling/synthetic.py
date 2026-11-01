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


COHESION_NAMES = [f"xi_cohesion_ewm_h{h}" for h in ("3", "5", "10", "20", "inf")] + [
    "xi_cohesion_reset",
    "xi_cohesion_win10",
]
H2_BASE = [
    "coach_tenure_days", "coach_is_new", "xi_quality", "xi_regulars_missing", "xi_mean_age",
    "xi_overlap_prev", "xi_new_starters", *COHESION_NAMES,
]  # fmt: skip


def with_composition(rows: pd.DataFrame, seed: int = 1, quality_effect: float = 0.0) -> pd.DataFrame:
    """Ajoute les colonnes H2 (G4 à G6) au jeu synthétique, avec leurs noms réels, et les colonnes de l'adversaire.

    `quality_effect` > 0 : les buts sont retirés de nouveau avec log λ += effet · (qualité de l'équipe − qualité
    de l'adversaire), pour tester qu'un modèle retrouve un effet connu de `xi_quality`.
    """
    rng = np.random.default_rng(seed)
    frame = rows.copy()
    n = len(frame)
    frame["xi_quality"] = rng.normal(7.0, 0.1, n)
    frame["xi_regulars_missing"] = rng.uniform(0, 0.8, n)
    frame["xi_mean_age"] = rng.normal(27, 1.5, n)
    frame["xi_overlap_prev"] = rng.integers(3, 12, n).astype(float)
    frame["xi_new_starters"] = rng.integers(0, 4, n).astype(float)
    for name in COHESION_NAMES:
        frame[name] = rng.uniform(0, 1, n)
    frame["coach_tenure_days"] = rng.integers(0, 366, n).astype(float)
    frame["coach_is_new"] = (rng.random(n) < 0.1).astype(float)
    opp = frame[["match_id", "team_id", *H2_BASE]].rename(
        columns={"team_id": "opp_team_id", **{c: f"opp_{c}" for c in H2_BASE}}
    )
    frame = frame.merge(opp, on=["match_id", "opp_team_id"], how="left")
    if quality_effect:
        mean = np.exp(
            0.3 + 0.25 * frame["is_home"] + quality_effect * (frame["xi_quality"] - frame["opp_xi_quality"]) / 0.1
        )
        frame["goals_for"] = rng.poisson(mean.to_numpy())
        goals = frame.set_index(["match_id", "team_id"])["goals_for"]
        frame["goals_against"] = goals.reindex(
            pd.MultiIndex.from_arrays([frame["match_id"], frame["opp_team_id"]])
        ).to_numpy()
    return frame


def synthetic_odds(data: pd.DataFrame) -> pd.DataFrame:
    """Probabilités de marché synthétiques (avant clôture et clôture) pour chaque match de `data`."""
    from foot_predictor.modeling.models import market

    rng = np.random.default_rng(1)
    ids = np.sort(data["match_id"].unique())
    frames = []
    for version in ("avant_cloture", "cloture"):
        over = rng.uniform(1.6, 2.4, len(ids))
        frames.append(
            pd.DataFrame({"match_id": ids, "version": version, "odds_over_2_5": over, "odds_under_2_5": 3.9 - over})
        )
    return market.market_probabilities(pd.concat(frames, ignore_index=True))
