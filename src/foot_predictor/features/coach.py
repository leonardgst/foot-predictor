"""Entraîneur (groupe G4, horizon H2) : ancienneté plafonnée et indicateur « nouvel entraîneur ».

Fonction pure : `compute_coach(matches, team_sheets)` lit les matchs (porte `load_matches`) et les
feuilles d'équipe (`load_team_sheets`), et renvoie une ligne par (match, équipe) de championnat
des échelles (top 5 et D2). Aucun accès à la base. Spécification : rapport de cadrage I.3 (G4),
ADR-0047 (décision 2 et D3).

Pour l'équipe e au match m (jour J), dont l'entraîneur c est celui de la feuille de match (connu
à T-60), et son **historique** : les matchs de championnat **terminés**, d'un jour **strictement
antérieur** à J, dont l'entraîneur est connu. Le match m n'y figure jamais. Le calcul est limité
au club et traverse les saisons. Un match à entraîneur inconnu sort de l'historique : il ne fait
pas passer son successeur pour un nouvel entraîneur.

La **période en cours** est la suite ininterrompue des derniers matchs de l'historique du club
dont l'entraîneur est c. Si le dernier match de l'historique a un autre entraîneur (ou s'il n'y a
pas d'historique), la période est vide : c arrive au club. Un retour (A, B, puis A) repart de zéro.

- `coach_tenure_days` : nombre de jours entre le premier match de la période et J, plafonné à
  365 ; 0 pour un entraîneur qui arrive ;
- `coach_is_new` : 1 si la période compte moins de 5 matchs, sinon 0.

**Censure à gauche** : l'API ne donne l'entraîneur qu'à partir de 2016-17. Un entraîneur déjà en
poste en août 2016 paraît arrivé à cette date, et ses 5 premiers matchs observés passent pour
des débuts. Le plafond de 365 jours absorbe l'effet pour l'ancienneté à partir d'août 2017 :
l'apprentissage commence en 2017-18 (ADR-0047, D3). Les valeurs de 2016-17 sont calculées, mais
biaisées.

**Valeur vide** (jamais remplacée) : entraîneur de m inconnu (toute la période avant 2016-17,
et un peu après), match non joué.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from foot_predictor.features.leagues import LADDERS
from foot_predictor.features.lineup_stability import day_numbers

TENURE_CAP_DAYS = 365
NEW_COACH_MATCHES = 5
COLUMNS = ["coach_tenure_days", "coach_is_new"]


def _team_values(valid: pd.DataFrame) -> dict[int, tuple[float, float]]:
    """Variables de chaque match d'une équipe, indexées par `match_id`.

    `valid` : matchs terminés à entraîneur connu (`match_id`, `day`, `coach`), triés par jour.
    """
    days = valid["day"].to_numpy()
    coaches = valid["coach"].to_numpy()
    run_start = np.zeros(len(valid), dtype=np.int64)  # début de la suite de même entraîneur qui finit en j
    for j in range(1, len(valid)):
        run_start[j] = run_start[j - 1] if coaches[j] == coaches[j - 1] else j
    out = {}
    for i, match_id in enumerate(valid["match_id"]):
        before = int(np.searchsorted(days, days[i], side="left"))  # matchs des jours antérieurs
        if before > 0 and coaches[before - 1] == coaches[i]:
            start = run_start[before - 1]
            matches_in_post = before - start
            tenure = min(int(days[i] - days[start]), TENURE_CAP_DAYS)
        else:
            matches_in_post, tenure = 0, 0
        out[match_id] = (float(tenure), float(matches_in_post < NEW_COACH_MATCHES))
    return out


def compute_coach(matches: pd.DataFrame, team_sheets: pd.DataFrame) -> pd.DataFrame:
    """Variables G4 d'avant-match, une ligne par (match, équipe) de championnat des échelles.

    `matches` : colonnes de `load_matches` ; `team_sheets` : de `load_team_sheets`. Les colonnes
    rendues sont `match_id`, `team_id`, `is_home`, `coach_tenure_days` et `coach_is_new`.
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
                    "day": day_numbers(league["match_day"]),
                    "played": (league["status"] == "played").to_numpy(),
                }
            )
        )
    targets = pd.concat(sides, ignore_index=True)
    sheets = team_sheets[["match_id", "team_id", "api_coach_id"]].drop_duplicates(["match_id", "team_id"])
    targets = targets.merge(sheets, on=["match_id", "team_id"], how="left")
    known = targets[targets["played"] & targets["api_coach_id"].notna()].copy()
    known["coach"] = known["api_coach_id"].astype("int64")

    position = pd.Series(np.arange(len(targets)), index=pd.MultiIndex.from_frame(targets[["match_id", "team_id"]]))
    values = {c: np.full(len(targets), np.nan) for c in COLUMNS}
    for team, valid in known.groupby("team_id"):
        valid = valid.sort_values(["day", "match_id"], kind="mergesort")
        for match_id, (tenure, is_new) in _team_values(valid).items():
            index = position[(match_id, team)]
            values["coach_tenure_days"][index] = tenure
            values["coach_is_new"][index] = is_new

    out = targets[["match_id", "team_id", "is_home"]].copy()
    for column in COLUMNS:
        out[column] = values[column]
    return out.sort_values(["match_id", "is_home"], ascending=[True, False], kind="mergesort").reset_index(drop=True)
