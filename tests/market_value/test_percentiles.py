"""Tests du calcul de percentiles par cluster (`market_value/performance/percentiles.py`) :
scoping par cluster (anti-fuite -- cf. docs/RECAP_PROJET.md section 10.3,
étape 5 : jamais de comparaison entre clusters différents), et cas limites
(groupe à un seul joueur, valeurs toutes identiques, valeurs manquantes)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foot_predictor.market_value.performance.percentiles import compute_percentiles


def test_percentiles_are_scoped_to_the_same_cluster_not_the_whole_population():
    """Un joueur avec la valeur la plus basse de TOUTE la population mais la
    plus haute de SON cluster doit recevoir un percentile élevé -- preuve que
    le calcul se fait bien par groupe (`groupby('cluster_id')`), pas
    globalement."""
    vectors = pd.DataFrame(
        {"goals_per90": [0.1, 5.0, 6.0, 7.0]},
        index=pd.Index([1, 2, 3, 4], name="player_id"),
    )
    # Joueur 1 seul dans le cluster 0 (=> percentile 100 dans son groupe),
    # alors qu'il a la valeur la plus basse de toute la population.
    cluster_ids = pd.Series([0, 1, 1, 1], index=vectors.index, name="cluster_id")

    result = compute_percentiles(vectors, cluster_ids, ["goals_per90"])

    assert result.loc[1, "goals_per90_pctl"] == pytest.approx(100.0)
    # Dans le cluster 1, joueur 2 a la valeur la plus basse -> percentile le
    # plus bas de son groupe (1/3 * 100).
    assert result.loc[2, "goals_per90_pctl"] == pytest.approx(100.0 / 3)
    assert result.loc[4, "goals_per90_pctl"] == pytest.approx(100.0)


def test_percentiles_single_player_group_gets_the_maximum_percentile():
    vectors = pd.DataFrame({"goals_per90": [1.23]}, index=pd.Index([1], name="player_id"))
    cluster_ids = pd.Series([0], index=vectors.index, name="cluster_id")

    result = compute_percentiles(vectors, cluster_ids, ["goals_per90"])

    assert result.loc[1, "goals_per90_pctl"] == pytest.approx(100.0)


def test_percentiles_all_identical_values_get_the_same_percentile():
    vectors = pd.DataFrame({"goals_per90": [2.0, 2.0, 2.0]}, index=pd.Index([1, 2, 3], name="player_id"))
    cluster_ids = pd.Series([0, 0, 0], index=vectors.index, name="cluster_id")

    result = compute_percentiles(vectors, cluster_ids, ["goals_per90"])

    # rank(pct=True) moyenne les rangs ex-aequo : (1+2+3)/3 = 2 -> 2/3 * 100.
    expected = 100.0 * 2 / 3
    assert result["goals_per90_pctl"].tolist() == pytest.approx([expected, expected, expected])


def test_percentiles_missing_value_yields_nan_without_breaking_peers():
    vectors = pd.DataFrame({"goals_per90": [1.0, np.nan, 3.0]}, index=pd.Index([1, 2, 3], name="player_id"))
    cluster_ids = pd.Series([0, 0, 0], index=vectors.index, name="cluster_id")

    result = compute_percentiles(vectors, cluster_ids, ["goals_per90"])

    assert np.isnan(result.loc[2, "goals_per90_pctl"])
    # Les 2 valeurs non manquantes sont classées entre elles seulement (n=2).
    assert result.loc[1, "goals_per90_pctl"] == pytest.approx(50.0)
    assert result.loc[3, "goals_per90_pctl"] == pytest.approx(100.0)


def test_percentiles_feature_column_absent_from_vectors_is_silently_skipped():
    vectors = pd.DataFrame({"goals_per90": [1.0, 2.0]}, index=pd.Index([1, 2], name="player_id"))
    cluster_ids = pd.Series([0, 0], index=vectors.index, name="cluster_id")

    result = compute_percentiles(vectors, cluster_ids, ["goals_per90", "xg_per90"])

    assert "xg_per90_pctl" not in result.columns
    assert "goals_per90_pctl" in result.columns


def test_percentiles_result_index_matches_input_vectors_index():
    vectors = pd.DataFrame({"goals_per90": [1.0, 2.0, 3.0]}, index=pd.Index([10, 20, 30], name="player_id"))
    cluster_ids = pd.Series([0, 1, 0], index=vectors.index, name="cluster_id")

    result = compute_percentiles(vectors, cluster_ids, ["goals_per90"])

    assert list(result.index) == [10, 20, 30]
