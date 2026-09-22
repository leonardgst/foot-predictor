"""Tests du calcul per-90 minutes (`market_value/preprocessing/per90.py`) :
calcul, exclusion des lignes à faible temps de jeu, garde-fou d'échantillon
minimum.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foot_predictor.market_value.preprocessing.per90 import (
    MIN_MATCHES_IN_WINDOW,
    MIN_MINUTES_PER_MATCH,
    apply_minimum_sample_filter,
    build_player_vectors,
)


def _row(player_id, minutes, **stats):
    base = {
        "player_id": player_id,
        "minutes": minutes,
        "goals": 0, "assists": 0, "shots": 0, "shots_on_target": 0, "key_passes": 0,
        "tackles": 0, "interceptions": 0, "dribbles_attempts": 0, "dribbles_success": 0,
        "dribbled_past": 0, "fouls_drawn": 0, "fouls_committed": 0,
        "duels_won": 0, "duels_total": 0, "pass_accuracy_pct": 80.0,
        "xg": None, "xa": None, "npxg": None,
    }
    base.update(stats)
    return base


def test_build_player_vectors_empty_input_returns_empty_dataframe():
    result = build_player_vectors(pd.DataFrame())
    assert result.empty


def test_goals_per90_scales_by_90_minutes_over_sum_of_minutes():
    df = pd.DataFrame([
        _row(1, 45, goals=1),
        _row(1, 45, goals=1),
    ])

    vectors = build_player_vectors(df)

    # 2 buts sur 90 minutes cumulées -> 2 buts / 90min = 2.0 per90
    assert vectors.loc[1, "goals_per90"] == pytest.approx(2.0)


def test_rows_below_min_minutes_are_excluded_from_aggregation():
    df = pd.DataFrame([
        _row(1, MIN_MINUTES_PER_MATCH - 1, goals=10),  # exclue du calcul per90
        _row(1, 90, goals=1),
    ])

    vectors = build_player_vectors(df)

    # Seule la ligne à 90 minutes doit compter : 1 but / 90min = 1.0 per90,
    # pas de contamination par la ligne à faible temps de jeu (10 buts).
    assert vectors.loc[1, "goals_per90"] == pytest.approx(1.0)


def test_matches_in_window_counts_all_rows_including_low_minutes():
    """matches_in_window doit compter TOUS les matchs de la fenêtre, y
    compris ceux en dessous du seuil minutes, pour appliquer le garde-fou
    d'échantillon minimum sur le volume réel disponible."""
    df = pd.DataFrame([
        _row(1, 5, goals=0),  # sous le seuil minutes, mais compte quand même
        _row(1, 90, goals=1),
    ])

    vectors = build_player_vectors(df)

    assert vectors.loc[1, "matches_in_window"] == 2


def test_duels_won_pct_ratio_computed_from_totals():
    df = pd.DataFrame([
        _row(1, 90, duels_won=6, duels_total=10),
        _row(1, 90, duels_won=2, duels_total=10),
    ])

    vectors = build_player_vectors(df)

    assert vectors.loc[1, "duels_won_pct"] == pytest.approx(0.4)


def test_xg_stat_excludes_null_rows_without_treating_as_zero():
    """Une ligne avec xg=NULL doit être exclue du calcul per90 du xG (pas
    comptée comme 0), et xg_coverage doit refléter la proportion couverte."""
    df = pd.DataFrame([
        _row(1, 90, xg=1.8),
        _row(1, 90, xg=None),
    ])

    vectors = build_player_vectors(df)

    assert vectors.loc[1, "xg_coverage"] == pytest.approx(0.5)
    # Seule la ligne avec xg renseigné compte : 1.8 sur 90 minutes -> 1.8 per90
    assert vectors.loc[1, "xg_per90"] == pytest.approx(1.8)


def test_xg_stat_all_null_yields_nan_per90_and_zero_coverage():
    df = pd.DataFrame([_row(1, 90, xg=None)])

    vectors = build_player_vectors(df)

    assert vectors.loc[1, "xg_coverage"] == 0.0
    assert np.isnan(vectors.loc[1, "xg_per90"])


def test_input_with_no_eligible_rows_returns_empty_dataframe():
    """Si AUCUNE ligne de l'entrée n'atteint MIN_MINUTES_PER_MATCH, `eligible`
    est vide : build_player_vectors doit renvoyer un DataFrame vide plutôt que
    lever un KeyError. Scénario plausible en tout début de saison sur un
    groupe de poste peu fourni."""
    df = pd.DataFrame([_row(1, MIN_MINUTES_PER_MATCH - 1, goals=5)])

    result = build_player_vectors(df)

    assert result.empty


def test_apply_minimum_sample_filter_removes_players_below_threshold():
    vectors = pd.DataFrame(
        {"matches_in_window": [MIN_MATCHES_IN_WINDOW - 1, MIN_MATCHES_IN_WINDOW, MIN_MATCHES_IN_WINDOW + 5]},
        index=pd.Index([1, 2, 3], name="player_id"),
    )

    filtered = apply_minimum_sample_filter(vectors)

    assert list(filtered.index) == [2, 3]


def test_apply_minimum_sample_filter_empty_input_returns_empty():
    result = apply_minimum_sample_filter(pd.DataFrame())
    assert result.empty
