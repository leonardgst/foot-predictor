"""Qualité du onze (groupe G5, horizon H2) : note rétrécie, habituels absents, âge moyen.

Fonction pure : `compute_xi_quality(matches, lineups, team_sheets)` lit les matchs (porte
`load_matches`), les compositions (`load_lineups`) et les feuilles d'équipe (`load_team_sheets`),
et renvoie une ligne par (match, équipe) de championnat des échelles (top 5 et D2). Aucun accès à
la base. Spécification : ADR-0013 (décision 3 et règles 3 et 4), ADR-0047 (D3, D9).

Pour l'équipe e au match m (jour J), avec son onze X_m connu à T-60 :

- `xi_quality` : moyenne, sur les 11 titulaires, de la **note rétrécie** de chaque joueur. Sa
  note brute est la moyenne, pondérée par les minutes, de ses notes de championnat (échelles)
  d'un jour **strictement antérieur** à J ; M est le total de ces minutes notées. La note
  rétrécie est `(M·r̄ + k·μ) / (M + k)` où μ est la moyenne, pondérée par les minutes, des notes
  antérieures à J au même poste, et k (en minutes) l'estimation bayésienne empirique de
  `features/params/xi_quality.json`. Un joueur sans note antérieure vaut μ (ADR-0013, règle 3) ;
  ces cas sont comptés par `starter_quality`. Une recrue venue hors des échelles est dans ce
  cas (D9 a : moyenne du poste, comptée, sans correction par championnat) ;
- `xi_regulars_missing` : part des « habituels » du club absents de X_m. Un habituel a débuté au
  moins 5 des 10 derniers matchs de l'historique du club (onze complet, jour strictement
  antérieur, sans remise à zéro par saison, comme G6). Ne distingue pas un joueur blessé d'un
  joueur parti : un départ compte comme une absence tant qu'il reste dans la fenêtre ;
- `xi_mean_age` : âge moyen des titulaires en années, au jour de m.

**Poste** : celui de la composition annoncée de m (connu à T-60), à défaut le dernier poste
connu du joueur dans le passé. Pour une apparition passée : poste de la composition, à défaut
celui des statistiques du match. Le poste d'un match qui sert à rétrécir ne vient jamais des
statistiques de ce match.

**Nettoyage** (ADR-0013, règle 4) : une note hors de 3 à 10, ou des minutes hors de 1 à 130,
rend l'apparition inutilisable pour la note (elle compte pour le poste et le onze, pas pour la
moyenne).

**Valeur vide** (jamais remplacée) : onze incomplet du match (comme G6), match non joué,
titulaire sans poste connu ni note antérieure (`xi_quality`), aucune note antérieure au poste
(2015-16, rodage D3), moins de 10 matchs d'historique ou aucun habitué (`xi_regulars_missing`),
titulaire sans date de naissance (`xi_mean_age`).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from foot_predictor.features.leagues import LADDERS
from foot_predictor.features.lineup_stability import XI_SIZE, complete_xis, day_numbers

PARAMS_PATH = Path(__file__).resolve().parent / "params" / "xi_quality.json"
RATING_RANGE = (3.0, 10.0)
MINUTES_RANGE = (1, 130)
REGULAR_WINDOW = 10
REGULAR_MIN_STARTS = 5
DAYS_PER_YEAR = 365.25
COLUMNS = ["xi_quality", "xi_regulars_missing", "xi_mean_age"]


def load_shrinkage(path: Path = PARAMS_PATH) -> float:
    """Constante k de rétrécissement, en minutes (estimée par `xi_quality_estimation`)."""
    return float(json.loads(path.read_text(encoding="utf-8"))["shrinkage_minutes"])


def _floats(series: pd.Series) -> np.ndarray:
    return pd.to_numeric(series).to_numpy(dtype="float64", na_value=np.nan)


def rated_appearances(matches: pd.DataFrame, lineups: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par apparition (joueur identifié, match de championnat terminé des échelles).

    Colonnes : `match_id`, `player`, `day`, `bucket` (poste de la composition, à défaut celui
    des statistiques), `weight` (minutes) et `weighted_rating` (minutes × note), à 0 quand la
    note ou les minutes sont absentes ou hors plage (apparition inutilisable pour la note).
    """
    league = matches[matches["api_league_id"].isin(list(LADDERS)) & (matches["status"] == "played")]
    days = pd.Series(day_numbers(league["match_day"]), index=league["match_id"].to_numpy())
    rows = lineups[lineups["api_player_id"].notna() & lineups["match_id"].isin(days.index)]
    rating, minutes = _floats(rows["rating"]), _floats(rows["minutes"])
    usable = (
        (rating >= RATING_RANGE[0])
        & (rating <= RATING_RANGE[1])
        & (minutes >= MINUTES_RANGE[0])
        & (minutes <= MINUTES_RANGE[1])
    )
    return pd.DataFrame(
        {
            "match_id": rows["match_id"].to_numpy(dtype="int64"),
            "player": rows["api_player_id"].to_numpy(dtype="int64"),
            "day": rows["match_id"].map(days).to_numpy(dtype="int64"),
            "bucket": rows["position_bucket"].fillna(rows["stats_position_bucket"]).to_numpy(dtype=object),
            "weight": np.where(usable, minutes, 0.0),
            "weighted_rating": np.where(usable, minutes * rating, 0.0),
        }
    )


