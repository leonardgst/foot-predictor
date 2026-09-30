"""Interface commune des modèles : `fit(lignes d'apprentissage)` puis `predict(lignes de test)`.

Une **ligne** est un couple (match, équipe) du jeu de données versionné (ADR-0030) : deux
lignes par match, `is_home` vrai pour l'équipe à domicile. Un modèle apprend sur les lignes,
mais **prédit des matchs** : `predict` renvoie une `MatchPredictions` indexée par match, avec
λ domicile, λ extérieur et la loi du total P(T = k), k de 0 à 9 et « 10 et plus » (ADR-0009).

Règles (rapport I.7, I.8) :

- `fit` ne reçoit que les lignes d'apprentissage du pli ; tout ce qui s'ajuste (moyennes,
  imputation, standardisation, régularisation) s'ajuste là, jamais sur le test ;
- `predict` reçoit des lignes **sans cible** (`goals_for`, `goals_against` retirées par le
  protocole) : il ne peut pas lire le résultat du match qu'il prédit ;
- une ligne de test à valeur manquante ne reçoit pas de prédiction (le match est absent de la
  sortie, et le protocole le compte) : **aucun remplissage silencieux**.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from foot_predictor.modeling import distributions as dist

TARGET_COLUMNS = ("goals_for", "goals_against")


@dataclass
class MatchPredictions:
    """Prédictions par match (même ordre dans tous les tableaux)."""

    match_id: np.ndarray
    lambda_home: np.ndarray
    lambda_away: np.ndarray
    total: np.ndarray
    """Loi du total, (n, 11)."""
    home: np.ndarray | None = None
    """Loi des buts à domicile sur 0..SUPPORT − 1, (n, SUPPORT), si le modèle la donne."""
    away: np.ndarray | None = None
    joint: np.ndarray | None = None
    """Loi jointe (n, G, G), si le modèle la donne (score exact, 1N2)."""
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.match_id = np.asarray(self.match_id, dtype=np.int64)
        n = len(self.match_id)
        for name in ("lambda_home", "lambda_away", "total"):
            value = np.asarray(getattr(self, name), dtype=float)
            if len(value) != n:
                raise ValueError(f"{name} : {len(value)} valeurs pour {n} matchs")
            setattr(self, name, value)

    def __len__(self) -> int:
        return len(self.match_id)

    def subset(self, match_ids) -> MatchPredictions:
        """Prédictions des seuls `match_ids`, dans leur ordre (intersection des modèles)."""
        position = pd.Series(np.arange(len(self)), index=self.match_id)
        index = position.loc[np.asarray(match_ids)].to_numpy()
        pick = lambda a: None if a is None else a[index]  # noqa: E731
        return MatchPredictions(
            self.match_id[index], self.lambda_home[index], self.lambda_away[index], self.total[index],
            pick(self.home), pick(self.away), pick(self.joint), {k: v[index] for k, v in self.extra.items()},
        )  # fmt: skip

    @classmethod
    def independent_poisson(cls, match_id, lambda_home, lambda_away) -> MatchPredictions:
        """Deux Poisson indépendants : lois par équipe, jointe tronquée, total Poisson(λ_dom + λ_ext)."""
        home, away = dist.poisson_pmf(lambda_home), dist.poisson_pmf(lambda_away)
        return cls(
            match_id, lambda_home, lambda_away, dist.poisson_total(lambda_home, lambda_away), home, away,
            dist.independent_joint(dist.fold(home), dist.fold(away)),  # score sur 0..9 et « 10 et plus »
        )  # fmt: skip


def match_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par match, colonnes `home_*` et `away_*`, à partir des deux lignes (match, équipe).

    Un match dont une des deux lignes manque est écarté.
    """
    home = rows[rows["is_home"]].set_index("match_id")
    away = rows[~rows["is_home"]].set_index("match_id")
    common = home.index.intersection(away.index)
    return home.loc[common].add_prefix("home_").join(away.loc[common].add_prefix("away_"))


class Model:
    """Classe de base : un nom, des hyperparamètres, `fit` et `predict`."""

    name = "modele"
    features: tuple[str, ...] = ()

    def __init__(self, **params) -> None:
        self.params = params

    def fit(self, rows: pd.DataFrame) -> Model:  # pragma: no cover - interface
        raise NotImplementedError

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "params": self.params, "features": list(self.features)}
