"""Effet des tirs de football-data (5.7) : retrait des tirs de l'API, correction de Holm, mesure appariée.

Données synthétiques : la mesure réelle tourne sur la base de travail (`python -m foot_predictor.inference.shots_check`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foot_predictor.features.dataset import build_frame
from foot_predictor.inference import shots_check as S
from foot_predictor.modeling.models.base import MatchPredictions, match_frame
from foot_predictor.modeling.models.team import M3
from tests.features.test_dataset import COEF, PARAMS
from tests.inference.test_predict import FakeModel, shifted_matches


def with_api_shots(matches: pd.DataFrame) -> pd.DataFrame:
    """Tirs de l'API différents de ceux de football-data (un tir cadré de plus) : la source se voit."""
    out = matches.copy()
    for side in ("home", "away"):
        out[f"{side}_shots_api"] = out[f"{side}_shots_fd"] + 2
        out[f"{side}_sot_api"] = out[f"{side}_sot_fd"] + 1
    return out


class ShotSensitiveModel(FakeModel):
    """λ croissant avec la moyenne glissante de l'`xg_proxy` : une variante de tirs change la perte."""

    def __init__(self):
        super().__init__()
        self.feature = next(f for f in self.features if "xg" in f)

    def predict(self, rows):
        matches = match_frame(rows)
        home = rows[rows["is_home"].astype(bool)].set_index("match_id").loc[matches.index]
        lam = np.exp(0.2 * home[self.feature].to_numpy(float))
        return MatchPredictions.independent_poisson(matches.index.to_numpy(), lam, np.full(len(lam), 1.1))


@pytest.fixture(scope="module")
def data():
    matches = with_api_shots(shifted_matches())
    return matches, build_frame(matches, PARAMS, COEF)


def build(frame):
    return build_frame(frame, PARAMS, COEF)


def test_without_api_shots_touches_only_the_chosen_seasons_and_never_the_input():
    matches = with_api_shots(shifted_matches())
    one = S.without_api_shots(matches, [2023])
    assert one.loc[one["season_year"] == 2023, list(S.API_SHOT_COLUMNS)].isna().all().all()
    assert one.loc[one["season_year"] == 2022, list(S.API_SHOT_COLUMNS)].notna().all().all()
    assert S.without_api_shots(matches)[list(S.API_SHOT_COLUMNS)].isna().all().all()
    assert matches[list(S.API_SHOT_COLUMNS)].notna().all().all()  # copie : l'entrée est intacte
    assert one["home_sot_fd"].equals(matches["home_sot_fd"])  # football-data jamais touché


def test_holm_is_step_down_monotone_and_treats_empty_p_as_one():
    adjusted = S.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": float("nan")})
    assert adjusted == pytest.approx({"a": 0.04, "c": 0.09, "b": 0.09, "d": 1.0})


def test_source_gap_counts_only_team_matches_with_both_sources(data):
    matches, _ = data
    gap = S.source_gap(matches, [2022, 2023])["Premier League"]
    assert gap["mean_gap"] == pytest.approx(-1.0)  # football-data − API = −1 tir cadré par construction
    assert gap["share_equal"] == 0.0
    assert gap["team_matches"] == 2 * int((matches["api_league_id"] == 39).sum())


def test_changed_share_sees_a_history_from_another_source(data):
    matches, dataset = data
    features = list(FakeModel().features)
    reference = dataset[dataset["season_year"] == 2023]
    assert S.changed_share(reference, reference, features) == 0.0
    variant = build(S.without_api_shots(matches, [2023]))
    assert S.changed_share(reference, variant[variant["season_year"] == 2023], features) > 0


def test_constant_model_gives_a_null_gap_and_is_not_significant(data):
    matches, dataset = data
    report = S.run(matches, dataset, {"version": "essai"}, seasons=(2023,), model_for=lambda s: FakeModel(),
                   build=build, n_resamples=200)  # fmt: skip
    for variant in report["variants"].values():
        assert variant["pooled"]["mean"] == 0.0
        assert not variant["significant"]
        assert variant["matches"]["2023"]["common"] > 0
    assert "Aucun écart significatif" in S.render(report)


def test_shot_sensitive_model_sees_the_season_variant_and_the_extreme_one(data):
    matches, dataset = data
    report = S.run(matches, dataset, {"version": "essai"}, seasons=(2023,), model_for=lambda s: ShotSensitiveModel(),
                   build=build, n_resamples=200)  # fmt: skip
    season, extreme = report["variants"]["saison_S"], report["variants"]["toute_histoire"]
    assert season["pooled"]["mean"] != 0.0
    assert extreme["changed_rows"]["2023"] >= season["changed_rows"]["2023"] > 0
    assert set(season["per_league"]) == {"Premier League"}  # championnats absents : pas d'intervalle vide
    assert report["seed"] == S.SEED and report["trials"] == 1
    markdown = S.render(report)
    assert "Holm (p)" in markdown and "## Conclusion" in markdown


def test_m3_features_include_the_xg_proxy_history():
    assert any("xg" in f for f in M3(("G0", "G1", "G2"), 60).features)
