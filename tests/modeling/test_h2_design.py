"""Variables H2 (G4 à G6) dans le modèle par équipe : colonnes, début d'apprentissage, effet retrouvé. Sans base."""

from __future__ import annotations

import numpy as np
import pytest

from foot_predictor.modeling import protocol
from foot_predictor.modeling.design import (
    COHESION_VARIANTS,
    Design,
    g6_columns,
)
from foot_predictor.modeling.models.team import M3
from tests.modeling.synthetic import realistic_rows, with_composition

H1 = ("G0", "G1", "G2")


def test_h1_design_is_unchanged_by_the_h2_groups():
    design = Design(H1, 120)
    assert design.required() == [
        "is_home", "api_league_id", "behind_closed_doors", "elo_pre", "opp_elo_pre",
        "goals_for_ewm_h120", "goals_against_ewm_h120", "xgp_for_ewm_h120", "xgp_against_ewm_h120",
        "opp_goals_for_ewm_h120", "opp_goals_against_ewm_h120", "opp_xgp_for_ewm_h120", "opp_xgp_against_ewm_h120",
    ]  # fmt: skip
    assert design.first_training_season is None
    assert design.describe() == {"groups": ["G0", "G1", "G2"], "half_life": 120, "level": "team", "dropped": []}
    assert M3(groups=H1, half_life=120).params == {"groups": list(H1), "half_life": 120, "check_dispersion": False}


def test_g6_needs_a_cohesion_variant_and_nothing_else_accepts_one():
    with pytest.raises(ValueError, match="cohésion"):
        Design((*H1, "G6"), 120)
    with pytest.raises(ValueError, match="cohesion sans G6"):
        Design(H1, 120, cohesion="h5")
    with pytest.raises(ValueError, match="cohésion"):
        Design((*H1, "G6"), 120, cohesion="h7")


@pytest.mark.parametrize("variant", COHESION_VARIANTS)
def test_g6_columns_are_three_variables_per_team_or_the_overlap_alone(variant):
    columns = g6_columns(variant)
    own = [c for c in columns if not c.startswith("opp_")]
    assert len(own) == (1 if variant == "overlap_only" else 3)
    assert columns[len(own) :] == [f"opp_{c}" for c in own]
    assert "xi_overlap_prev" in own


def test_cohesion_column_names_match_the_dataset():
    assert "xi_cohesion_ewm_hinf" in g6_columns("hinf")
    assert "xi_cohesion_ewm_h10" in g6_columns("h10")
    assert "xi_cohesion_reset" in g6_columns("reset") and "xi_cohesion_win10" in g6_columns("win10")


def test_groups_with_a_short_history_start_training_later():
    """D3 (ADR-0047) : G5 apprend dès 2016-17, G4 dès 2017-18 ; le plus tardif l'emporte."""
    assert Design((*H1, "G6"), 120, cohesion="h5").first_training_season is None
    assert Design((*H1, "G5"), 120).first_training_season == 2016
    assert Design((*H1, "G4"), 120).first_training_season == 2017
    assert Design((*H1, "G6", "G5", "G4"), 120, cohesion="h5").first_training_season == 2017


def test_required_columns_cover_every_group():
    required = Design((*H1, "G6", "G5", "G4"), 120, cohesion="hinf").required()
    for column in ("xi_overlap_prev", "xi_cohesion_ewm_hinf", "opp_xi_new_starters", "xi_quality",
                   "opp_xi_mean_age", "coach_tenure_days", "opp_coach_is_new"):  # fmt: skip
        assert column in required


@pytest.fixture(scope="module")
def rows():
    return with_composition(realistic_rows(seed=3, rounds=22), quality_effect=0.12)


def test_m3_recovers_a_known_effect_of_the_xi_quality(rows):
    model = M3(groups=(*H1, "G5"), half_life=120).fit(rows[rows["season_year"] < 2024])
    beta = model.diagnostics_["coefficients"]
    # log λ = ... + 0,12 · (qualité − qualité adverse) / 0,1 : par écart type de qualité (0,1), +0,12 et −0,12.
    assert beta["z_xi_quality"] == pytest.approx(0.12, abs=0.04)
    assert beta["z_opp_xi_quality"] == pytest.approx(-0.12, abs=0.04)
    assert abs(beta["z_xi_mean_age"]) < 0.04  # variable sans effet


def test_m3_with_all_h2_groups_predicts_the_matches_of_the_test_rows(rows):
    train = rows[rows["season_year"] < 2024]
    test = rows[rows["season_year"] == 2024].drop(columns=["goals_for", "goals_against"])
    model = M3(groups=(*H1, "G6", "G5", "G4"), half_life=120, cohesion="h5").fit(train)
    predicted = model.predict(test)
    assert len(predicted) == test["match_id"].nunique()
    assert np.isfinite(predicted.total).all() and np.allclose(predicted.total.sum(axis=1), 1.0)
    assert model.params["cohesion"] == "h5"


def test_select_and_fit_counts_the_run_in_rows_and_does_not_train_on_them(rows):
    fold = protocol.Fold(2021)
    make = M3
    grid = [{"groups": (*H1, "G5"), "half_life": 120}]
    features = make(**grid[0]).features
    result = protocol.select_and_fit(make, grid, rows, fold, "top5", features, first_season=2016)
    early = rows[(rows["season_year"] == 2015) & rows["api_league_id"].isin([39, 140, 78, 135, 61])]
    assert result.run_in_rows == len(early) and result.first_training_season == 2016
    kept = rows[rows["season_year"].between(2016, 2020) & rows["api_league_id"].isin([39, 140, 78, 135, 61])]
    assert result.model.diagnostics_["n_rows"] == len(kept)  # les lignes de 2015-16 n'entrent pas dans l'ajustement


def test_without_a_first_season_nothing_changes(rows):
    fold = protocol.Fold(2021)
    grid = [{"groups": H1, "half_life": 120}]
    features = M3(**grid[0]).features
    result = protocol.select_and_fit(M3, grid, rows, fold, "top5", features)
    assert result.run_in_rows == 0 and result.first_training_season is None


def test_train_from_is_a_window_control_that_never_starts_before_the_groups(rows):
    """ADR-0048 : un témoin sans variable H2 appris sur la même fenêtre qu'un modèle à historique court."""
    assert M3(groups=H1, half_life=120, train_from=2017).first_training_season == 2017
    assert M3(groups=(*H1, "G5"), half_life=120, train_from=2015).first_training_season == 2016
    assert M3(groups=(*H1, "G4"), half_life=120, train_from=2016).first_training_season == 2017
    assert M3(groups=H1, half_life=120).first_training_season is None
    assert M3(groups=H1, half_life=120, train_from=2017).params["train_from"] == 2017
    grid = [{"groups": H1, "half_life": 120, "train_from": 2017}]
    result = protocol.select_and_fit(M3, grid, rows, protocol.Fold(2021), "top5", M3(**grid[0]).features, 2017)
    assert result.run_in_rows == len(rows[rows["season_year"].between(2015, 2016) & rows["eval_population"]])
