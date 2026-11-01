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


def write_journal(path, *experiments):
    """Journal du scellé avec une ligne « évaluation terminée » par fichier d'expérience donné."""
    from foot_predictor.seal import SEALED_DONE

    lines = [f"| x | y | {e} | {SEALED_DONE}, rapport z |\n" for e in experiments]
    path.write_text("".join(lines), encoding="utf-8")
    return path


def test_replay_seasons_open_from_2021_and_sealed_seasons_open_with_the_h2_test_line(tmp_path):
    from foot_predictor.seal import H1_SEALED_EXPERIMENT, H2_SEALED_EXPERIMENT

    with pytest.raises(models.ModelUnavailable, match="2021-22"):
        models.check_replay_season(2020)
    models.check_replay_season(2024)  # ouverte
    h1_only = write_journal(tmp_path / "h1.md", H1_SEALED_EXPERIMENT)
    for season in (2025, 2026):  # fermées sans la ligne du test H2 (ADR-0045), même si le test H1 est fini
        for log in (tmp_path / "absent.md", h1_only):
            with pytest.raises(models.ModelUnavailable, match="test scellé de H2"):
                models.check_replay_season(season, log)
    both = write_journal(tmp_path / "h2.md", H1_SEALED_EXPERIMENT, H2_SEALED_EXPERIMENT)
    for season in (2025, 2026, 2027):  # ouvertes par la ligne du journal (ADR-0052)
        models.check_replay_season(season, both)
    with pytest.raises(models.ModelUnavailable, match="2021-22"):
        models.check_replay_season(2020, both)  # l'ouverture ne rouvre pas le passé


def test_sealed_seasons_use_the_model_of_the_test():
    """ADR-0052 : le modèle de 2025-26 et de 2026-27 est celui du pli 2025 (apprentissage 2015-16 à 2024-25)."""
    assert [models.training_season(s) for s in (2021, 2024, 2025, 2026, 2027)] == [2021, 2024, 2025, 2025, 2025]


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


# ------------------------------------------------------------------------------ rejeu H2 (6.10, ADR-0050)


@pytest.fixture(scope="module")
def data_h2(data):
    from tests.modeling.synthetic import with_composition

    return with_composition(data)


def test_h2_replay_model_follows_the_m3_h2_procedure_with_the_g5_run_in(data_h2):
    model, card = models.train_replay_model(2022, data_h2, horizon="H2")
    assert card["horizon"] == "H2" and card["version"] == "rejeu-2022-m3_h2" and card["replay_season"] == 2022
    assert "xi_quality" in card["model"]["features"] and "opp_xi_quality" in card["model"]["features"]
    assert card["training"]["first_season"] == 2016  # 2015-16 sert de rodage à G5 (ADR-0047, D3)
    assert card["training"]["last_season"] == 2021 and card["training"]["includes_sealed_matches"] is False
    assert card["experiment_file"] == "experiments/scelle_h2.yaml" and card["model"]["id"] == "M3_H2"
    assert any("live" in limit for limit in card["limits"])  # limites propres à H2, pas celles de H1


def test_h2_replay_model_never_saw_its_season_nor_later_ones(data_h2):
    _, card = models.train_replay_model(2022, data_h2, horizon="H2")
    later = data_h2.copy()
    later.loc[later["season_year"] >= 2022, "goals_for"] = 9
    _, card_later = models.train_replay_model(2022, later, horizon="H2")
    assert card_later["coefficients"] == card["coefficients"]


def test_h1_replay_model_is_unchanged_by_the_h2_option(data):
    """Garde H1 : même version, même horizon, même début d'apprentissage qu'avant 6.10."""
    _, card = models.train_replay_model(2022, data)
    assert (
        card["horizon"] == "H1" and card["version"] == "rejeu-2022-m3_g0g2" and card["training"]["first_season"] == 2015
    )
    assert "xi_quality" not in card["model"]["features"]


def test_h2_replay_models_are_cached_apart_from_h1(data, data_h2, tmp_path):
    h1 = models.replay_model(2023, data, replay_root=tmp_path)
    h2 = models.replay_model(2023, data_h2, replay_root=tmp_path, horizon="H2")
    assert (tmp_path / "2023" / "model.joblib").exists() and (tmp_path / "h2" / "2023" / "model.joblib").exists()
    assert h1.card["horizon"] == "H1" and h2.card["horizon"] == "H2" and "xi_quality" in h2.features
    again = models.replay_model(2023, data=None, replay_root=tmp_path, horizon="H2")  # lu dans le cache
    assert again.card["version"] == h2.card["version"] == "rejeu-2023-m3_h2"


def test_h2_replay_seasons_are_as_closed_as_h1_and_the_horizon_is_checked(tmp_path):
    with pytest.raises(models.ModelUnavailable, match="test scellé de H2"):
        models.replay_model(2025, horizon="H2", sealed_log=tmp_path / "absent.md")
    with pytest.raises(ValueError, match="Horizon inconnu"):
        models.replay_model(2022, horizon="H3")
    assert models.REPLAY_DATASET_VERSION["H2"] == "ds-2026-11-01-e0defb32"
    assert models.EXPERIMENT_FILE_H2.name == "scelle_h2.yaml" and models.MODEL_ID_H2 == "M3_H2"


def test_the_models_command_lists_h1_and_h2_replay_folders_and_ignores_the_h2_parent(
    data, data_h2, tmp_path, monkeypatch
):
    """Le cache H2 est le sous-dossier `h2/` du cache H1 : il ne doit être pris ni pour une saison ni pour un modèle."""
    from foot_predictor.inference.__main__ import replay_folders

    monkeypatch.setattr(models, "REPLAY_ROOT", tmp_path)
    assert replay_folders() == []
    models.replay_model(2022, data, replay_root=tmp_path)
    models.replay_model(2022, data_h2, replay_root=tmp_path, horizon="H2")
    assert [f.relative_to(tmp_path).as_posix() for f in replay_folders()] == ["2022", "h2/2022"]
