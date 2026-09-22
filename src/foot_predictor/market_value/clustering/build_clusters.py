"""
Clustering indépendant par groupe de poste (cf. recap clustering, section 6
étape 3). Stratégie : HDBSCAN en premier choix (gère le bruit sans forcer
chaque joueur dans un cluster) ; si le résultat est instable (trop de bruit,
ou un seul cluster détecté), fallback automatique sur un GMM avec sélection
de k par BIC.

Les seuils ci-dessous sont des valeurs de départ, à ajuster une fois les
diagnostics (data/diagnostics.py) lancés sur les vraies données (cf. recap
clustering, section 9).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

try:
    import hdbscan

    HDBSCAN_AVAILABLE = True
except ImportError:  # pragma: no cover
    HDBSCAN_AVAILABLE = False

MAX_NOISE_RATIO = 0.30  # au-delà, on considère HDBSCAN peu fiable sur ce groupe
MIN_CLUSTERS_HDBSCAN = 2
MIN_SAMPLES_FOR_CLUSTERING = 50  # en dessous, ne pas faire confiance aux clusters
GMM_K_RANGE = range(2, 9)


def _fit_hdbscan(X: np.ndarray) -> tuple[np.ndarray, dict, object]:
    # prediction_data=True : indispensable pour que hdbscan.approximate_predict
    # (clustering/assign_cluster.py) puisse réassigner de nouveaux joueurs sans
    # ré-entraîner -- sans ce flag, le modèle sauvegardé n'a pas de "prediction
    # data" et approximate_predict lève AttributeError("No prediction data was
    # generated") à l'utilisation.
    clusterer = hdbscan.HDBSCAN(min_cluster_size=max(10, len(X) // 20), prediction_data=True)
    labels = clusterer.fit_predict(X)
    noise_ratio = float((labels == -1).mean())
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    meta = {"algorithm": "hdbscan", "noise_ratio": noise_ratio, "n_clusters": n_clusters}
    return labels, meta, clusterer


def _fit_gmm(X: np.ndarray) -> tuple[np.ndarray, dict, object]:
    best_model, best_bic = None, np.inf
    for k in GMM_K_RANGE:
        if k >= len(X):
            break
        model = GaussianMixture(n_components=k, random_state=42)
        model.fit(X)
        bic = model.bic(X)
        if bic < best_bic:
            best_bic, best_model = bic, model
    labels = best_model.predict(X)
    meta = {"algorithm": "gmm", "n_clusters": best_model.n_components, "bic": float(best_bic)}
    return labels, meta, best_model


def fit_clusters(X: pd.DataFrame) -> tuple[pd.Series, dict, object]:
    """X : vecteurs normalisés (une ligne par joueur, un seul groupe de poste
    à la fois -- ne jamais mélanger plusieurs position_bucket ici).

    Renvoie (Series player_id -> cluster_id, métadonnées à logger pour audit,
    modèle entraîné à conserver si on veut réassigner de nouveaux joueurs sans
    ré-entraîner, cf. clustering/assign_cluster.py).
    """
    if len(X) < MIN_SAMPLES_FOR_CLUSTERING:
        raise ValueError(
            f"Seulement {len(X)} joueurs disponibles pour ce groupe de poste "
            f"(< {MIN_SAMPLES_FOR_CLUSTERING}) : clustering non fiable, à reporter."
        )

    values = X.to_numpy()

    if HDBSCAN_AVAILABLE:
        labels, meta, model = _fit_hdbscan(values)
        if meta["noise_ratio"] > MAX_NOISE_RATIO or meta["n_clusters"] < MIN_CLUSTERS_HDBSCAN:
            labels, meta, model = _fit_gmm(values)
            meta["fallback_reason"] = "hdbscan_unstable"
    else:
        labels, meta, model = _fit_gmm(values)
        meta["fallback_reason"] = "hdbscan_not_installed"

    return pd.Series(labels, index=X.index, name="cluster_id"), meta, model
