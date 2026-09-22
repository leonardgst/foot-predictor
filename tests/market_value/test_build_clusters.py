"""Tests du clustering par groupe de poste (`market_value/clustering/build_clusters.py`) :
garde-fou d'échantillon minimum, forme du résultat sur un petit échantillon
synthétique bien séparé en deux groupes."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foot_predictor.market_value.clustering.build_clusters import (
    MIN_SAMPLES_FOR_CLUSTERING,
    fit_clusters,
)


def _two_blob_dataframe(n_per_blob: int = 30, seed: int = 42) -> pd.DataFrame:
    """Deux groupes bien séparés dans l'espace des features normalisées, pour
    que HDBSCAN (ou son fallback GMM) les distingue de façon déterministe."""
    rng = np.random.default_rng(seed)
    blob_a = rng.normal(loc=0.0, scale=0.3, size=(n_per_blob, 3))
    blob_b = rng.normal(loc=8.0, scale=0.3, size=(n_per_blob, 3))
    values = np.vstack([blob_a, blob_b])
    index = pd.Index(range(1, len(values) + 1), name="player_id")
    return pd.DataFrame(values, index=index, columns=["f1", "f2", "f3"])


def test_fit_clusters_raises_below_minimum_sample_size():
    tiny = pd.DataFrame(
        {"f1": np.arange(MIN_SAMPLES_FOR_CLUSTERING - 1, dtype=float)},
        index=pd.Index(range(MIN_SAMPLES_FOR_CLUSTERING - 1), name="player_id"),
    )

    with pytest.raises(ValueError, match="clustering non fiable"):
        fit_clusters(tiny)


def test_fit_clusters_accepts_exactly_the_minimum_sample_size():
    """Le garde-fou est une borne stricte (`<`), donc exactement le seuil ne
    doit pas lever d'erreur."""
    rng = np.random.default_rng(1)
    values = rng.normal(size=(MIN_SAMPLES_FOR_CLUSTERING, 2))
    X = pd.DataFrame(
        values, index=pd.Index(range(MIN_SAMPLES_FOR_CLUSTERING), name="player_id"), columns=["f1", "f2"]
    )

    labels, meta, model = fit_clusters(X)

    assert len(labels) == MIN_SAMPLES_FOR_CLUSTERING
    assert meta["algorithm"] in {"hdbscan", "gmm"}


def test_fit_clusters_returns_series_indexed_like_input():
    X = _two_blob_dataframe()

    labels, meta, model = fit_clusters(X)

    assert isinstance(labels, pd.Series)
    assert labels.name == "cluster_id"
    assert list(labels.index) == list(X.index)
    assert len(labels) == len(X)


def test_fit_clusters_on_two_well_separated_blobs_finds_two_groups():
    """Sur un jeu de données synthétique où deux groupes sont nettement
    séparés, le clustering (HDBSCAN ou son fallback GMM) doit distinguer au
    moins 2 groupes -- ne doit pas tout regrouper en un seul cluster ni
    planter."""
    X = _two_blob_dataframe()

    labels, meta, model = fit_clusters(X)

    non_noise_labels = set(labels[labels != -1].unique())
    assert len(non_noise_labels) >= 2
    assert meta["algorithm"] in {"hdbscan", "gmm"}
    assert model is not None


def test_fit_clusters_labels_are_integer_typed():
    X = _two_blob_dataframe()

    labels, _meta, _model = fit_clusters(X)

    assert np.issubdtype(labels.dtype, np.integer)
