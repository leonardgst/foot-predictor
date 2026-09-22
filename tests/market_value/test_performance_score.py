"""Tests du score Performance = somme pondérée des percentiles
(`market_value/performance/performance_score.py`) : calcul numérique sur un
exemple calculable à la main, et les deux cas `None` explicites du code
(aucune statistique disponible / somme des poids nulle)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foot_predictor.market_value.performance import weights as weights_module
from foot_predictor.market_value.performance.performance_score import compute_performance_score


def test_weighted_sum_matches_hand_computed_example(monkeypatch):
    monkeypatch.setitem(
        weights_module.CLUSTER_WEIGHTS, "cluster_x", {"a_pctl": 0.7, "b_pctl": 0.3}
    )
    percentiles = pd.DataFrame({"a_pctl": [80.0], "b_pctl": [60.0]}, index=pd.Index([1], name="player_id"))
    cluster_labels = pd.Series({1: "cluster_x"})

    scores = compute_performance_score(percentiles, cluster_labels)

    # 80*0.7 + 60*0.3 = 56 + 18 = 74.0
    assert scores.loc[1] == pytest.approx(74.0)


def test_unknown_cluster_uses_uniform_weights_and_renormalizes_over_available_stats():
    """Cluster non configuré -> poids uniforme sur les 3 colonnes déclarées,
    mais une seule stat manquante (NaN) est exclue du numérateur ET du
    dénominateur (renormalisation sur les stats disponibles)."""
    percentiles = pd.DataFrame(
        {"a_pctl": [80.0], "b_pctl": [60.0], "c_pctl": [np.nan]}, index=pd.Index([1], name="player_id")
    )
    cluster_labels = pd.Series({1: "cluster_inconnu"})

    scores = compute_performance_score(percentiles, cluster_labels)

    # poids uniforme = 1/3 chacun ; c_pctl manquant -> total_weight = 2/3
    # score = (80*1/3 + 60*1/3) / (2/3) = (80+60)/2 = 70.0
    assert scores.loc[1] == pytest.approx(70.0)


def test_returns_none_when_no_stats_available_for_player():
    percentiles = pd.DataFrame(
        {"a_pctl": [np.nan], "b_pctl": [np.nan]}, index=pd.Index([1], name="player_id")
    )
    cluster_labels = pd.Series({1: "cluster_x"})

    scores = compute_performance_score(percentiles, cluster_labels)

    assert scores.loc[1] is None


def test_returns_none_when_total_weight_is_zero(monkeypatch):
    """Cas explicite du code : si les poids du cluster pour les colonnes
    disponibles somment à 0 (ex. cluster défini mais toutes ses stats
    disponibles à poids nul), le score est None plutôt qu'une division par
    zéro silencieuse."""
    monkeypatch.setitem(
        weights_module.CLUSTER_WEIGHTS, "cluster_poids_nuls", {"a_pctl": 0.0, "b_pctl": 0.0}
    )
    percentiles = pd.DataFrame({"a_pctl": [80.0], "b_pctl": [60.0]}, index=pd.Index([1], name="player_id"))
    cluster_labels = pd.Series({1: "cluster_poids_nuls"})

    scores = compute_performance_score(percentiles, cluster_labels)

    assert scores.loc[1] is None


def test_multiple_players_are_scored_independently():
    percentiles = pd.DataFrame(
        {"a_pctl": [100.0, 0.0], "b_pctl": [100.0, 0.0]}, index=pd.Index([1, 2], name="player_id")
    )
    cluster_labels = pd.Series({1: "cluster_inconnu", 2: "cluster_inconnu"})

    scores = compute_performance_score(percentiles, cluster_labels)

    assert scores.loc[1] == pytest.approx(100.0)
    assert scores.loc[2] == pytest.approx(0.0)
