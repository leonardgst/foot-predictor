"""Tests de la composante Potentiel du MVS
(`market_value/components/potential.py`) : courbe âge -> score, cas
limites, propriétés de monotonie (la courbe exacte est un choix "à dire
d'expert" amené à être retouché -- les tests de monotonie survivent à un
retuning des constantes, contrairement à des valeurs figées)."""
from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.market_value.components.potential import (
    DECLINE_AGE_ANCHOR,
    MAX_SCORE,
    MIN_SCORE,
    PEAK_AGE_END,
    PEAK_AGE_START,
    PEAK_SCORE,
    YOUNG_AGE_ANCHOR,
    compute_potential_score,
)

AS_OF = dt.date(2024, 1, 1)


def _birth_date_for_age(age_years: float) -> dt.date:
    """Renvoie une date de naissance telle que l'âge à AS_OF soit ~age_years."""
    days = round(age_years * 365.25)
    return AS_OF - dt.timedelta(days=days)


def test_very_young_player_gets_max_score():
    # En dessous de l'ancrage jeune, le score est plafonné à MAX_SCORE :
    # marge de progression maximale.
    birth_date = _birth_date_for_age(YOUNG_AGE_ANCHOR - 1)

    score = compute_potential_score(birth_date, AS_OF)

    assert score == pytest.approx(MAX_SCORE)


def test_player_in_peak_window_gets_peak_score():
    # Au milieu du plateau de pic (26-27 ans), le score doit être le score
    # de pic (plateau, pas de décroissance à l'intérieur de la fenêtre).
    peak_mid_age = (PEAK_AGE_START + PEAK_AGE_END) / 2
    birth_date = _birth_date_for_age(peak_mid_age)

    score = compute_potential_score(birth_date, AS_OF)

    assert score == pytest.approx(PEAK_SCORE)


def test_player_past_decline_anchor_gets_min_score():
    # Au-delà de l'ancrage de déclin, le score plancher est MIN_SCORE :
    # potentiel de progression de valeur considéré comme nul.
    birth_date = _birth_date_for_age(DECLINE_AGE_ANCHOR + 5)

    score = compute_potential_score(birth_date, AS_OF)

    assert score == pytest.approx(MIN_SCORE)


def test_score_strictly_decreases_with_age_past_the_peak():
    # Propriété centrale : passé le pic (27 ans), plus un joueur est âgé,
    # moins il a de marge de progression -- décroissance stricte jusqu'à
    # l'ancrage de déclin.
    ages = [PEAK_AGE_END, PEAK_AGE_END + 1, PEAK_AGE_END + 2, DECLINE_AGE_ANCHOR - 1, DECLINE_AGE_ANCHOR]
    scores = [compute_potential_score(_birth_date_for_age(age), AS_OF) for age in ages]

    for earlier, later in zip(scores, scores[1:]):
        assert later < earlier


def test_score_strictly_decreases_with_age_before_the_peak():
    # Avant le pic, plus un joueur se rapproche de sa fenêtre de pic, plus
    # sa marge de progression restante se réduit -- décroissance stricte
    # entre l'ancrage jeune et le début du plateau de pic.
    ages = [YOUNG_AGE_ANCHOR, YOUNG_AGE_ANCHOR + 2, YOUNG_AGE_ANCHOR + 4, PEAK_AGE_START]
    scores = [compute_potential_score(_birth_date_for_age(age), AS_OF) for age in ages]

    for earlier, later in zip(scores, scores[1:]):
        assert later < earlier


def test_score_never_negative_and_never_above_max():
    # Le score doit toujours rester dans l'échelle 0-100 du MVS, quel que
    # soit l'âge (même extrême).
    for age in [0, YOUNG_AGE_ANCHOR, PEAK_AGE_START, PEAK_AGE_END, DECLINE_AGE_ANCHOR, 45]:
        score = compute_potential_score(_birth_date_for_age(age), AS_OF)
        assert MIN_SCORE <= score <= MAX_SCORE


def test_as_of_date_before_birth_date_raises_value_error():
    # Donnée invalide (date de naissance dans le futur par rapport à
    # as_of_date) : on refuse plutôt que de renvoyer un score fantaisiste.
    birth_date = dt.date(2020, 1, 1)
    as_of_date = dt.date(2019, 1, 1)

    with pytest.raises(ValueError):
        compute_potential_score(birth_date, as_of_date)


def test_as_of_date_equal_birth_date_is_valid_newborn_case():
    # Cas limite : naissance le jour même de as_of_date -> âge 0, doit
    # rester valide (pas d'erreur) et renvoyer le score maximal.
    birth_date = dt.date(2024, 1, 1)

    score = compute_potential_score(birth_date, birth_date)

    assert score == pytest.approx(MAX_SCORE)
