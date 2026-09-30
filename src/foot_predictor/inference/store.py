"""Traçabilité des prédictions et registre des modèles (décision 7 de la partie 5, ADR-0040 ; migration 0008).

- `save_prediction` écrit une réponse de `predict` dans `ops.prediction`. **Idempotente** : une
  prédiction existe déjà pour (match, version du modèle, horizon, mode) ⇒ elle est renvoyée telle
  quelle, sauf avec `force` (une nouvelle ligne s'ajoute, l'ancienne reste : rien ne s'efface).
- **Live** : une prédiction n'est écrite qu'**avant le coup d'envoi** (heure connue) ou, sans heure,
  avant le début du jour du match (00:00 UTC) ; sinon, refus explicite. C'est ce qui fait du journal
  `live` une évaluation prospective honnête (ADR-0011, règle 6).
- `register_model` inscrit un modèle (carte, chemin) dans `ops.model_registry` ; `activate` en fait
  le modèle actif (un seul à la fois, garanti par un index unique partiel).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from foot_predictor.db.models import ModelRegistry, Prediction
from foot_predictor.inference.availability import AVAILABLE


class LivePredictionTooLate(RuntimeError):
    """Prédiction live demandée après le coup d'envoi (ou après le début du jour sans heure connue)."""


@dataclass
class Saved:
    prediction: Prediction
    created: bool


def live_deadline(answer: dict) -> dt.datetime:
    """Heure limite d'écriture d'une prédiction live : le coup d'envoi, sinon 00:00 UTC du jour du match."""
    if answer.get("kickoff_utc"):
        return pd.Timestamp(answer["kickoff_utc"]).to_pydatetime()
    day = dt.date.fromisoformat(answer["date"])
    return dt.datetime.combine(day, dt.time(0, 0), tzinfo=dt.UTC)


def existing(session: Session, answer: dict) -> Prediction | None:
    query = (
        select(Prediction)
        .where(
            Prediction.match_id == answer["match_id"],
            Prediction.model_version == answer["model_version"],
            Prediction.horizon == answer["horizon"],
            Prediction.mode == answer["mode"],
        )
        .order_by(Prediction.created_at.desc(), Prediction.id.desc())
    )
    return session.execute(query).scalars().first()


def save_prediction(
    session: Session,
    answer: dict,
    reference_date: dt.date,
    *,
    force: bool = False,
    now: dt.datetime | None = None,
    api_fixture_id: int | None = None,
) -> Saved:
    """Écrit (ou renvoie) la prédiction d'une réponse de `predict_match` ; ne valide pas la transaction."""
    now = now or dt.datetime.now(dt.UTC)
    if answer["mode"] == "live" and now >= live_deadline(answer):
        raise LivePredictionTooLate(
            f"Match {answer['match_id']} : prédiction live refusée après {live_deadline(answer).isoformat()} "
            "(coup d'envoi, ou début du jour sans heure connue)."
        )
    if not force:
        found = existing(session, answer)
        if found is not None:
            return Saved(found, created=False)
    prediction = answer.get("prediction") or {}
    interval = prediction.get("interval") or {}
    variables = answer.get("availability") or []
    row = Prediction(
        match_id=answer["match_id"],
        api_fixture_id=api_fixture_id,
        competition_id=answer.get("competition_id"),
        home_team_id=answer.get("home_team_id"),
        away_team_id=answer.get("away_team_id"),
        kickoff_utc=pd.Timestamp(answer["kickoff_utc"]).to_pydatetime() if answer.get("kickoff_utc") else None,
        match_day=dt.date.fromisoformat(answer["date"]),
        model_version=answer["model_version"],
        horizon=answer["horizon"],
        mode=answer["mode"],
        reference_date=reference_date,
        created_at=now,
        status=answer["status"],
        reasons=answer.get("reasons") or [],
        lambda_home=prediction.get("lambda_home"),
        lambda_away=prediction.get("lambda_away"),
        expected_total=prediction.get("expected_total"),
        total_distribution=prediction.get("total_distribution") if answer["status"] == AVAILABLE else None,
        p_over_2_5=prediction.get("p_over_2_5"),
        interval_low=interval.get("low"),
        interval_high=interval.get("high"),
        announced_coverage=interval.get("announced_coverage"),
        variables_used=[v for v in variables if v["status"] == "presente"],
        variables_not_present=[v for v in variables if v["status"] != "presente"],
        data_version=answer["data_version"],
        data_complete_until=dt.date.fromisoformat(answer["data_complete_until"]) if answer.get("data_complete_until") else None,
    )  # fmt: skip
    session.add(row)
    session.flush()
    return Saved(row, created=True)


def register_model(session: Session, version: str, card: dict, path: str, *, activate: bool = False) -> ModelRegistry:
    """Inscrit un modèle (idempotent : une version déjà inscrite est mise à jour) ; `activate` le rend actif."""
    entry = session.get(ModelRegistry, version)
    if entry is None:
        entry = ModelRegistry(version=version, horizon=card.get("horizon", "H1"), card=card, path=path, active=False)
        session.add(entry)
    else:
        entry.card, entry.path = card, path
    session.flush()
    if activate:
        session.execute(update(ModelRegistry).where(ModelRegistry.version != version).values(active=False))
        session.flush()
        entry.active = True
        session.flush()
    return entry


def active_version(session: Session) -> str | None:
    return session.execute(select(ModelRegistry.version).where(ModelRegistry.active)).scalar_one_or_none()
