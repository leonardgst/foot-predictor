"""Protocole d'évaluation : plis, validation interne, lignes utilisables, intersection (ADR-0012, ADR-0037).

**Plis** (ADR-0012) : 4 plis à fenêtre croissante. Pour le pli de la saison de test s, on
apprend sur les lignes (match, équipe) des saisons 2015-16 à s − 1 et on évalue sur les matchs
de championnat du top 5 de la saison s (s = 2021-22, 2022-23, 2023-24, 2024-25). Les saisons
de rodage (avant 2015-16) ne servent que d'historique aux variables, déjà calculées dans le jeu.

**Validation interne** (hyperparamètres) : dans le pli s, chaque candidat apprend sur 2015-16
à s − 2 et se mesure sur la saison s − 1 (log-loss du total, top 5) ; le meilleur est ensuite
réajusté sur toutes les saisons d'apprentissage du pli. La saison de test n'est **jamais** lue
pour choisir.

**Population d'apprentissage** : `top5` (championnats du top 5) ou `top5_d2` (avec les D2),
choix expérimental jugé sur la même population d'évaluation (top 5).

**Aucun remplissage silencieux** : une ligne d'apprentissage à valeur manquante dans une variable
du modèle est exclue et comptée ; un match de test dont une variable manque n'a pas de
prédiction, et la comparaison se fait sur l'**intersection** des matchs prédits par tous les
modèles (nombre de matchs écartés publié).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from foot_predictor.features.leagues import TOP5
from foot_predictor.modeling import metrics
from foot_predictor.modeling.models.base import TARGET_COLUMNS, MatchPredictions, Model
from foot_predictor.seal import SEAL_DATE, check_seal

FIRST_TRAINING_SEASON = 2015
TEST_SEASONS = (2021, 2022, 2023, 2024)
POPULATIONS = ("top5", "top5_d2")


class ProtocolError(RuntimeError):
    """Un pli ou une étape viole le protocole (fuite, scellé, saison interdite)."""


@dataclass(frozen=True)
class Fold:
    test_season: int
    first_season: int = FIRST_TRAINING_SEASON

    @property
    def train_seasons(self) -> range:
        return range(self.first_season, self.test_season)

    @property
    def inner_train_seasons(self) -> range:
        return range(self.first_season, self.test_season - 1)

    @property
    def inner_valid_season(self) -> int:
        return self.test_season - 1

    @property
    def name(self) -> str:
        return f"{self.test_season}-{(self.test_season + 1) % 100:02d}"


def folds(test_seasons: Iterable[int] = TEST_SEASONS) -> list[Fold]:
    result = [Fold(int(s)) for s in test_seasons]
    for fold in result:
        if fold.test_season >= SEAL_DATE.year:
            raise ProtocolError(f"Saison de test {fold.name} : sous scellés (ADR-0012), refusée sans test scellé.")
    return result


def population_mask(rows: pd.DataFrame, population: str) -> pd.Series:
    if population == "top5":
        return rows["api_league_id"].isin(list(TOP5))
    if population == "top5_d2":
        return pd.Series(True, index=rows.index)
    raise ValueError(f"Population d'apprentissage inconnue : {population} (attendu : {POPULATIONS})")


def usable(rows: pd.DataFrame, features: Iterable[str]) -> tuple[pd.DataFrame, int]:
    """Lignes dont toutes les `features` sont connues, et nombre de lignes exclues (jamais remplies)."""
    features = list(features)
    if not features:
        return rows, 0
    keep = rows[features].notna().all(axis=1)
    return rows[keep], int((~keep).sum())


def complete_matches(rows: pd.DataFrame) -> pd.DataFrame:
    """Lignes des matchs dont les deux lignes (domicile et extérieur) sont présentes."""
    counts = rows.groupby("match_id")["is_home"].transform("size")
    return rows[counts == 2]


def training_rows(data: pd.DataFrame, seasons: Iterable[int], population: str) -> pd.DataFrame:
    seasons = list(seasons)
    part = data[data["season_year"].isin(seasons) & population_mask(data, population)]
    return part


def test_rows(data: pd.DataFrame, season: int) -> pd.DataFrame:
    """Lignes du top 5 de la saison de test, **sans les cibles** : un modèle ne peut pas lire le résultat."""
    part = data[(data["season_year"] == season) & data["eval_population"].astype(bool)]
    return part.drop(columns=[c for c in TARGET_COLUMNS if c in part.columns])


def outcomes(data: pd.DataFrame, season: int) -> pd.DataFrame:
    """Résultats des matchs d'évaluation d'une saison : une ligne par match (buts domicile, extérieur, total)."""
    part = data[(data["season_year"] == season) & data["eval_population"].astype(bool)]
    home = part[part["is_home"]].set_index("match_id")
    frame = pd.DataFrame(
        {
            "home_goals": home["goals_for"].astype(int),
            "away_goals": home["goals_against"].astype(int),
        }
    )
    frame["total"] = frame["home_goals"] + frame["away_goals"]
    keep = ["api_league_id", "season_year", "round", "match_day", "match_date"]
    return frame.join(home[[c for c in keep if c in home.columns]])


@dataclass
class FitResult:
    model: Model
    params: dict
    excluded_train_rows: int
    inner_scores: list[dict] = field(default_factory=list)


def select_and_fit(
    make: Callable[..., Model],
    grid: list[dict],
    data: pd.DataFrame,
    fold: Fold,
    population: str,
    features: Iterable[str] = (),
) -> FitResult:
    """Validation interne sur la dernière saison d'apprentissage, puis réajustement sur tout l'apprentissage.

    Garde-fou : aucune ligne de la saison de test n'entre dans le choix ni dans l'ajustement.
    """
    features = list(features)
    grid = grid or [{}]
    inner_scores = []
    if len(grid) > 1:
        inner_train, _ = usable(training_rows(data, fold.inner_train_seasons, population), features)
        valid = data[(data["season_year"] == fold.inner_valid_season) & data["eval_population"].astype(bool)]
        valid_x, _ = usable(valid, features)
        valid_x = complete_matches(valid_x)
        truth = outcomes(data, fold.inner_valid_season)
        _guard(inner_train, fold)
        _guard(valid_x, fold)
        for params in grid:
            model = make(**params).fit(inner_train)
            predicted = model.predict(valid_x.drop(columns=list(TARGET_COLUMNS)))
            totals = truth.loc[predicted.match_id, "total"].to_numpy()
            score = float(metrics.log_loss_by_match(predicted.total, totals).mean())
            inner_scores.append({"params": params, "log_loss": score, "matches": len(predicted)})
        best = min(inner_scores, key=lambda s: s["log_loss"])["params"]
    else:
        best = grid[0]
    train, excluded = usable(training_rows(data, fold.train_seasons, population), features)
    _guard(train, fold)
    return FitResult(make(**best).fit(train), best, excluded, inner_scores)


def _guard(rows: pd.DataFrame, fold: Fold) -> None:
    """Contrôle anti-fuite : aucune ligne de la saison de test (ni au-delà) dans l'apprentissage, aucun scellé."""
    if len(rows) and int(rows["season_year"].max()) >= fold.test_season:
        raise ProtocolError(f"Pli {fold.name} : une ligne de la saison de test ou postérieure dans l'apprentissage.")
    check_seal(rows["match_date"]) if "match_date" in rows.columns else None


def predict_fold(
    fit: FitResult, data: pd.DataFrame, fold: Fold, features: Iterable[str] = ()
) -> tuple[MatchPredictions, int]:
    """Prédictions des matchs de test du pli ; matchs sans prédiction (variable manquante) comptés."""
    rows = test_rows(data, fold.test_season)
    n_matches = rows["match_id"].nunique()
    rows, _ = usable(rows, features)
    rows = complete_matches(rows)
    predicted = fit.model.predict(rows)
    return predicted, int(n_matches - len(predicted))


def intersection(predictions: dict[str, MatchPredictions]) -> np.ndarray:
    """Matchs prédits par **tous** les modèles comparés (rapport I.7), triés."""
    ids = None
    for predicted in predictions.values():
        current = set(predicted.match_id.tolist())
        ids = current if ids is None else ids & current
    return np.array(sorted(ids or []), dtype=np.int64)
