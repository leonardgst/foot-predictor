"""Tests de `modeling/predict_service.py` : le service d'inférence qui relie
un modèle entraîné à un match à venir. Le modèle utilisé ici est ajusté sur
des données synthétiques minimales (pas le vrai Modèle A) : on teste
l'assemblage (features -> X -> lambda -> distribution -> 1N2) et les cas
limites, pas la qualité prédictive (déjà couverte par
`tests/modeling/test_poisson_model.py` et `docs/RESULTATS_MODELE.md`)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.modeling.persistence import PersistedPoissonModel
from foot_predictor.modeling.poisson_model import fit_poisson_model
from foot_predictor.modeling.predict_service import (
    InsufficientFeatureHistoryError,
    predict_match,
    predict_scheduled_match,
)

pytestmark = pytest.mark.db


def _fake_persisted_model() -> PersistedPoissonModel:
    """Modèle A minimal ajusté sur des données synthétiques, avec seulement
    deux features z (form_points_last10, goals_for_last10) pour ne pas avoir
    à construire d'historique xG/classement dans chaque test."""
    X = pd.DataFrame(
        {
            "own_form_points_last10": [10, 5, 2, 8, 3, 9, 1, 7],
            "opp_form_points_last10": [3, 9, 8, 2, 10, 5, 9, 2],
            "own_goals_for_last10": [2.0, 1.0, 0.5, 1.8, 0.7, 2.1, 0.4, 1.9],
            "opp_goals_for_last10": [0.7, 1.8, 2.1, 0.5, 2.0, 1.0, 2.2, 0.6],
            "is_home": [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        }
    )
    y = pd.Series([2, 1, 0, 3, 1, 2, 0, 3])
    model = fit_poisson_model(X, y)
    return PersistedPoissonModel(
        model=model,
        z_feature_columns=["form_points_last10", "goals_for_last10"],
        trained_at=dt.datetime.now(dt.timezone.utc),
        n_rows_train=len(X),
    )


def _seed_one_prior_match(
    make_match, make_team_match, *, competition_id, season_id, team_id, opponent_id, is_home, match_date, goals_for
):
    match = make_match(
        competition_id=competition_id, season_id=season_id, match_date=match_date,
        home_team_id=team_id if is_home else opponent_id,
        away_team_id=opponent_id if is_home else team_id,
        home_goals=goals_for if is_home else 1,
        away_goals=1 if is_home else goals_for,
        status="played",
    )
    make_team_match(match_id=match.id, team_id=team_id, is_home=is_home, goals_for=goals_for, goals_against=1)
    make_team_match(match_id=match.id, team_id=opponent_id, is_home=not is_home, goals_for=1, goals_against=goals_for)
    return match


def test_predict_match_returns_a_valid_joint_probability_distribution(
    db_session, make_competition, make_season, make_team, make_match, make_team_match
):
    competition = make_competition()
    season = make_season(competition.id)
    home_team = make_team("Home FC")
    away_team = make_team("Away FC")
    filler_home = make_team("Filler Home Opponent")
    filler_away = make_team("Filler Away Opponent")

    past_date = dt.datetime(2024, 8, 1, tzinfo=dt.timezone.utc)
    match_date = dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc)

    _seed_one_prior_match(
        make_match, make_team_match, competition_id=competition.id, season_id=season.id,
        team_id=home_team.id, opponent_id=filler_home.id, is_home=True, match_date=past_date, goals_for=3,
    )
    _seed_one_prior_match(
        make_match, make_team_match, competition_id=competition.id, season_id=season.id,
        team_id=away_team.id, opponent_id=filler_away.id, is_home=False, match_date=past_date, goals_for=1,
    )

    prediction = predict_match(
        db_session,
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        match_date=match_date,
        competition_id=competition.id,
        season_id=season.id,
        persisted_model=_fake_persisted_model(),
    )

    assert prediction.lambda_home > 0
    assert prediction.lambda_away > 0
    assert prediction.score_matrix.sum() == pytest.approx(1.0, abs=1e-6)
    assert prediction.p_home_win + prediction.p_draw + prediction.p_away_win == pytest.approx(1.0, abs=1e-6)
    a, b = prediction.most_likely_score
    assert prediction.score_matrix[a, b] == pytest.approx(prediction.score_matrix.max())


def test_predict_match_raises_when_a_team_has_no_history(
    db_session, make_competition, make_season, make_team
):
    competition = make_competition()
    season = make_season(competition.id)
    home_team = make_team("Newly Promoted FC")
    away_team = make_team("Away FC")

    with pytest.raises(InsufficientFeatureHistoryError):
        predict_match(
            db_session,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            match_date=dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc),
            competition_id=competition.id,
            season_id=season.id,
            persisted_model=_fake_persisted_model(),
        )


def test_predict_scheduled_match_reads_match_row_and_matches_predict_match(
    db_session, make_competition, make_season, make_team, make_match, make_team_match
):
    competition = make_competition()
    season = make_season(competition.id)
    home_team = make_team("Home FC")
    away_team = make_team("Away FC")
    filler_home = make_team("Filler Home Opponent")
    filler_away = make_team("Filler Away Opponent")

    past_date = dt.datetime(2024, 8, 1, tzinfo=dt.timezone.utc)
    match_date = dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc)

    _seed_one_prior_match(
        make_match, make_team_match, competition_id=competition.id, season_id=season.id,
        team_id=home_team.id, opponent_id=filler_home.id, is_home=True, match_date=past_date, goals_for=3,
    )
    _seed_one_prior_match(
        make_match, make_team_match, competition_id=competition.id, season_id=season.id,
        team_id=away_team.id, opponent_id=filler_away.id, is_home=False, match_date=past_date, goals_for=1,
    )

    scheduled_match = make_match(
        competition_id=competition.id, season_id=season.id, match_date=match_date,
        home_team_id=home_team.id, away_team_id=away_team.id, status="scheduled",
    )

    model = _fake_persisted_model()
    from_scheduled = predict_scheduled_match(db_session, scheduled_match.id, persisted_model=model)
    direct = predict_match(
        db_session, home_team_id=home_team.id, away_team_id=away_team.id, match_date=match_date,
        competition_id=competition.id, season_id=season.id, persisted_model=model,
    )

    assert from_scheduled.lambda_home == pytest.approx(direct.lambda_home)
    assert from_scheduled.lambda_away == pytest.approx(direct.lambda_away)
    assert np.array_equal(from_scheduled.score_matrix, direct.score_matrix)


def test_predict_scheduled_match_raises_if_match_is_not_scheduled(
    db_session, make_competition, make_season, make_team, make_match
):
    competition = make_competition()
    season = make_season(competition.id)
    home_team = make_team("Home FC")
    away_team = make_team("Away FC")

    played_match = make_match(
        competition_id=competition.id, season_id=season.id,
        match_date=dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc),
        home_team_id=home_team.id, away_team_id=away_team.id,
        home_goals=1, away_goals=0, status="played",
    )

    with pytest.raises(ValueError):
        predict_scheduled_match(db_session, played_match.id, persisted_model=_fake_persisted_model())


def test_predict_scheduled_match_raises_if_match_id_unknown(db_session):
    with pytest.raises(ValueError):
        predict_scheduled_match(db_session, 999_999_999, persisted_model=_fake_persisted_model())
