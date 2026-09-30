"""Traçabilité (ops.prediction, ops.model_registry) : idempotence, modes séparés, live avant le coup d'envoi."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from foot_predictor.db.models import ModelRegistry, Prediction
from foot_predictor.inference.store import (
    LivePredictionTooLate,
    active_version,
    live_deadline,
    register_model,
    save_prediction,
)

pytestmark = pytest.mark.db

KICKOFF = "2026-10-24T15:00:00+00:00"


def answer(mode="replay", status="available", kickoff=KICKOFF, match_id=900_001):
    prediction = None
    if status == "available":
        prediction = {
            "lambda_home": 1.5, "lambda_away": 1.1, "expected_total": 2.6, "p_over_2_5": 0.48,
            "total_distribution": {str(k): 0.1 for k in range(10)} | {"10+": 0.0},
            "interval": {"low": 1, "high": 5, "high_label": "5", "announced_coverage": 0.87},
        }  # fmt: skip
    return {
        "match_id": match_id, "date": "2026-10-24", "kickoff_utc": kickoff, "competition_id": 1,
        "home_team_id": 1, "away_team_id": 2, "mode": mode, "horizon": "H1", "status": status,
        "reasons": [] if status == "available" else ["xgp_for_ewm_h240 (domicile) manquante : …"],
        "availability": [{"variable": "is_home", "side": "domicile", "status": "presente", "value": 1}],
        "model_version": "essai-v1", "data_version": "load_run-5", "data_complete_until": "2026-10-23",
        "prediction": prediction,
    }  # fmt: skip


def count(session, **filters):
    query = (
        select(func.count()).select_from(Prediction).where(*[getattr(Prediction, k) == v for k, v in filters.items()])
    )
    return session.execute(query).scalar_one()


def test_saving_is_idempotent_and_force_adds_a_row(db_session):
    first = save_prediction(db_session, answer(), dt.date(2026, 10, 24))
    again = save_prediction(db_session, answer(), dt.date(2026, 10, 24))
    assert first.created and not again.created and again.prediction.id == first.prediction.id
    forced = save_prediction(db_session, answer(), dt.date(2026, 10, 24), force=True)
    assert forced.created and count(db_session, match_id=900_001) == 2


def test_replay_and_live_are_separate(db_session):
    early = dt.datetime(2026, 10, 24, 14, 0, tzinfo=dt.UTC)
    save_prediction(db_session, answer("replay"), dt.date(2026, 10, 24))
    live = save_prediction(db_session, answer("live"), dt.date(2026, 10, 23), now=early)
    assert live.created and count(db_session, match_id=900_001, mode="live") == 1


def test_live_prediction_after_kickoff_is_refused(db_session):
    with pytest.raises(LivePredictionTooLate):
        save_prediction(
            db_session, answer("live"), dt.date(2026, 10, 24), now=dt.datetime(2026, 10, 24, 15, 0, tzinfo=dt.UTC)
        )
    assert count(db_session, match_id=900_001) == 0


def test_live_deadline_without_kickoff_time_is_the_start_of_the_day():
    assert live_deadline(answer("live", kickoff=None)) == dt.datetime(2026, 10, 24, tzinfo=dt.UTC)
    assert live_deadline(answer("live")) == dt.datetime(2026, 10, 24, 15, tzinfo=dt.UTC)


def test_unavailable_answer_is_traced_without_values_and_values_require_availability(db_session):
    saved = save_prediction(db_session, answer(status="unavailable", match_id=900_002), dt.date(2026, 10, 24))
    assert saved.prediction.lambda_home is None and saved.prediction.reasons
    bad = answer(status="unavailable", match_id=900_003)
    bad["prediction"] = answer()["prediction"]  # des valeurs pour un match indisponible : refusé par la base
    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError):
        save_prediction(db_session, bad | {"status": "unavailable"}, dt.date(2026, 10, 24))
    savepoint.rollback()


def test_registry_keeps_a_single_active_model(db_session):
    register_model(db_session, "m-a", {"horizon": "H1"}, "models/m-a", activate=True)
    register_model(db_session, "m-b", {"horizon": "H1"}, "models/m-b", activate=True)
    assert active_version(db_session) == "m-b"
    actives = db_session.execute(
        select(func.count()).select_from(ModelRegistry).where(ModelRegistry.active)
    ).scalar_one()
    assert actives == 1
    register_model(db_session, "m-a", {"horizon": "H1", "maj": True}, "models/m-a")  # réinscription : mise à jour
    assert db_session.get(ModelRegistry, "m-a").card["maj"] is True
