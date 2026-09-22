"""Tests de `modeling/live_features.py` : calcul en direct du vecteur z pour
un match pas encore joué. Réutilise les mêmes garanties anti-fuite que
`features/rolling_form.py` etc. (strictement avant `before_date`), donc ces
tests vérifient surtout l'assemblage et les cas limites propres à ce module :
colonnes non supportées (z9-z11) et absence totale d'historique."""
from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.modeling.live_features import compute_live_z_features
from foot_predictor.modeling.features_config import DEFAULT_FEATURE_COLUMNS

pytestmark = pytest.mark.db


def test_unsupported_feature_columns_raise_not_implemented_error(
    db_session, make_competition, make_season, make_team
):
    competition = make_competition()
    season = make_season(competition.id)
    team = make_team("Team A")

    with pytest.raises(NotImplementedError):
        compute_live_z_features(
            db_session,
            team_id=team.id,
            is_home=True,
            before_date=dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc),
            competition_id=competition.id,
            season_id=season.id,
            feature_columns=["squad_avg_age"],
        )


def test_team_with_no_history_returns_none_for_form_and_standing(
    db_session, make_competition, make_season, make_team
):
    competition = make_competition()
    season = make_season(competition.id)
    team = make_team("Team A")

    result = compute_live_z_features(
        db_session,
        team_id=team.id,
        is_home=True,
        before_date=dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc),
        competition_id=competition.id,
        season_id=season.id,
        feature_columns=DEFAULT_FEATURE_COLUMNS,
    )

    assert result["goals_for_last10"] is None
    assert result["xg_for_last5"] is None
    assert result["standing_position"] is None


def test_before_date_excludes_a_match_played_on_the_exact_same_datetime(
    db_session, make_competition, make_season, make_team, make_match, make_team_match
):
    """Anti-fuite : un match daté EXACTEMENT `before_date` ne doit pas
    compter dans l'historique (borne strictement inférieure)."""
    competition = make_competition()
    season = make_season(competition.id)
    team = make_team("Team A")
    opponent = make_team("Opponent")

    match_date = dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc)
    match = make_match(
        competition_id=competition.id, season_id=season.id, match_date=match_date,
        home_team_id=team.id, away_team_id=opponent.id, home_goals=5, away_goals=0, status="played",
    )
    make_team_match(match_id=match.id, team_id=team.id, is_home=True, goals_for=5, goals_against=0)
    make_team_match(match_id=match.id, team_id=opponent.id, is_home=False, goals_for=0, goals_against=5)

    excluded = compute_live_z_features(
        db_session, team_id=team.id, is_home=True, before_date=match_date,
        competition_id=competition.id, season_id=season.id,
        feature_columns=["goals_for_last10"],
    )
    assert excluded["goals_for_last10"] is None

    included = compute_live_z_features(
        db_session, team_id=team.id, is_home=True, before_date=match_date + dt.timedelta(days=1),
        competition_id=competition.id, season_id=season.id,
        feature_columns=["goals_for_last10"],
    )
    assert included["goals_for_last10"] == pytest.approx(5.0)
