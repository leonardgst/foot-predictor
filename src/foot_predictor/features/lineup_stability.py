"""Stabilité du onze (groupe G6, horizon H2) : recouvrement, cohésion par paires, nouveaux titulaires.

Fonction pure : `compute_lineup_stability(matches, lineups, team_sheets)` lit les matchs
(porte `load_matches`), les compositions (`load_lineups`) et les feuilles d'équipe
(`load_team_sheets`), et renvoie une ligne par (match, équipe) de championnat des échelles
(top 5 et D2). Aucun accès à la base. Spécification : rapport de cadrage H.3 et H.7, ADR-0047.

Pour l'équipe e au match m (jour J), avec son onze X_m connu à T-60, et son **historique** :
les matchs de championnat **terminés**, d'un jour **strictement antérieur** à J, dont le onze
est complet. Le match m n'y figure jamais (rapport H.2 : sinon le score vaudrait 1 au premier
match). Le calcul est limité au club, sans remise à zéro par saison : un joueur parti ne compte
plus, une recrue arrive avec 0.

- `xi_overlap_prev` : |X_m ∩ X_k| pour k le match précédent de l'historique (0 à 11) ;
- `xi_cohesion_ewm_h<h>` : moyenne des s_k(s_k − 1) / 110 sur l'historique, avec s_k = |X_m ∩ X_k|,
  pondérée par une décroissance exponentielle **par rang de match** : le match précédent a le
  poids 1, celui d'avant 0,5^(1/h), etc. (demi-vie h = 3, 5, 10, 20 matchs ; `hinf` : poids égaux).
  C'est exactement la somme de la matrice cumulée des paires restreinte au onze (H.3, prouvé
  par un test), calculée sans construire la matrice ;
- `xi_new_starters` : nombre de titulaires de X_m qui ont moins de 3 titularisations de
  championnat dans le club sur les 365 jours précédents.

**Valeur vide** (jamais remplacée) : onze incomplet du match (moins de 11 titulaires
identifiés, entrée sans identifiant ou exclue pour collision, ADR-0008 et ADR-0020), match non
joué, ou aucun match antérieur dans l'historique. Un match au onze incomplet n'entre pas non
plus dans l'historique des suivants.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from foot_predictor.features.leagues import LADDERS

XI_SIZE = 11
PAIRS = XI_SIZE * (XI_SIZE - 1)  # 110 paires ordonnées
HALF_LIVES = (3, 5, 10, 20, float("inf"))
"""Demi-vies de la cohésion, en nombre de matchs (rapport H.7). `inf` : poids égaux, historique intégral du club."""
NEW_STARTER_WINDOW_DAYS = 365
NEW_STARTER_MIN_STARTS = 3


def half_life_suffix(half_life: float) -> str:
    """Suffixe de colonne d'une demi-vie : `3`, `5`, ... ou `inf`."""
    return "inf" if np.isinf(half_life) else str(int(half_life))


def cohesion_columns() -> list[str]:
    return [f"xi_cohesion_ewm_h{half_life_suffix(h)}" for h in HALF_LIVES]


def _days(values) -> np.ndarray:
    return ((pd.to_datetime(pd.Series(values)) - pd.Timestamp("2000-01-01")).dt.days).to_numpy(dtype=np.int64)


def complete_xis(lineups: pd.DataFrame, team_sheets: pd.DataFrame) -> pd.DataFrame:
    """Une ligne (match, équipe, joueur) par titulaire des onze complets, les autres onze étant écartés.

    Complet : exactement 11 titulaires distincts avec identifiant API, aucune entrée sans
    identifiant ni exclue pour collision sur la feuille d'équipe.
    """
    starters = lineups.loc[lineups["started"] & lineups["api_player_id"].notna(), ["match_id", "team_id"]].copy()
    starters["player"] = lineups.loc[starters.index, "api_player_id"].astype("int64")
    starters = starters.drop_duplicates()
    size = starters.groupby(["match_id", "team_id"]).size().rename("n").reset_index()
    sheets = team_sheets[["match_id", "team_id", "unknown_starters", "collision_excluded"]].copy()
    sheets["clean"] = (sheets["unknown_starters"].fillna(0) == 0) & (sheets["collision_excluded"].fillna(0) == 0)
    keep = size.merge(sheets[["match_id", "team_id", "clean"]], on=["match_id", "team_id"], how="left")
    keep = keep[(keep["n"] == XI_SIZE) & (keep["clean"].fillna(True))]
    return starters.merge(keep[["match_id", "team_id"]], on=["match_id", "team_id"])


def common_starters(xi: np.ndarray) -> np.ndarray:
    """Matrice s[i, j] = |X_i ∩ X_j| pour des onze donnés en indicatrices (matchs × joueurs)."""
    return xi @ xi.T


