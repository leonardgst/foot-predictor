"""
Réutilisation d'un clustering déjà entraîné plutôt que ré-entraînement à
chaque calcul de score : le style de jeu global évolue lentement, donc un
ré-entraînement périodique (proposition : mensuel) suffit largement, plutôt
qu'à chaque `as_of_date` calculé.

⚠️ Décision proposée par défaut, pas actée dans le document de cadrage —
à confirmer/ajuster une fois qu'on voit la fréquence réelle de calcul des
scores en production.

Persistance minimale par fichier joblib versionné par date d'entraînement.
À remplacer par un stockage en base si besoin d'historiser plus proprement
plus tard (ex. table `market_value_clustering_model`).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import joblib
import pandas as pd

MODELS_DIR = Path("models/market_value/clustering")


def _model_path(position_bucket: str, trained_at: dt.date) -> Path:
    return MODELS_DIR / f"{position_bucket.lower()}_{trained_at.isoformat()}.joblib"


def save_clustering_model(
    position_bucket: str,
    trained_at: dt.date,
    scaler,
    cluster_model,
    feature_columns: list[str],
) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = _model_path(position_bucket, trained_at)
    joblib.dump(
        {"scaler": scaler, "cluster_model": cluster_model, "feature_columns": feature_columns},
        path,
    )
    return path


def load_latest_clustering_model(position_bucket: str) -> dict | None:
    if not MODELS_DIR.exists():
        return None
    candidates = sorted(MODELS_DIR.glob(f"{position_bucket.lower()}_*.joblib"))
    if not candidates:
        return None
    return joblib.load(candidates[-1])


def assign_cluster_from_saved_model(vectors: pd.DataFrame, saved: dict) -> pd.Series:
    """vectors : sortie de build_player_vectors, PAS encore normalisée -- le
    scaler sauvegardé s'en charge, pour rester cohérent avec l'entraînement
    d'origine."""
    feature_columns = saved["feature_columns"]
    X = vectors[feature_columns].fillna(vectors[feature_columns].median())
    X_scaled = saved["scaler"].transform(X)

    model = saved["cluster_model"]
    if hasattr(model, "predict"):
        labels = model.predict(X_scaled)
    else:
        # HDBSCAN sans predict natif : approximate_predict nécessite le
        # clusterer d'origine (pas juste les labels).
        import hdbscan

        labels, _ = hdbscan.approximate_predict(model, X_scaled)

    return pd.Series(labels, index=vectors.index, name="cluster_id")
