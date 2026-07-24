"""
Normalisation StandardScaler indépendante par groupe de poste. Ne jamais fit
un scaler sur des joueurs de groupes de poste différents mélangés (cf. recap
clustering, section 6 étape 2).
"""
from __future__ import annotations

import pandas as pd
from sklearn.preprocessing import StandardScaler

# Vecteur de style : uniquement des variables de style de jeu par 90 minutes
# ou des ratios déjà normalisés par nature. Volontairement PAS d'âge, minutes
# jouées, ou nombre de matchs (cf. recap clustering, section 6 étape 1).
STYLE_FEATURE_COLUMNS = [
    "goals_per90",
    "assists_per90",
    "shots_per90",
    "shots_on_target_per90",
    "key_passes_per90",
    "xg_per90",
    "xa_per90",
    "npxg_per90",
    "tackles_per90",
    "interceptions_per90",
    "duels_won_pct",
    "dribbles_success_per90",
    "dribbled_past_per90",
    "fouls_drawn_per90",
    "fouls_committed_per90",
    "pass_accuracy_pct",
]


def normalize_style_vectors(
    vectors: pd.DataFrame, feature_columns: list[str] | None = None
) -> tuple[pd.DataFrame, StandardScaler, list[str]]:
    """vectors : sortie de build_player_vectors (indexée par player_id).
    Renvoie (DataFrame normalisé, scaler fitté, colonnes utilisées) — le
    scaler est à conserver/versionner si on veut ré-appliquer la même
    normalisation plus tard sans refitter (cf. clustering/assign_cluster.py).

    Imputation minimale : NaN -> médiane de la colonne. Les colonnes xG à
    faible couverture (cf. *_coverage dans `vectors`) devront être arbitrées
    séparément une fois les diagnostics lancés sur les vraies données -- si
    la couverture est trop faible, envisager de retirer xg_per90/xa_per90/
    npxg_per90 du vecteur de style plutôt que de les imputer massivement.
    """
    feature_columns = feature_columns or STYLE_FEATURE_COLUMNS
    available = [c for c in feature_columns if c in vectors.columns]

    X = vectors[available].copy()
    X = X.fillna(X.median())

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return pd.DataFrame(X_scaled, index=vectors.index, columns=available), scaler, available
