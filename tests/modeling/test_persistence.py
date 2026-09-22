"""Tests de `modeling/persistence.py` : sauvegarde/chargement joblib du
Modèle A entraîné, sans dépendance base de données (pas de marqueur `db`)."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from foot_predictor.modeling.persistence import PersistedPoissonModel, load_model, save_model
from foot_predictor.modeling.poisson_model import fit_poisson_model


def _fit_tiny_model():
    X = pd.DataFrame({"own_form_points_last10": [10, 5, 2, 8], "is_home": [1.0, 0.0, 1.0, 0.0]})
    y = pd.Series([2, 1, 0, 3])
    return fit_poisson_model(X, y)


def test_save_then_load_roundtrips_predictions(tmp_path):
    model = _fit_tiny_model()
    persisted = PersistedPoissonModel(
        model=model,
        z_feature_columns=["form_points_last10"],
        trained_at=dt.datetime.now(dt.timezone.utc),
        n_rows_train=4,
    )
    path = tmp_path / "model.joblib"

    save_model(persisted, path)
    reloaded = load_model(path)

    X_new = pd.DataFrame({"own_form_points_last10": [7], "is_home": [1.0]})
    original_lambda = persisted.model.predict_lambda(X_new)
    reloaded_lambda = reloaded.model.predict_lambda(X_new)

    assert reloaded_lambda == pytest.approx(original_lambda)
    assert reloaded.z_feature_columns == ["form_points_last10"]
    assert reloaded.n_rows_train == 4


def test_load_missing_path_raises_file_not_found_with_helpful_message(tmp_path):
    missing_path = tmp_path / "does_not_exist.joblib"

    with pytest.raises(FileNotFoundError, match="train_and_persist"):
        load_model(missing_path)
