"""Service d'inférence : pour un match à venir, construit sa ligne de
features (`live_features.py`), applique le Modèle A persisté
(`persistence.py`) et renvoie lambda_home/away, la distribution jointe du
score exact et le 1N2 dérivé.

C'est la pièce qui manque entre "modèle entraîné" (`modeling/run_comparison.py`)
et le produit visé (bouton « Prédire », cf. README) : ce module est ce que
l'API / la couche produit appellera plus tard pour un match donné.

Convention reprise de `dataset.py` : deux blocs own_*/opp_* par observation,
`is_home` et un one-hot championnat (`comp_<nom>`). `PoissonModel.predict_lambda`
réaligne déjà sur les colonnes vues à l'entraînement (`reindex(..., fill_value=0.0)`),
donc une modalité de championnat absente ou égale à la référence absorbée à
l'entraînement est correctement traitée comme "toutes les dummies à 0" sans
qu'on ait besoin de connaître explicitement quelle modalité était la
référence.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import Competition, Match
from foot_predictor.modeling.evaluation import MAX_GOALS, independent_poisson_matrix, outcome_probabilities
from foot_predictor.modeling.live_features import compute_live_z_features
from foot_predictor.modeling.persistence import DEFAULT_MODEL_PATH, PersistedPoissonModel, load_model


class InsufficientFeatureHistoryError(ValueError):
    """Levée quand une des deux équipes n'a pas assez d'historique pour
    calculer une des features z1-z8 (ex. tout début de saison, équipe
    promue) -- le modèle n'a jamais été entraîné sur de telles lignes
    (`dataset.py` les écarte via `dropna`), donc prédire dessus produirait un
    résultat non fiable plutôt qu'une simple imprécision."""


@dataclass(frozen=True)
class ExactScorePrediction:
    home_team_id: int
    away_team_id: int
    match_date: dt.datetime
    competition_id: int
    lambda_home: float
    lambda_away: float
    score_matrix: np.ndarray
    """P(buts_domicile=a, buts_extérieur=b), a/b en ligne/colonne, 0..MAX_GOALS."""
    most_likely_score: tuple[int, int]
    p_home_win: float
    p_draw: float
    p_away_win: float


def _build_observation_row(
    *,
    own: dict[str, float | int | None],
    opp: dict[str, float | int | None],
    is_home: bool,
    competition_name: str,
    feature_columns: list[str],
) -> dict[str, float]:
    row: dict[str, float] = {f"own_{c}": float(own[c]) for c in feature_columns}
    row.update({f"opp_{c}": float(opp[c]) for c in feature_columns})
    row["is_home"] = 1.0 if is_home else 0.0
    row[f"comp_{competition_name}"] = 1.0
    return row


def predict_match(
    session: Session,
    *,
    home_team_id: int,
    away_team_id: int,
    match_date: dt.datetime,
    competition_id: int,
    season_id: int,
    persisted_model: PersistedPoissonModel | None = None,
) -> ExactScorePrediction:
    """Prédit le score exact d'un match à venir (pas encore en base, ou en
    base avec `status='scheduled'`) à partir des identifiants d'équipes,
    d'une date et d'une compétition/saison. `match_date` sert d'ancrage
    `before_date` pour toutes les features glissantes (anti-fuite : mêmes
    fonctions que le pipeline d'entraînement)."""
    if persisted_model is None:
        persisted_model = load_model(DEFAULT_MODEL_PATH)

    feature_columns = persisted_model.z_feature_columns

    competition = session.get(Competition, competition_id)
    if competition is None:
        raise ValueError(f"Compétition introuvable : competition_id={competition_id}")

    own_home = compute_live_z_features(
        session,
        team_id=home_team_id,
        is_home=True,
        before_date=match_date,
        competition_id=competition_id,
        season_id=season_id,
        feature_columns=feature_columns,
    )
    own_away = compute_live_z_features(
        session,
        team_id=away_team_id,
        is_home=False,
        before_date=match_date,
        competition_id=competition_id,
        season_id=season_id,
        feature_columns=feature_columns,
    )

    missing_home = [c for c in feature_columns if own_home[c] is None]
    missing_away = [c for c in feature_columns if own_away[c] is None]
    if missing_home or missing_away:
        raise InsufficientFeatureHistoryError(
            "Historique insuffisant pour prédire ce match : "
            f"équipe domicile (team_id={home_team_id}) manque {missing_home}, "
            f"équipe extérieur (team_id={away_team_id}) manque {missing_away}."
        )

    home_row = _build_observation_row(
        own=own_home, opp=own_away, is_home=True,
        competition_name=competition.name, feature_columns=feature_columns,
    )
    away_row = _build_observation_row(
        own=own_away, opp=own_home, is_home=False,
        competition_name=competition.name, feature_columns=feature_columns,
    )

    X = pd.DataFrame([home_row, away_row])
    lambda_home, lambda_away = persisted_model.model.predict_lambda(X)

    matrix = independent_poisson_matrix(float(lambda_home), float(lambda_away), max_goals=MAX_GOALS)
    most_likely_flat = int(np.argmax(matrix))
    most_likely_score = (most_likely_flat // matrix.shape[1], most_likely_flat % matrix.shape[1])
    p_home_win, p_draw, p_away_win = outcome_probabilities(matrix)

    return ExactScorePrediction(
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        match_date=match_date,
        competition_id=competition_id,
        lambda_home=float(lambda_home),
        lambda_away=float(lambda_away),
        score_matrix=matrix,
        most_likely_score=most_likely_score,
        p_home_win=p_home_win,
        p_draw=p_draw,
        p_away_win=p_away_win,
    )


def predict_scheduled_match(
    session: Session,
    match_id: int,
    persisted_model: PersistedPoissonModel | None = None,
) -> ExactScorePrediction:
    """Variante pratique pour un match déjà en base
    (`staging.match.status = 'scheduled'`) : récupère équipes/date/compétition
    /saison directement depuis la ligne, puis délègue à `predict_match`."""
    match = session.scalar(select(Match).where(Match.id == match_id))
    if match is None:
        raise ValueError(f"Match introuvable : match_id={match_id}")
    if match.status != "scheduled":
        raise ValueError(
            f"predict_scheduled_match attend un match 'scheduled', "
            f"match_id={match_id} a le statut '{match.status}'"
        )

    return predict_match(
        session,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        match_date=match.match_date,
        competition_id=match.competition_id,
        season_id=match.season_id,
        persisted_model=persisted_model,
    )
