"""
Orchestration complète de l'étape Performance du MVS, pour un `as_of_date`
donné : chargement -> per90 -> normalisation -> clustering -> percentiles ->
score -> écriture en base.

Usage :
    python -m foot_predictor.market_value.run_performance_pipeline
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from foot_predictor.market_value.clustering.build_clusters import fit_clusters
from foot_predictor.market_value.data.load_player_match_stats import (
    load_player_match_stats_window,
)
from foot_predictor.market_value.performance.percentiles import compute_percentiles
from foot_predictor.market_value.performance.performance_score import compute_performance_score
from foot_predictor.market_value.persistence.save_results import (
    save_performance_scores,
    save_style_profiles,
)
from foot_predictor.market_value.preprocessing.normalize import (
    STYLE_FEATURE_COLUMNS,
    normalize_style_vectors,
)
from foot_predictor.market_value.preprocessing.per90 import (
    apply_minimum_sample_filter,
    build_player_vectors,
)

POSITION_BUCKETS = ["Defender", "Midfielder", "Attacker"]


def run_for_position_bucket(session: Session, position_bucket: str, as_of_date: dt.date) -> dict:
    raw = load_player_match_stats_window(session, position_bucket, as_of_date)
    if raw.empty:
        return {"position_bucket": position_bucket, "status": "no_data"}

    vectors = build_player_vectors(raw)
    eligible = apply_minimum_sample_filter(vectors)
    if eligible.empty:
        return {"position_bucket": position_bucket, "status": "no_eligible_players"}

    X_scaled, _scaler, feature_columns = normalize_style_vectors(eligible)

    try:
        cluster_ids, meta, _model = fit_clusters(X_scaled)
    except ValueError as exc:
        return {"position_bucket": position_bucket, "status": "clustering_skipped", "reason": str(exc)}

    # Nommage des clusters : PAS automatique (cf. recap, étape 4). En
    # attendant l'observation manuelle, on utilise l'id numérique comme label
    # temporaire -- à remplacer par un vrai mapping id -> nom métier une fois
    # les clusters observés sur les vraies données.
    cluster_labels = cluster_ids.astype(str)

    percentiles = compute_percentiles(eligible, cluster_ids, feature_columns)
    scores = compute_performance_score(percentiles, cluster_labels)

    save_style_profiles(
        session,
        position_bucket,
        as_of_date,
        cluster_ids,
        cluster_labels,
        eligible["matches_in_window"],
    )
    save_performance_scores(session, as_of_date, scores)

    return {
        "position_bucket": position_bucket,
        "status": "ok",
        "n_players_scored": int(scores.notna().sum()),
        "clustering_meta": meta,
    }


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    AS_OF_DATE = dt.date.today()

    with get_session() as session:
        for bucket in POSITION_BUCKETS:
            result = run_for_position_bucket(session, bucket, AS_OF_DATE)
            print(result)
        session.commit()
