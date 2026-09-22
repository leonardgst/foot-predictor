"""Tests de la composante Réputation du MVS
(`market_value/components/reputation.py`) : mapping position -> score,
validation des entrées, monotonie (cf. test_components_potential.py pour
la même logique de tests de monotonie plutôt que de valeurs figées)."""
from __future__ import annotations

import pytest

from foot_predictor.market_value.components.reputation import compute_reputation_score


def test_first_place_gets_max_score():
    # 1er du classement -> score maximal, quel que soit le nombre d'équipes.
    score = compute_reputation_score(standing_position=1, n_teams_in_competition=20)

    assert score == pytest.approx(100.0)


def test_last_place_gets_min_score():
    # Dernier du classement -> score minimal (0).
    score = compute_reputation_score(standing_position=20, n_teams_in_competition=20)

    assert score == pytest.approx(0.0)


def test_middle_of_table_is_hand_computable():
    # Championnat à 21 équipes (n-1 = 20, valeur ronde) : 11e position ->
    # exactement à mi-tableau -> 100 * (21-11)/20 = 50.0.
    score = compute_reputation_score(standing_position=11, n_teams_in_competition=21)

    assert score == pytest.approx(50.0)


def test_score_strictly_decreases_as_standing_position_worsens():
    # Propriété centrale : plus la position se dégrade (nombre plus grand,
    # plus loin de la 1re place), plus le score de réputation baisse.
    n_teams = 18
    positions = list(range(1, n_teams + 1))
    scores = [compute_reputation_score(p, n_teams) for p in positions]

    for better, worse in zip(scores, scores[1:]):
        assert worse < better


def test_standing_position_below_one_raises_value_error():
    # Position invalide (0 ou négative) : donnée corrompue, on refuse.
    with pytest.raises(ValueError):
        compute_reputation_score(standing_position=0, n_teams_in_competition=20)


def test_standing_position_above_n_teams_raises_value_error():
    # Position au-delà du nombre d'équipes de la compétition : incohérent.
    with pytest.raises(ValueError):
        compute_reputation_score(standing_position=21, n_teams_in_competition=20)


def test_n_teams_zero_raises_value_error():
    # Compétition sans équipe : classement dénué de sens, on refuse plutôt
    # que de renvoyer un score neutre arbitraire (cf. docstring du module).
    with pytest.raises(ValueError):
        compute_reputation_score(standing_position=1, n_teams_in_competition=0)


def test_n_teams_one_raises_value_error():
    # Compétition à une seule équipe : division par zéro évitée
    # explicitement, on refuse plutôt que de masquer le problème.
    with pytest.raises(ValueError):
        compute_reputation_score(standing_position=1, n_teams_in_competition=1)
