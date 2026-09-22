"""Tests de la réassignation de joueurs à un clustering déjà entraîné
(`market_value/clustering/assign_cluster.py`) : chemin `predict` natif (GMM)
et chemin `hdbscan.approximate_predict` (HDBSCAN, qui n'a pas de `.predict`),
y compris le label de bruit -1."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from foot_predictor.market_value.clustering.assign_cluster import assign_cluster_from_saved_model

FEATURE_COLUMNS = ["f1", "f2"]


def _two_blob_training_data(n_per_blob: int = 30, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    blob_a = rng.normal(loc=0.0, scale=0.3, size=(n_per_blob, 2))
    blob_b = rng.normal(loc=10.0, scale=0.3, size=(n_per_blob, 2))
    values = np.vstack([blob_a, blob_b])
    index = pd.Index(range(1, len(values) + 1), name="player_id")
    return pd.DataFrame(values, index=index, columns=FEATURE_COLUMNS)


def test_assign_cluster_uses_native_predict_when_available_gmm():
    """Un modèle avec `.predict` (GMM) doit passer par le chemin natif, pas
    par `hdbscan.approximate_predict`."""
    train = _two_blob_training_data()
    scaler = StandardScaler().fit(train[FEATURE_COLUMNS])
    gmm = GaussianMixture(n_components=2, random_state=42).fit(scaler.transform(train[FEATURE_COLUMNS]))

    saved = {"scaler": scaler, "cluster_model": gmm, "feature_columns": FEATURE_COLUMNS}
    new_vectors = pd.DataFrame(
        {"f1": [0.0, 10.0], "f2": [0.0, 10.0]}, index=pd.Index([101, 102], name="player_id")
    )

    labels = assign_cluster_from_saved_model(new_vectors, saved)

    assert isinstance(labels, pd.Series)
    assert labels.name == "cluster_id"
    assert list(labels.index) == [101, 102]
    # Les deux nouveaux points sont chacun au centre d'un des deux blobs
    # d'entraînement -> ils doivent être assignés à des clusters différents.
    assert labels.loc[101] != labels.loc[102]


def test_assign_cluster_imputes_missing_feature_with_median_of_new_vectors():
    train = _two_blob_training_data()
    scaler = StandardScaler().fit(train[FEATURE_COLUMNS])
    gmm = GaussianMixture(n_components=2, random_state=42).fit(scaler.transform(train[FEATURE_COLUMNS]))
    saved = {"scaler": scaler, "cluster_model": gmm, "feature_columns": FEATURE_COLUMNS}

    new_vectors = pd.DataFrame(
        {"f1": [0.0, 0.4, np.nan], "f2": [0.0, 0.2, 0.1]},
        index=pd.Index([1, 2, 3], name="player_id"),
    )

    labels = assign_cluster_from_saved_model(new_vectors, saved)

    # Ne doit pas lever malgré le NaN (imputé par la médiane des vecteurs
    # passés en argument, pas ceux d'entraînement) et renvoyer un label pour
    # chaque joueur, y compris celui avec la valeur manquante.
    assert len(labels) == 3
    assert not labels.isna().any()


def test_assign_cluster_uses_hdbscan_approximate_predict_when_no_native_predict():
    """Un modèle HDBSCAN (pas de `.predict`) doit passer par
    `hdbscan.approximate_predict`, y compris pour un point aberrant très
    éloigné des deux clusters d'entraînement (label de bruit -1)."""
    hdbscan = pytest.importorskip("hdbscan")

    train = _two_blob_training_data(seed=7)
    scaler = StandardScaler().fit(train[FEATURE_COLUMNS])
    X_scaled = scaler.transform(train[FEATURE_COLUMNS])

    clusterer = hdbscan.HDBSCAN(min_cluster_size=10, prediction_data=True)
    clusterer.fit(X_scaled)
    assert not hasattr(clusterer, "predict")  # confirme qu'on est bien sur le chemin approximate_predict

    saved = {"scaler": scaler, "cluster_model": clusterer, "feature_columns": FEATURE_COLUMNS}
    new_vectors = pd.DataFrame(
        {"f1": [0.0, 10.0, 10_000.0], "f2": [0.0, 10.0, 10_000.0]},
        index=pd.Index([1, 2, 3], name="player_id"),
    )

    labels = assign_cluster_from_saved_model(new_vectors, saved)

    assert list(labels.index) == [1, 2, 3]
    assert labels.loc[1] != labels.loc[2]
    assert labels.loc[3] == -1  # point aberrant -> bruit
