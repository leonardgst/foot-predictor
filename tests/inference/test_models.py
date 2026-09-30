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
    first = models.replay_model(2023, data, replay_root=tmp_path, log_path=tmp_path / "journal.md")
    assert (tmp_path / "2023" / "model.joblib").exists()
    second = models.replay_model(2023, data=None, replay_root=tmp_path, log_path=tmp_path / "journal.md")
    assert second.card["version"] == first.card["version"] == "rejeu-2023-m3_g0g2"


def test_replay_seasons_open_only_from_2021_and_sealed_seasons_wait_for_the_sealed_test(tmp_path):
    log = tmp_path / "journal.md"
    with pytest.raises(models.ModelUnavailable, match="2021-22"):
        models.check_replay_season(2020, log)
    with pytest.raises(models.ModelUnavailable, match="scellés"):
        models.check_replay_season(2025, log)
    models.check_replay_season(2024, log)  # ouverte
    log.write_text("| x | y | experiments/scelle_h1.yaml | évaluation terminée, rapport z |\n", encoding="utf-8")
    models.check_replay_season(2025, log)  # ouverte une fois le test scellé terminé


def test_season_of_a_day():
    assert models.season_of(dt.date(2024, 8, 15)) == 2024
    assert models.season_of(dt.date(2025, 5, 25)) == 2024
    assert models.season_of(dt.date(2025, 7, 1)) == 2025


def test_missing_active_model_is_reported(tmp_path):
    with pytest.raises(models.ModelUnavailable, match="absent"):
        models.load_active("inexistant", models_root=tmp_path)
