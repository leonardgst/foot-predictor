"""Split d'évaluation chronologique (jamais aléatoire).

Un split aléatoire laisserait fuir de l'information future : deux lignes du
même match (domicile/extérieur), ou deux matchs proches dans le temps d'une
même équipe, sont corrélées (même forme, même adversaire pour une des deux
lignes). Le split doit donc couper le temps une seule fois : tout ce qui est
strictement avant `cutoff_date` va en train, tout le reste en test -- jamais un
tirage aléatoire de lignes ou de matchs.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from foot_predictor.modeling.dataset import DatasetResult


@dataclass(frozen=True)
class ChronologicalSplit:
    X_train: pd.DataFrame
    y_train: pd.Series
    meta_train: pd.DataFrame
    X_test: pd.DataFrame
    y_test: pd.Series
    meta_test: pd.DataFrame
    cutoff_date: dt.datetime


def chronological_split(dataset: DatasetResult, cutoff_date: dt.datetime) -> ChronologicalSplit:
    """Train = matchs strictement avant `cutoff_date`, test = à partir de
    `cutoff_date` (bornes incluses côté test). `cutoff_date` doit être
    timezone-aware (les dates de `staging.match` le sont)."""
    match_date = dataset.meta["match_date"]
    train_mask = match_date < cutoff_date
    test_mask = ~train_mask

    return ChronologicalSplit(
        X_train=dataset.X.loc[train_mask].reset_index(drop=True),
        y_train=dataset.y.loc[train_mask].reset_index(drop=True),
        meta_train=dataset.meta.loc[train_mask].reset_index(drop=True),
        X_test=dataset.X.loc[test_mask].reset_index(drop=True),
        y_test=dataset.y.loc[test_mask].reset_index(drop=True),
        meta_test=dataset.meta.loc[test_mask].reset_index(drop=True),
        cutoff_date=cutoff_date,
    )
