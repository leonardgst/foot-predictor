"""
Score Performance final = somme pondérée des percentiles (0-100) -- cf.
recap clustering, section 6 étape 7.
"""
from __future__ import annotations

import pandas as pd

from foot_predictor.market_value.performance.weights import get_weights_for_cluster


def compute_performance_score(percentiles: pd.DataFrame, cluster_labels: pd.Series) -> pd.Series:
    """percentiles : sortie de compute_percentiles (colonnes *_pctl).
    cluster_labels : Series player_id -> cluster_label (nom du cluster, pas
    juste l'id numérique -- les poids sont définis par label).

    Renvoie une Series player_id -> performance_score (0-100), ou None si
    aucune statistique n'est disponible pour ce joueur (cas limite)."""
    feature_columns = list(percentiles.columns)
    scores = {}

    for player_id, row in percentiles.iterrows():
        label = cluster_labels.get(player_id)
        weights = get_weights_for_cluster(label, feature_columns)
        available = row.dropna()
        if available.empty:
            scores[player_id] = None
            continue
        total_weight = sum(weights.get(col, 0.0) for col in available.index)
        if total_weight == 0:
            scores[player_id] = None
            continue
        score = sum(row[col] * weights.get(col, 0.0) for col in available.index) / total_weight
        scores[player_id] = score

    return pd.Series(scores, name="performance_score")
