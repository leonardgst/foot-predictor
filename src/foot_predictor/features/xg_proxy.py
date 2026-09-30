"""xG estimé à partir des tirs (`xg_proxy`, groupe G2 ; ADR-0032).

Sans xG avant 2022-23 (ADR-0023), le MVP estime l'xG d'une équipe dans un match par une
combinaison linéaire **fixe** de ses tirs cadrés et non cadrés :

    xg_proxy = a · tirs_cadrés + b · (tirs − tirs_cadrés)

Les coefficients a et b sont estimés **une seule fois**, par moindres carrés **sans
constante et à coefficients positifs ou nuls** des buts de l'équipe sur ses tirs cadrés et
non cadrés, sur les saisons 2015-16 à 2020-21 (avant tous les plis de validation, 2021-22 à
2024-25), puis figés dans `features/params/xg_proxy.json`. Sans constante et positifs, comme
un vrai xG (somme de probabilités de but par tir) : zéro tir donne zéro, un tir ne retire
jamais de but attendu. Sans la contrainte, b sort légèrement négatif (tirs non cadrés
associés à moins de buts à tirs cadrés égaux) : c'est affiché dans le rapport, non retenu.

Source des tirs (ADR-0035, qui complète l'ADR-0029) : pour un match joué à partir de
2015-16 où API-FOOTBALL a les tirs **et** les tirs cadrés **des deux équipes**, les tirs
viennent de l'API ; sinon, de football-data. Le choix se fait **par match** (jamais une équipe
d'une source et l'autre de l'autre) et `shots_source` le dit. Cela corrige la rupture de série
de football-data en Serie A (2018-19 à 2020-21) et l'écart de la Bundesliga.

Pour une équipe, un même match donne son `xg_proxy` **pour** (ses tirs) et **contre** (les
tirs de l'adversaire). Tir manquant : `xg_proxy` vide, jamais 0.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from foot_predictor.features.leagues import LADDERS

ESTIMATION_SEASONS = range(2015, 2021)
"""Années de début des saisons d'estimation : 2015-16 à 2020-21, jamais au-delà."""

PARAMS_PATH = Path(__file__).resolve().parent / "params" / "xg_proxy.json"

API_SHOTS_FROM = 2015
"""Première saison (année de début) où les tirs d'API-FOOTBALL sont retenus : 2015-16 (ADR-0035)."""

SOURCE_API = "api"
SOURCE_FOOTBALL_DATA = "football_data"
_API_COLUMNS = ("home_shots_api", "home_sot_api", "away_shots_api", "away_sot_api")
_FD_COLUMNS = ("home_shots_fd", "home_sot_fd", "away_shots_fd", "away_sot_fd")


@dataclass(frozen=True)
class XgProxyCoefficients:
    on_target: float
    """a : buts attendus par tir cadré."""
    off_target: float
    """b : buts attendus par tir non cadré (tirs contrés compris)."""
    n_team_matches: int
    seasons: str
    source: str = "api_puis_football_data"
    """Source des tirs de l'estimation : `select_shots` (API depuis 2015-16, sinon football-data)."""

    def to_dict(self) -> dict:
        return asdict(self)


def _column(matches: pd.DataFrame, name: str) -> pd.Series:
    """Colonne numérique nullable ; absente de la table (jeu de test réduit) : entièrement vide."""
    if name in matches.columns:
        return pd.to_numeric(matches[name], errors="coerce").astype("Float64")
    return pd.Series(pd.NA, index=matches.index, dtype="Float64")


