"""
Percentile de chaque statistique per90, calculé au sein du même groupe de
poste ET du même cluster (cf. recap clustering, section 6 étape 5) -- jamais
au sein du position_bucket entier, sinon on recompare un "ailier créateur" à
un "ailier finisseur" sur les mêmes variables, ce qui n'a pas de sens.
"""
from __future__ import annotations

import pandas as pd


def compute_percentiles(
    vectors: pd.DataFrame, cluster_ids: pd.Series, feature_columns: list[str]
) -> pd.DataFrame:
    """vectors : indexé par player_id, colonnes *_per90/pct brutes (non
    normalisées -- les percentiles se calculent sur les valeurs réelles, pas
    sur le vecteur standardisé utilisé pour le clustering).
    cluster_ids : Series player_id -> cluster_id (même index que vectors).

    Renvoie un DataFrame même index, une colonne `<feature>_pctl` par
    feature (0-100)."""
    df = vectors.join(cluster_ids)
    result = pd.DataFrame(index=df.index)

    for _cluster_id, group in df.groupby("cluster_id"):
        for col in feature_columns:
            if col not in group.columns:
                continue
            pct = group[col].rank(pct=True, na_option="keep") * 100
            result.loc[group.index, f"{col}_pctl"] = pct

    return result