def _history_before(targets: pd.DataFrame, table: pd.DataFrame, by: str) -> pd.DataFrame:
    """Dernière ligne de `table` (cumuls par `by`) d'un jour strictement antérieur à celui de chaque cible."""
    merged = pd.merge_asof(
        targets.sort_values("day", kind="mergesort"),
        table.sort_values("day", kind="mergesort"),
        on="day",
        by=by,
        allow_exact_matches=False,
    )
    return merged.sort_values("row", kind="mergesort").reset_index(drop=True)


def _cumulate(appearances: pd.DataFrame, key: str, with_bucket: bool) -> pd.DataFrame:
    """Cumuls (minutes, minutes × note) par `key` et par jour, et dernier poste connu si demandé."""
    spec = {"weight": ("weight", "sum"), "weighted_rating": ("weighted_rating", "sum")}
    if with_bucket:
        spec["bucket"] = ("bucket", "last")
    daily = appearances.groupby([key, "day"], as_index=False).agg(**spec).sort_values([key, "day"])
    grouped = daily.groupby(key)
    daily["cum_weight"] = grouped["weight"].cumsum()
    daily["cum_weighted_rating"] = grouped["weighted_rating"].cumsum()
    columns = [key, "day", "cum_weight", "cum_weighted_rating"]
    if with_bucket:
        daily["last_bucket"] = grouped["bucket"].ffill()
        columns.append("last_bucket")
    return daily[columns]


def starter_quality(
    matches: pd.DataFrame, lineups: pd.DataFrame, team_sheets: pd.DataFrame, *, shrinkage_minutes: float | None = None
) -> pd.DataFrame:
    """Une ligne par titulaire des onze complets de matchs terminés : minutes notées, poste, note rétrécie.

    Colonnes : `match_id`, `team_id`, `player`, `day`, `birth_date`, `bucket` (poste retenu),
    `rated_minutes` (M, 0 sans historique), `position_mean` (μ), `quality` (note rétrécie, vide si
    ni poste ni μ), `no_history` (vrai si M = 0). Sert aussi aux décomptes publiés (D9).
    """
    k = load_shrinkage() if shrinkage_minutes is None else float(shrinkage_minutes)
    appearances = rated_appearances(matches, lineups)
    xis = complete_xis(lineups, team_sheets)
    keys = xis[["match_id", "team_id"]].drop_duplicates()
    rows = lineups[lineups["started"] & lineups["api_player_id"].notna()]
    rows = rows.drop_duplicates(["match_id", "team_id", "api_player_id"]).merge(keys, on=["match_id", "team_id"])
    day_of = appearances.drop_duplicates("match_id").set_index("match_id")["day"]
    targets = pd.DataFrame(
        {
            "row": np.arange(len(rows)),
            "match_id": rows["match_id"].to_numpy(dtype="int64"),
            "team_id": rows["team_id"].to_numpy(dtype="int64"),
            "player": rows["api_player_id"].to_numpy(dtype="int64"),
            "day": rows["match_id"].map(day_of).to_numpy(dtype="float64"),
            "birth_date": rows["birth_date"].to_numpy(),
            "match_bucket": rows["position_bucket"].to_numpy(dtype=object),
        }
    )
    targets = targets[targets["day"].notna()].assign(day=lambda t: t["day"].astype("int64"))

    own = _history_before(targets[["row", "player", "day"]], _cumulate(appearances, "player", True), "player")
    targets = targets.merge(
        own[["row", "cum_weight", "cum_weighted_rating", "last_bucket"]], on="row", how="left"
    ).sort_values("row", kind="mergesort")
    targets["rated_minutes"] = targets["cum_weight"].fillna(0.0)
    targets["own_weighted_rating"] = targets["cum_weighted_rating"].fillna(0.0)
    targets["bucket"] = targets["match_bucket"].where(targets["match_bucket"].notna(), targets["last_bucket"])

    with_bucket = appearances[appearances["bucket"].notna()]
    position = _history_before(
        targets.loc[targets["bucket"].notna(), ["row", "bucket", "day"]],
        _cumulate(with_bucket, "bucket", False),
        "bucket",
    )
    mean = position.set_index("row")
    targets["position_mean"] = targets["row"].map(mean["cum_weighted_rating"] / mean["cum_weight"])
    targets["quality"] = (targets["own_weighted_rating"] + k * targets["position_mean"]) / (
        targets["rated_minutes"] + k
    )
    targets["no_history"] = targets["rated_minutes"] == 0
    return targets[
        [
            "match_id",
            "team_id",
            "player",
            "day",
            "birth_date",
            "bucket",
            "rated_minutes",
            "position_mean",
            "quality",
            "no_history",
        ]
    ].reset_index(drop=True)


