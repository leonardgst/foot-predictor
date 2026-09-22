"""Tests de `modeling/dataset.py` : la construction de X doit inverser les
blocs own/opp selon la perspective (section 2.3 du document mathématique), et
ne jamais rattacher à une équipe les features calculées pour un AUTRE match de
cette même équipe -- LE bug de fuite le plus silencieux possible ici (une
jointure par team_id seul, sans filtrer sur match_id, donnerait un résultat
plausible mais faux)."""
from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.modeling.dataset import build_dataset

pytestmark = pytest.mark.db


def test_own_and_opponent_blocks_are_inverted_between_home_and_away_rows(
    db_session, make_competition, make_season, make_team, make_match, make_team_match, make_team_match_features
):
    competition = make_competition()
    season = make_season(competition.id)
    home_team = make_team("Home FC")
    away_team = make_team("Away FC")

    match = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc),
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        home_goals=2,
        away_goals=1,
        status="played",
    )
    home_tm = make_team_match(match_id=match.id, team_id=home_team.id, is_home=True, goals_for=2, goals_against=1)
    away_tm = make_team_match(match_id=match.id, team_id=away_team.id, is_home=False, goals_for=1, goals_against=2)

    make_team_match_features(
        team_match_id=home_tm.id, match_id=match.id, team_id=home_team.id,
        form_points_last10=9, goals_for_last10=2.5, standing_position=1,
    )
    make_team_match_features(
        team_match_id=away_tm.id, match_id=match.id, team_id=away_team.id,
        form_points_last10=3, goals_for_last10=1.0, standing_position=15,
    )

    feature_columns = ["form_points_last10", "goals_for_last10", "standing_position"]
    result = build_dataset(db_session, feature_columns=feature_columns)

    home_mask = result.meta["team_id"] == home_team.id
    away_mask = result.meta["team_id"] == away_team.id
    home_row = result.X[home_mask].iloc[0]
    away_row = result.X[away_mask].iloc[0]

    assert home_row["own_form_points_last10"] == 9
    assert home_row["opp_form_points_last10"] == 3
    assert away_row["own_form_points_last10"] == 3
    assert away_row["opp_form_points_last10"] == 9

    assert home_row["own_standing_position"] == 1
    assert home_row["opp_standing_position"] == 15
    assert away_row["own_standing_position"] == 15
    assert away_row["opp_standing_position"] == 1

    assert bool(result.meta[home_mask]["is_home"].iloc[0]) is True
    assert bool(result.meta[away_mask]["is_home"].iloc[0]) is False
    assert result.y[home_mask].iloc[0] == 2
    assert result.y[away_mask].iloc[0] == 1


def test_features_are_scoped_to_this_match_not_another_match_of_the_same_team(
    db_session, make_competition, make_season, make_team, make_match, make_team_match, make_team_match_features
):
    """Équipe A joue deux matchs : un match plus ancien (contre C) avec des
    valeurs sentinelles, puis le match testé (contre B) avec d'autres valeurs.
    Si le code joignait par team_id seul (sans filtrer sur match_id), le match
    testé récupérerait par erreur les valeurs du match contre C."""
    competition = make_competition()
    season = make_season(competition.id)
    team_a = make_team("A")
    team_b = make_team("B")
    team_c = make_team("C")

    older_match = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 8, 1, tzinfo=dt.timezone.utc),
        home_team_id=team_a.id,
        away_team_id=team_c.id,
        home_goals=1,
        away_goals=1,
        status="played",
    )
    older_tm_a = make_team_match(match_id=older_match.id, team_id=team_a.id, is_home=True, goals_for=1, goals_against=1)
    older_tm_c = make_team_match(match_id=older_match.id, team_id=team_c.id, is_home=False, goals_for=1, goals_against=1)
    make_team_match_features(team_match_id=older_tm_a.id, match_id=older_match.id, team_id=team_a.id, form_points_last10=999)
    make_team_match_features(team_match_id=older_tm_c.id, match_id=older_match.id, team_id=team_c.id, form_points_last10=888)

    match = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc),
        home_team_id=team_a.id,
        away_team_id=team_b.id,
        home_goals=2,
        away_goals=0,
        status="played",
    )
    tm_a = make_team_match(match_id=match.id, team_id=team_a.id, is_home=True, goals_for=2, goals_against=0)
    tm_b = make_team_match(match_id=match.id, team_id=team_b.id, is_home=False, goals_for=0, goals_against=2)
    make_team_match_features(team_match_id=tm_a.id, match_id=match.id, team_id=team_a.id, form_points_last10=6)
    make_team_match_features(team_match_id=tm_b.id, match_id=match.id, team_id=team_b.id, form_points_last10=0)

    result = build_dataset(db_session, feature_columns=["form_points_last10"])

    row_a_vs_b = result.X[(result.meta["match_id"] == match.id) & (result.meta["team_id"] == team_a.id)].iloc[0]
    assert row_a_vs_b["own_form_points_last10"] == 6
    assert row_a_vs_b["opp_form_points_last10"] == 0


def test_rows_with_a_missing_feature_value_are_dropped_and_counted(
    db_session, make_competition, make_season, make_team, make_match, make_team_match, make_team_match_features
):
    """Un match dont une des deux équipes n'a pas encore assez d'historique
    (feature NULL) doit être écarté des deux côtés (le bloc `opp` du côté
    valide référence justement cette valeur manquante)."""
    competition = make_competition()
    season = make_season(competition.id)
    team_a = make_team("A")
    team_b = make_team("B")

    match = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc),
        home_team_id=team_a.id,
        away_team_id=team_b.id,
        home_goals=1,
        away_goals=0,
        status="played",
    )
    tm_a = make_team_match(match_id=match.id, team_id=team_a.id, is_home=True, goals_for=1, goals_against=0)
    tm_b = make_team_match(match_id=match.id, team_id=team_b.id, is_home=False, goals_for=0, goals_against=1)
    make_team_match_features(team_match_id=tm_a.id, match_id=match.id, team_id=team_a.id, form_points_last10=6)
    make_team_match_features(team_match_id=tm_b.id, match_id=match.id, team_id=team_b.id, form_points_last10=None)

    result = build_dataset(db_session, feature_columns=["form_points_last10"])

    assert len(result.X) == 0
    assert result.n_rows_dropped_missing_values == 2
    assert result.n_matches_dropped_missing_features == 0


def test_matches_missing_features_entirely_on_one_side_are_dropped_and_counted(
    db_session, make_competition, make_season, make_team, make_match, make_team_match, make_team_match_features
):
    """Un match dont une des deux équipes n'a pas de ligne dans
    features.team_match_features (pipeline pas encore passé dessus) doit être
    écarté et compté séparément des lignes écartées pour valeur manquante."""
    competition = make_competition()
    season = make_season(competition.id)
    team_a = make_team("A")
    team_b = make_team("B")

    match = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc),
        home_team_id=team_a.id,
        away_team_id=team_b.id,
        home_goals=1,
        away_goals=0,
        status="played",
    )
    tm_a = make_team_match(match_id=match.id, team_id=team_a.id, is_home=True, goals_for=1, goals_against=0)
    make_team_match(match_id=match.id, team_id=team_b.id, is_home=False, goals_for=0, goals_against=1)
    make_team_match_features(team_match_id=tm_a.id, match_id=match.id, team_id=team_a.id, form_points_last10=6)
    # Pas de team_match_features pour team_b.

    result = build_dataset(db_session, feature_columns=["form_points_last10"])

    assert len(result.X) == 0
    assert result.n_matches_dropped_missing_features == 1
    assert result.n_rows_dropped_missing_values == 0
