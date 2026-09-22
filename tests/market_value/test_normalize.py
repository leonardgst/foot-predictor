"""Tests de la normalisation StandardScaler par groupe de poste
(`market_value/preprocessing/normalize.py`)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foot_predictor.market_value.preprocessing.normalize import normalize_style_vectors


def test_normalize_produces_zero_mean_unit_variance():
    vectors = pd.DataFrame(
        {"goals_per90": [0.1, 0.3, 0.5, 0.7, 0.9]},
        index=pd.Index([1, 2, 3, 4, 5], name="player_id"),
    )

    normalized, scaler, columns = normalize_style_vectors(vectors, feature_columns=["goals_per90"])

    assert columns == ["goals_per90"]
    assert normalized["goals_per90"].mean() == pytest.approx(0.0, abs=1e-9)
    assert normalized["goals_per90"].std(ddof=0) == pytest.approx(1.0, abs=1e-9)


def test_normalize_imputes_nan_with_column_median():
    vectors = pd.DataFrame(
        {"goals_per90": [1.0, 2.0, np.nan]},
        index=pd.Index([1, 2, 3], name="player_id"),
    )

    normalized, _scaler, _columns = normalize_style_vectors(vectors, feature_columns=["goals_per90"])

    # Médiane de [1.0, 2.0] = 1.5 -> imputée à la place du NaN, donc
    # aucune valeur NaN ne subsiste après normalisation.
    assert not normalized["goals_per90"].isna().any()


def test_normalize_only_uses_available_columns_subset():
    vectors = pd.DataFrame(
        {"goals_per90": [1.0, 2.0], "assists_per90": [0.5, 1.5]},
        index=pd.Index([1, 2], name="player_id"),
    )

    _normalized, _scaler, columns = normalize_style_vectors(
        vectors, feature_columns=["goals_per90", "xg_per90"]  # xg_per90 absent des colonnes
    )

    assert columns == ["goals_per90"]


def test_normalize_default_feature_columns_used_when_none_given():
    vectors = pd.DataFrame(
        {"goals_per90": [1.0, 2.0], "duels_won_pct": [0.4, 0.6]},
        index=pd.Index([1, 2], name="player_id"),
    )

    _normalized, _scaler, columns = normalize_style_vectors(vectors)

    assert set(columns) == {"goals_per90", "duels_won_pct"}


def test_normalize_index_preserved_as_player_id():
    vectors = pd.DataFrame(
        {"goals_per90": [1.0, 2.0, 3.0]},
        index=pd.Index([10, 20, 30], name="player_id"),
    )

    normalized, _scaler, _columns = normalize_style_vectors(vectors, feature_columns=["goals_per90"])

    assert list(normalized.index) == [10, 20, 30]