def pair_score(common: np.ndarray) -> np.ndarray:
    """s(s − 1) / 110 : part des 110 paires ordonnées du onze déjà réunies dans un autre onze (rapport H.3)."""
    return common * (common - 1.0) / PAIRS


def _team_values(valid: pd.DataFrame, xis: pd.DataFrame) -> dict[int, dict]:
    """Variables de chaque match au onze complet d'une équipe, indexées par `match_id`.

    `valid` : matchs de l'historique de l'équipe (`match_id`, `day`), triés par jour ;
    `xis` : leurs titulaires (`match_id`, `player`).
    """
    row_of = {m: i for i, m in enumerate(valid["match_id"])}
    xis = xis[xis["match_id"].isin(row_of)]  # les titulaires des matchs hors historique (coupes, autres onze) sortent
    codes, _ = pd.factorize(xis["player"])
    xi = np.zeros((len(valid), codes.max() + 1), dtype=np.float32)
    xi[xis["match_id"].map(row_of).to_numpy(), codes] = 1.0
    days = valid["day"].to_numpy()
    common = common_starters(xi)
    score = pair_score(common)
    cumulative = np.vstack([np.zeros((1, xi.shape[1]), dtype=np.float32), np.cumsum(xi, axis=0)])
    out = {}
    for i, match_id in enumerate(valid["match_id"]):
        before = int(np.searchsorted(days, days[i], side="left"))  # matchs des jours antérieurs
        values = {name: np.nan for name in ("xi_overlap_prev", "xi_new_starters", *cohesion_columns())}
        if before > 0:
            values["xi_overlap_prev"] = float(common[i, before - 1])
            ranks = np.arange(before, 0, -1)  # rang 1 = match précédent, pour les colonnes 0..before-1
            for half_life, name in zip(HALF_LIVES, cohesion_columns(), strict=True):
                weights = np.ones(before) if np.isinf(half_life) else 0.5 ** ((ranks - 1) / half_life)
                values[name] = float(weights @ score[i, :before] / weights.sum())
            low = int(np.searchsorted(days, days[i] - NEW_STARTER_WINDOW_DAYS, side="left"))
            starts = cumulative[before] - cumulative[low]
            values["xi_new_starters"] = float((starts[xi[i] > 0] < NEW_STARTER_MIN_STARTS).sum())
        out[match_id] = values
    return out


def compute_lineup_stability(matches: pd.DataFrame, lineups: pd.DataFrame, team_sheets: pd.DataFrame) -> pd.DataFrame:
    """Variables G6 d'avant-match, une ligne par (match, équipe) de championnat des échelles.

    `matches` : colonnes de `load_matches` ; `lineups` : de `load_lineups` ; `team_sheets` : de
    `load_team_sheets`. Les colonnes rendues sont `match_id`, `team_id`, `is_home`,
    `xi_overlap_prev`, `xi_cohesion_ewm_h*` (une par demi-vie) et `xi_new_starters`.
    """
    league = matches[matches["api_league_id"].isin(list(LADDERS))]
    sides = []
    for side in ("home", "away"):
        sides.append(
            pd.DataFrame(
                {
                    "match_id": league["match_id"].to_numpy(),
                    "team_id": league[f"{side}_team_id"].to_numpy(),
                    "is_home": side == "home",
                    "day": _days(league["match_day"]),
                    "played": (league["status"] == "played").to_numpy(),
                }
            )
        )
    targets = pd.concat(sides, ignore_index=True)

    xis = complete_xis(lineups, team_sheets)
    history = targets[targets["played"]].merge(
        xis[["match_id", "team_id"]].drop_duplicates(), on=["match_id", "team_id"]
    )
    columns = ["xi_overlap_prev", *cohesion_columns(), "xi_new_starters"]
    values = {c: np.full(len(targets), np.nan) for c in columns}
    position = pd.Series(np.arange(len(targets)), index=pd.MultiIndex.from_frame(targets[["match_id", "team_id"]]))
    xis_by_team = {team: group for team, group in xis.groupby("team_id")}
    for team, valid in history.groupby("team_id"):
        valid = valid.sort_values(["day", "match_id"], kind="mergesort")
        per_match = _team_values(valid, xis_by_team[team])
        for match_id, row_values in per_match.items():
            index = position[(match_id, team)]
            for column in columns:
                values[column][index] = row_values[column]

    out = targets[["match_id", "team_id", "is_home"]].copy()
    for column in columns:
        out[column] = values[column]
    return out.sort_values(["match_id", "is_home"], ascending=[True, False], kind="mergesort").reset_index(drop=True)
