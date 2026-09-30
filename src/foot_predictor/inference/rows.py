"""Variables d'un match quelconque, par la fonction de l'entraînement (décision 2 de la partie 5, ADR-0040).

Pour prédire les matchs d'un jour J, on appelle `features.dataset.build_frame`, la fonction qui a
construit le jeu d'entraînement, sur la table des matchs **tronquée au jour J** :

1. on garde les matchs de jour ≤ J ;
2. les **matchs cibles** (ceux du jour J à prédire, à jouer ou de rejeu) reçoivent le statut « joué »,
   des buts **fictifs** (0-0) et **aucune statistique** (tirs, tirs cadrés, xG retirés) : c'est la
   situation d'un match qui n'a pas encore eu lieu ;
3. `build_frame` calcule toutes les lignes ; on ne garde que celles des cibles et on **retire** les
   colonnes d'après-match (`goals_for`, `goals_against`, `shots_source`).

Pourquoi c'est exact : l'Elo s'applique en fin de jour (les matchs du jour J ne modifient pas les
notes d'avant-match du jour J), les glissants et le calendrier ne lisent que les jours
**strictement antérieurs**. Les buts fictifs ne touchent donc aucune variable du jour J. En
revanche, calculer deux jours ensemble ferait entrer le résultat fictif du premier dans les
variables du second : on calcule **un jour à la fois**.

Aucun remplissage : une variable incalculable (glissant sans historique) reste vide, comme dans le
jeu d'entraînement.
"""

from __future__ import annotations

import datetime as dt
import time
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from foot_predictor.features import huis_clos, xg_proxy
from foot_predictor.features.dataset import build_frame, load_elo_params

POST_MATCH_COLUMNS = ("goals_for", "goals_against", "shots_source")
"""Colonnes qui décrivent le match lui-même, connues après lui : jamais dans une ligne d'inférence."""
FICTITIOUS_GOALS = (0, 0)
MATCH_STAT_COLUMNS = (
    "home_shots_api", "home_sot_api", "home_xg_api", "away_shots_api", "away_sot_api", "away_xg_api",
    "home_shots_fd", "home_sot_fd", "away_shots_fd", "away_sot_fd",
)  # fmt: skip


def as_day(value) -> dt.date:
    return value if isinstance(value, dt.date) and not isinstance(value, dt.datetime) else pd.Timestamp(value).date()


def day_targets(matches: pd.DataFrame, day: dt.date, match_ids: Iterable[int] | None = None) -> np.ndarray:
    """Identifiants des matchs du jour `day` (tous, ou ceux de `match_ids`)."""
    on_day = matches[matches["match_day"] == as_day(day)]
    if match_ids is not None:
        on_day = on_day[on_day["match_id"].isin(list(match_ids))]
    return on_day["match_id"].to_numpy()


def history_for_day(matches: pd.DataFrame, day: dt.date, targets: Iterable[int]) -> pd.DataFrame:
    """Table des matchs tronquée au jour J, les cibles devenues « jouées, 0-0, sans statistiques »."""
    day = as_day(day)
    history = matches[matches["match_day"] <= day].copy()
    target = history["match_id"].isin(list(targets)).to_numpy()
    if (history.loc[target, "match_day"] != day).any():
        raise ValueError("Toutes les cibles doivent être du jour J : un seul jour à la fois.")
    history.loc[target, "status"] = "played"
    history.loc[target, "home_goals_90"] = FICTITIOUS_GOALS[0]
    history.loc[target, "away_goals_90"] = FICTITIOUS_GOALS[1]
    for column in MATCH_STAT_COLUMNS:
        if column in history.columns:
            # Type nullable (features/ lit ces colonnes en Float64 de toute façon, xg_proxy._column).
            history[column] = pd.to_numeric(history[column], errors="coerce").astype("Float64")
            history.loc[target, column] = pd.NA
    return history


def rows_for_day(
    matches: pd.DataFrame,
    day: dt.date,
    match_ids: Iterable[int] | None = None,
    *,
    elo_params=None,
    coefficients=None,
    periods=None,
) -> pd.DataFrame:
    """Lignes (match, équipe) des matchs du jour `day` (ou de `match_ids`), sans colonnes d'après-match.

    Seuls les matchs de saison régulière des 10 championnats donnent des lignes (règle de
    `build_frame`) ; un autre match (coupe, barrage) n'a pas de ligne : la disponibilité le dira.
    """
    targets = day_targets(matches, day, match_ids)
    if len(targets) == 0:
        return pd.DataFrame()
    history = history_for_day(matches, day, targets)
    frame = build_frame(
        history,
        elo_params or load_elo_params(),
        coefficients or xg_proxy.load(),
        periods if periods is not None else huis_clos.load_periods(),
    )
    rows = frame[frame["match_id"].isin(targets)]
    return rows.drop(columns=[c for c in POST_MATCH_COLUMNS if c in rows.columns]).reset_index(drop=True)


@dataclass
class RowsCache:
    """Cache des lignes par (jour, version des données) : un calcul complet de quelques secondes par jour.

    `data_version` identifie l'état de la table des matchs (chargement de `staging`, fichiers de
    football-data) : une autre version donne une autre clé, jamais une ligne périmée.
    """

    matches: pd.DataFrame
    data_version: str
    max_days: int = 64
    _cache: OrderedDict = field(default_factory=OrderedDict)
    timings: list = field(default_factory=list)

    def rows(self, day: dt.date) -> pd.DataFrame:
        key = (as_day(day), self.data_version)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        started = time.perf_counter()
        rows = rows_for_day(self.matches, key[0])
        self.timings.append((key[0], time.perf_counter() - started))
        self._cache[key] = rows
        if len(self._cache) > self.max_days:
            self._cache.popitem(last=False)
        return rows
