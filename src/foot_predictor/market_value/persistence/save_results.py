"""
Écriture des résultats du clustering/Performance en base (cf. recap
clustering, section 7).

⚠️ Suppose l'existence de modèles SQLAlchemy `PlayerStyleProfile` et
`PlayerMarketValueScore` dans foot_predictor.db.models, avec les colonnes
listées dans le recap (player_id, as_of_date, position_bucket, cluster_id,
cluster_label, matches_in_window, computed_at / player_id, as_of_date,
performance_score). Le schéma est décrit comme "déjà en place et testé" mais
je n'ai pas les noms de classes exacts -> à adapter si les noms réels
diffèrent (renommer l'import ci-dessous suffit si les colonnes correspondent).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import PlayerMarketValueScore, PlayerStyleProfile


def save_style_profiles(
    session: Session,
    position_bucket: str,
    as_of_date: dt.date,
    cluster_ids: pd.Series,
    cluster_labels: pd.Series,
    matches_in_window: pd.Series,
) -> int:
    """Upsert sur (player_id, as_of_date) -- une ligne par joueur et par date
    de calcul, cohérent avec le reste du projet (pas d'historique de
    versions multiples pour la même date de référence)."""
    processed = 0
    for player_id in cluster_ids.index:
        existing = session.scalar(
            select(PlayerStyleProfile).where(
                PlayerStyleProfile.player_id == player_id,
                PlayerStyleProfile.as_of_date == as_of_date,
            )
        )
        values = dict(
            position_bucket=position_bucket,
            cluster_id=int(cluster_ids.loc[player_id]),
            cluster_label=cluster_labels.get(player_id),
            matches_in_window=int(matches_in_window.loc[player_id]),
            computed_at=dt.datetime.utcnow(),
        )
        if existing is not None:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            session.add(PlayerStyleProfile(player_id=player_id, as_of_date=as_of_date, **values))
        processed += 1

    session.flush()
    return processed


def save_performance_scores(session: Session, as_of_date: dt.date, scores: pd.Series) -> int:
    """Met à jour uniquement performance_score -- les autres composantes du
    MVS (potential_score, reputation_score, etc.) sont hors périmètre de ce
    module et traitées ailleurs."""
    processed = 0
    for player_id, score in scores.items():
        if score is None:
            continue
        existing = session.scalar(
            select(PlayerMarketValueScore).where(
                PlayerMarketValueScore.player_id == player_id,
                PlayerMarketValueScore.as_of_date == as_of_date,
            )
        )
        if existing is not None:
            existing.performance_score = score
        else:
            session.add(
                PlayerMarketValueScore(
                    player_id=player_id, as_of_date=as_of_date, performance_score=score
                )
            )
        processed += 1

    session.flush()
    return processed
