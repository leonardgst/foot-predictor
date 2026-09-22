"""Tests du lookup de pondérations par cluster (`market_value/performance/weights.py`) :
fallback uniforme explicite pour un cluster inconnu/pas encore nommé (cf.
docstring du module : `CLUSTER_WEIGHTS` est vide tant que les clusters réels
n'ont pas été observés), et lookup direct pour un cluster connu."""
from __future__ import annotations

import pytest

from foot_predictor.market_value.performance import weights as weights_module
from foot_predictor.market_value.performance.weights import get_weights_for_cluster


def test_unknown_cluster_falls_back_to_uniform_weights():
    result = get_weights_for_cluster("cluster_pas_encore_nomme", ["a_pctl", "b_pctl", "c_pctl"])

    assert result == {"a_pctl": pytest.approx(1 / 3), "b_pctl": pytest.approx(1 / 3), "c_pctl": pytest.approx(1 / 3)}


def test_unknown_cluster_with_empty_feature_columns_returns_empty_dict():
    """`uniform_weight` vaut 0.0 pour éviter une division par zéro, mais le
    dict renvoyé reste vide puisqu'il est construit à partir de
    `feature_columns` (aucune colonne à pondérer)."""
    result = get_weights_for_cluster("cluster_x", [])

    assert result == {}


def test_known_cluster_returns_the_configured_weights_verbatim(monkeypatch):
    monkeypatch.setitem(
        weights_module.CLUSTER_WEIGHTS,
        "attacker_0_finisseur",
        {"goals_per90_pctl": 0.6, "xg_per90_pctl": 0.4},
    )

    result = get_weights_for_cluster("attacker_0_finisseur", ["goals_per90_pctl", "xg_per90_pctl"])

    assert result == {"goals_per90_pctl": 0.6, "xg_per90_pctl": 0.4}


def test_known_cluster_weights_are_returned_even_if_feature_columns_argument_differs(monkeypatch):
    """Le lookup par cluster connu ignore `feature_columns` : il renvoie le
    dict configuré tel quel (pas de filtrage), contrairement au fallback
    uniforme qui, lui, est construit à partir de `feature_columns`."""
    monkeypatch.setitem(weights_module.CLUSTER_WEIGHTS, "midfielder_2_relayeur", {"tackles_per90_pctl": 1.0})

    result = get_weights_for_cluster("midfielder_2_relayeur", ["some_other_column"])

    assert result == {"tackles_per90_pctl": 1.0}