def select_shots(matches: pd.DataFrame) -> pd.DataFrame:
    """Tirs retenus pour chaque match, et leur source (ADR-0035). Même index que `matches`.

    Règle, **par match** : API-FOOTBALL si la saison commence en 2015 ou après et si l'API a
    les quatre valeurs (tirs et tirs cadrés des deux équipes) ; sinon football-data, valeurs
    vides comprises. `shots_source` vaut `api`, `football_data`, ou reste vide si aucune des
    deux sources n'a de valeur. Aucune valeur n'est inventée : une valeur absente reste vide.

    Colonnes : `home_shots`, `home_sot`, `away_shots`, `away_sot`, `shots_source`.
    """
    api = {c: _column(matches, c) for c in _API_COLUMNS}
    fd = {c: _column(matches, c) for c in _FD_COLUMNS}
    api_complete = pd.concat(api.values(), axis=1).notna().all(axis=1).to_numpy()
    if "season_year" in matches.columns:
        recent = (pd.to_numeric(matches["season_year"], errors="coerce").fillna(0) >= API_SHOTS_FROM).to_numpy()
    else:
        recent = np.zeros(len(matches), dtype=bool)
    use_api = api_complete & recent
    out = pd.DataFrame(index=matches.index)
    for side in ("home", "away"):
        for kind in ("shots", "sot"):
            out[f"{side}_{kind}"] = api[f"{side}_{kind}_api"].where(use_api, fd[f"{side}_{kind}_fd"])
    fd_any = pd.concat(fd.values(), axis=1).notna().any(axis=1).to_numpy()
    source = np.select([use_api, fd_any], [SOURCE_API, SOURCE_FOOTBALL_DATA], default="")
    out["shots_source"] = pd.Series(source, index=matches.index, dtype="string").replace("", pd.NA)
    return out


def team_shots(matches: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par (match, équipe) : buts au temps réglementaire, tirs et tirs cadrés retenus (`select_shots`)."""
    base = ["match_id", "season_year", "api_league_id", "status", "excluded"]
    shots = select_shots(matches)
    sides = []
    for side in ("home", "away"):
        part = matches[base].copy()
        part["team_id"] = matches[f"{side}_team_id"]
        part["goals"] = matches[f"{side}_goals_90"]
        part["shots"] = shots[f"{side}_shots"]
        part["shots_on_target"] = shots[f"{side}_sot"]
        part["shots_source"] = shots["shots_source"]
        sides.append(part)
    return pd.concat(sides, ignore_index=True)


def estimate(
    matches: pd.DataFrame, seasons: range = ESTIMATION_SEASONS, nonnegative: bool = True
) -> XgProxyCoefficients:
    """Moindres carrés sans constante : buts ~ a · cadrés + b · non cadrés, sur `seasons` seulement.

    `nonnegative=True` (retenu) contraint a, b ≥ 0 ; `False` donne l'estimation libre (rapport).

    Population : matchs terminés, non exclus, des championnats des échelles (top 5 et D2),
    dont les tirs et les buts sont connus.
    """
    if max(seasons) > 2020:
        raise ValueError("L'xg_proxy s'estime avant les plis de validation : saisons 2015-16 à 2020-21 au plus.")
    rows = team_shots(matches)
    rows = rows[
        rows["season_year"].isin(list(seasons))
        & rows["api_league_id"].isin(list(LADDERS))
        & (rows["status"] == "played")
        & ~rows["excluded"].astype(bool)
    ].dropna(subset=["goals", "shots", "shots_on_target"])
    on = rows["shots_on_target"].astype(float).to_numpy()
    off = (rows["shots"] - rows["shots_on_target"]).astype(float).to_numpy()
    keep = off >= 0  # un fichier où cadrés > tirs est incohérent : ligne écartée
    design = np.column_stack([on[keep], off[keep]])
    goals = rows["goals"].astype(float).to_numpy()[keep]
    if nonnegative:
        coef, _ = nnls(design, goals)
    else:
        coef, *_ = np.linalg.lstsq(design, goals, rcond=None)
    return XgProxyCoefficients(
        on_target=round(float(coef[0]), 6),
        off_target=round(float(coef[1]), 6),
        n_team_matches=int(keep.sum()),
        seasons=f"{min(seasons)}-{max(seasons) + 1}",
    )


def apply(coefficients: XgProxyCoefficients, shots, shots_on_target) -> pd.Series:
    """xg_proxy = a · cadrés + b · (tirs − cadrés) ; vide si un tir manque ou si cadrés > tirs."""
    shots = pd.to_numeric(pd.Series(shots), errors="coerce").astype("Float64")
    on = pd.to_numeric(pd.Series(shots_on_target), errors="coerce").astype("Float64")
    off = shots - on
    value = coefficients.on_target * on + coefficients.off_target * off
    return value.mask(off < 0)


def save(coefficients: XgProxyCoefficients, path: Path = PARAMS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(coefficients.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load(path: Path = PARAMS_PATH) -> XgProxyCoefficients:
    return XgProxyCoefficients(**json.loads(path.read_text(encoding="utf-8")))