def _regulars_missing(valid: pd.DataFrame, xis: pd.DataFrame) -> dict[int, float]:
    """Part des habituels absents de chaque match au onze complet d'une équipe, indexée par `match_id`.

    `valid` : matchs de l'historique de l'équipe (`match_id`, `day`), triés par jour ;
    `xis` : leurs titulaires (`match_id`, `player`).
    """
    row_of = {m: i for i, m in enumerate(valid["match_id"])}
    xis = xis[xis["match_id"].isin(row_of)]
    codes, _ = pd.factorize(xis["player"])
    xi = np.zeros((len(valid), codes.max() + 1), dtype=np.float32)
    xi[xis["match_id"].map(row_of).to_numpy(), codes] = 1.0
    days = valid["day"].to_numpy()
    cumulative = np.vstack([np.zeros((1, xi.shape[1]), dtype=np.float32), np.cumsum(xi, axis=0)])
    out = {}
    for i, match_id in enumerate(valid["match_id"]):
        before = int(np.searchsorted(days, days[i], side="left"))  # matchs des jours antérieurs
        value = np.nan
        if before >= REGULAR_WINDOW:
            starts = cumulative[before] - cumulative[before - REGULAR_WINDOW]
            regulars = starts >= REGULAR_MIN_STARTS
            if regulars.any():
                value = float((regulars & (xi[i] == 0)).sum() / regulars.sum())
        out[match_id] = value
    return out


def compute_xi_quality(
    matches: pd.DataFrame, lineups: pd.DataFrame, team_sheets: pd.DataFrame, *, shrinkage_minutes: float | None = None
) -> pd.DataFrame:
    """Variables G5 d'avant-match, une ligne par (match, équipe) de championnat des échelles.

    `matches` : colonnes de `load_matches` ; `lineups` : de `load_lineups` ; `team_sheets` : de
    `load_team_sheets`. Les colonnes rendues sont `match_id`, `team_id`, `is_home`, `xi_quality`,
    `xi_regulars_missing` et `xi_mean_age`. `shrinkage_minutes` : k, par défaut celui du fichier
    de paramètres.
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
    out = targets[["match_id", "team_id", "is_home"]].copy()
    index = pd.MultiIndex.from_frame(out[["match_id", "team_id"]])

    starters = starter_quality(matches, lineups, team_sheets, shrinkage_minutes=shrinkage_minutes)
    by_team = starters.groupby(["match_id", "team_id"])
    complete = by_team["quality"].count() == XI_SIZE
    quality = by_team["quality"].sum().where(complete) / XI_SIZE
    years = (starters["day"] - day_numbers(starters["birth_date"].fillna(pd.Timestamp("2000-01-01")))).to_numpy()
    starters["age"] = np.where(starters["birth_date"].notna(), years / DAYS_PER_YEAR, np.nan)
    by_team = starters.groupby(["match_id", "team_id"])
    known = by_team["age"].count() == XI_SIZE
    age = by_team["age"].sum().where(known) / XI_SIZE
    out["xi_quality"] = quality.reindex(index).to_numpy()
    out["xi_mean_age"] = age.reindex(index).to_numpy()

    xis = complete_xis(lineups, team_sheets)
    history = targets[targets["played"]].merge(
        xis[["match_id", "team_id"]].drop_duplicates(), on=["match_id", "team_id"]
    )
    position = pd.Series(np.arange(len(targets)), index=index)
    regulars = np.full(len(targets), np.nan)
    xis_by_team = {team: group for team, group in xis.groupby("team_id")}
    for team, valid in history.groupby("team_id"):
        valid = valid.sort_values(["day", "match_id"], kind="mergesort")
        for match_id, value in _regulars_missing(valid, xis_by_team[team]).items():
            regulars[position[(match_id, team)]] = value
    out["xi_regulars_missing"] = regulars

    out = out[["match_id", "team_id", "is_home", *COLUMNS]]
    return out.sort_values(["match_id", "is_home"], ascending=[True, False], kind="mergesort").reset_index(drop=True)
