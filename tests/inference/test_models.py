"""Modèles de l'inférence : allègement sans effet, rejeu par pli (jamais la saison ni les suivantes), scellé."""

from __future__ import annotations

import datetime as dt
import io

import joblib
import numpy as np
import pytest

from foot_predictor.inference import models
from foot_predictor.modeling.models.team import M3
from tests.modeling.synthetic import realistic_rows


@pytest.fixture(scope="module")
def data():
    return realistic_rows(seasons=range(2015, 2025), teams_per_league=10, rounds=10)


def test_slimming_keeps_predictions_bit_for_bit_and_shrinks_the_file(data):
    train = data[data["season_year"] < 2024]
    test = data[data["season_year"] == 2024].drop(columns=["goals_for", "goals_against"])
    model = M3(("G0", "G1", "G2"), 120).fit(train)
    before = model.predict(test)
    size_before = len(_dump(model))
    models.slim(model)
    after = model.predict(test)
    np.testing.assert_array_equal(before.total, after.total)
    np.testing.assert_array_equal(before.lambda_home, after.lambda_home)
    assert len(_dump(model)) < size_before / 3


def _dump(obj) -> bytes:
    buffer = io.BytesIO()
    joblib.dump(obj, buffer)
    return buffer.getvalue()


def test_replay_model_of_a_season_never_saw_it_nor_later_seasons(data):
    model, card = models.train_replay_model(2022, data)
    assert card["training"]["last_season"] == 2021 and card["training"]["first_season"] == 2015
    assert card["replay_season"] == 2022 and card["model"]["params"]["half_life"] in (60, 120, 240)
    assert card["training"]["includes_sealed_matches"] is False
    later = data.copy()
    later.loc[later["season_year"] >= 2022, "goals_for"] = 9  # changer la saison S et après ne change rien
    _, card_later = models.train_replay_model(2022, later)
    assert card_later["coefficients"] == card["coefficients"]


def test_replay_model_is_cached_on_disk(data, tmp_path):
    first = models.replay_model(2023, data, replay_root=tmp_path)
    assert (tmp_path / "2023" / "model.joblib").exists()
    second = models.replay_model(2023, data=None, replay_root=tmp_path)
    assert second.card["version"] == first.card["version"] == "rejeu-2023-m3_g0g2"


def test_replay_seasons_open_from_2021_and_sealed_seasons_stay_closed_until_the_h2_test():
    with pytest.raises(models.ModelUnavailable, match="2021-22"):
        models.check_replay_season(2020)
    models.check_replay_season(2024)  # ouverte
    for season in (2025, 2026):  # fermées même après le test H1 : le test de H2 réutilisera ces matchs (ADR-0045)
        with pytest.raises(models.ModelUnavailable, match="test scellé de H2"):
            models.check_replay_season(season)


def test_the_final_h1_model_is_the_default_active_model():
    assert models.DEFAULT_ACTIVE_VERSION == "scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle"


def test_activating_a_missing_model_is_refused_before_any_database_access(monkeypatch, capsys):
    from foot_predictor.db import session as db_session_module
    from foot_predictor.inference.__main__ import main

    monkeypatch.setattr(db_session_module, "get_engine", lambda: pytest.fail("aucune base ne doit être ouverte"))
    assert main(["models", "--activate", "version-absente-de-models"]) == 2
    assert "Modèle absent : version-absente-de-models" in capsys.readouterr().err


def test_season_of_a_day():
    assert models.season_of(dt.date(2024, 8, 15)) == 2024
    assert models.season_of(dt.date(2025, 5, 25)) == 2024
    assert models.season_of(dt.date(2025, 7, 1)) == 2025


def test_missing_active_model_is_reported(tmp_path):
    with pytest.raises(models.ModelUnavailable, match="absent"):
        models.load_active("inexistant", models_root=tmp_path)
