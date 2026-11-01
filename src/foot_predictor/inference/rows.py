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

**Horizon H2** (6.10) : même principe, avec `features.dataset.build_frame_h2` et les compositions
(`lineups`) et feuilles de match (`team_sheets`) lues par la porte. Les deux tables sont tronquées aux
matchs de l'historique. Pour un match cible, on garde ce que l'on sait à T-60 (les titulaires, le poste
annoncé, l'entraîneur, la formation) et on **retire** ce que le match produit : minutes, note,
remplaçant, capitaine, poste des statistiques. C'est l'équivalent, pour les compositions, des tirs
retirés plus haut. Les groupes G4 à G6 ne lisent d'ailleurs que des jours strictement antérieurs.

**Jours scellés** (à partir du 1er juillet 2025) : `build_frame` refuse un historique qui contient
des matchs scellés, sauf avec son option `sealed_test=True`, qui l'accepte et produit les lignes
jusqu'à la dernière saison présente, sans rien changer au calcul. L'inférence ne s'en sert que
pour un contexte ouvert après le test scellé H1 (`history_opened`, ADR-0045) et pour un jour
scellé ; avant le scellé, l'appel reste celui de la période de développement.
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
from foot_predictor.features.dataset import build_frame, build_frame_h2, load_elo_params
from foot_predictor.seal import SEAL_DATE

POST_MATCH_COLUMNS = ("goals_for", "goals_against", "shots_source")
"""Colonnes qui décrivent le match lui-même, connues après lui : jamais dans une ligne d'inférence."""
FICTITIOUS_GOALS = (0, 0)
POST_MATCH_LINEUP_COLUMNS = ("minutes", "rating", "stats_position_bucket", "substitute", "captain")
"""Colonnes des compositions produites par le match lui-même : retirées pour un match cible (H2)."""
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


def lineups_for_day(
    lineups: pd.DataFrame, team_sheets: pd.DataFrame, history: pd.DataFrame, targets: Iterable[int]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compositions et feuilles de match tronquées à l'historique ; cibles réduites à ce que l'on sait à T-60."""
    known = history["match_id"].to_numpy()
    kept = lineups[lineups["match_id"].isin(known)].copy()
    target = kept["match_id"].isin(list(targets)).to_numpy()
    for column in POST_MATCH_LINEUP_COLUMNS:
        if column in kept.columns:
            kept.loc[target, column] = pd.NA
    return kept, team_sheets[team_sheets["match_id"].isin(known)]


def rows_for_day(
    matches: pd.DataFrame,
    day: dt.date,
    match_ids: Iterable[int] | None = None,
    *,
    elo_params=None,
    coefficients=None,
    periods=None,
    history_opened: bool = False,
    horizon: str = "H1",
    lineups: pd.DataFrame | None = None,
    team_sheets: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Lignes (match, équipe) des matchs du jour `day` (ou de `match_ids`), sans colonnes d'après-match.

    Seuls les matchs de saison régulière des 10 championnats donnent des lignes (règle de
    `build_frame`) ; un autre match (coupe, barrage) n'a pas de ligne : la disponibilité le dira.
    `history_opened` : table lue avec l'ouverture du scellé à l'inférence (ADR-0045) ; sans elle,
    un jour scellé est refusé par `build_frame` (`SealViolation`).
    `horizon="H2"` : `lineups` et `team_sheets` (porte) sont obligatoires ; colonnes du registre complet.
    """
    targets = day_targets(matches, day, match_ids)
    if len(targets) == 0:
        return pd.DataFrame()
    history = history_for_day(matches, day, targets)
    common = (
        elo_params or load_elo_params(),
        coefficients or xg_proxy.load(),
        periods if periods is not None else huis_clos.load_periods(),
    )
    sealed = history_opened and as_day(day) >= SEAL_DATE  # voir la docstring du module
    if horizon == "H2":
        if lineups is None or team_sheets is None:
            raise ValueError("Horizon H2 : compositions et feuilles de match requises (porte load_lineups).")
        day_lineups, day_sheets = lineups_for_day(lineups, team_sheets, history, targets)
        frame = build_frame_h2(history, day_lineups, day_sheets, *common, sealed_test=sealed)
    elif horizon == "H1":
        frame = build_frame(history, *common, sealed_test=sealed)
    else:
        raise ValueError(f"Horizon inconnu : {horizon}")
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
    history_opened: bool = False
    """Table lue avec l'ouverture du scellé à l'inférence (ADR-0045)."""
    lineups: pd.DataFrame | None = None
    team_sheets: pd.DataFrame | None = None
    """Compositions et feuilles de match de la porte (horizon H2, rejeu seulement) ; None : H2 impossible."""
    max_days: int = 64
    _cache: OrderedDict = field(default_factory=OrderedDict)
    timings: list = field(default_factory=list)

    def rows(self, day: dt.date, horizon: str = "H1") -> pd.DataFrame:
        key = (as_day(day), self.data_version, horizon)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        started = time.perf_counter()
        rows = rows_for_day(
            self.matches, key[0], history_opened=self.history_opened, horizon=horizon,
            lineups=self.lineups, team_sheets=self.team_sheets,
        )  # fmt: skip
        self.timings.append((key[0], time.perf_counter() - started))
        self._cache[key] = rows
        if len(self._cache) > self.max_days:
            self._cache.popitem(last=False)
        return rows
