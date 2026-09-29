"""Calendrier (groupe G3) : repos, charge récente, match européen récent (ADR-0033).

Fonction pure : `compute_rest(matches)` lit une table de matchs de **toutes compétitions**
(championnats et coupes, porte `features/sources.py`) et renvoie une ligne par (match,
équipe) pour les matchs de championnat des échelles (top 5 et D2). Aucun accès à la base.

Pour l'équipe e au match du jour J, sur ses matchs **terminés** avant le jour J, toutes
compétitions présentes dans `staging` :

- `rest_days` : J − jour de son dernier match (vide si elle n'en a aucun) ;
- `matches_last_14d` : nombre de matchs joués du jour J − 14 au jour J − 1 ;
- `european_match_last_4d` : au moins un match de coupe d'Europe du jour J − 4 au jour J − 1 ;
- `rest_reliable` : vrai si toutes les coupes jouées par les équipes du pays sont dans
  `staging` cette saison (Angleterre, Allemagne, France depuis 2015-16 ; Italie depuis
  2016-17 ; Espagne depuis 2018-19). Avant, seuls les matchs de championnat sont connus :
  les valeurs sont calculées quand même, et l'indicateur dit qu'elles sous-estiment la
  charge.

**Rétrospectif seulement** : la date du prochain match n'est jamais utilisée (reports,
incertitude du calendrier). Disponible en live : non (les coupes ne sont couvertes par
aucune source gratuite après l'abonnement ; rejeu seulement, ADR-0011).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from foot_predictor.features.leagues import EUROPEAN_CUPS, LADDERS, REST_RELIABLE_FROM

LOAD_WINDOW_DAYS = 14
EUROPEAN_WINDOW_DAYS = 4


def _days(values) -> np.ndarray:
    return ((pd.to_datetime(pd.Series(values)) - pd.Timestamp("2000-01-01")).dt.days).to_numpy(dtype=np.int64)


def compute_rest(matches: pd.DataFrame) -> pd.DataFrame:
    """Variables de calendrier d'avant-match, une ligne par (match, équipe) de championnat des échelles."""
    played = matches[matches["status"] == "played"]
    history = pd.concat(
        [
            pd.DataFrame(
                {
                    "team_id": played[f"{side}_team_id"].to_numpy(),
                    "day": _days(played["match_day"]),
                    "european": played["api_league_id"].isin(list(EUROPEAN_CUPS)).to_numpy(),
                }
            )
            for side in ("home", "away")
        ],
        ignore_index=True,
    )
    league = matches[matches["api_league_id"].isin(list(LADDERS))]
    targets = pd.concat(
        [
            pd.DataFrame(
                {
                    "match_id": league["match_id"].to_numpy(),
                    "team_id": league[f"{side}_team_id"].to_numpy(),
                    "is_home": side == "home",
                    "day": _days(league["match_day"]),
                    "season_year": league["season_year"].to_numpy(),
                    "country": [LADDERS[int(x)][0] for x in league["api_league_id"]],
                }
            )
            for side in ("home", "away")
        ],
        ignore_index=True,
    )

    rest = np.full(len(targets), np.nan)
    load = np.zeros(len(targets), dtype=np.int64)
    european = np.zeros(len(targets), dtype=bool)
    by_team = {team: group for team, group in history.groupby("team_id")}
    for team, index in targets.groupby("team_id").groups.items():
        idx = targets.index.get_indexer(index)
        day = targets["day"].to_numpy()[idx]
        group = by_team.get(team)
        if group is None:
            continue
        hist_days = np.sort(group["day"].to_numpy())
        euro_days = np.sort(group.loc[group["european"], "day"].to_numpy())
        before = np.searchsorted(hist_days, day, side="left")  # matchs des jours < J
        has_previous = before > 0
        last = hist_days[np.maximum(before - 1, 0)]
        rest[idx] = np.where(has_previous, day - last, np.nan)
        load[idx] = before - np.searchsorted(hist_days, day - LOAD_WINDOW_DAYS, side="left")
        euro_before = np.searchsorted(euro_days, day, side="left")
        european[idx] = (euro_before - np.searchsorted(euro_days, day - EUROPEAN_WINDOW_DAYS, side="left")) > 0

    out = targets[["match_id", "team_id", "is_home"]].copy()
    out["rest_days"] = rest
    out["matches_last_14d"] = load
    out["european_match_last_4d"] = european
    first = targets["country"].map(REST_RELIABLE_FROM)
    out["rest_reliable"] = (targets["season_year"].astype("Int64") >= first).fillna(False).astype(bool).to_numpy()
    return out.sort_values(["match_id", "is_home"], ascending=[True, False], kind="mergesort").reset_index(drop=True)
