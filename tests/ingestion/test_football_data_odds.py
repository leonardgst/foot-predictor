"""Cotes plus/moins 2,5 de football-data : ordre de priorité, cotes illisibles, marge retirée (ADR-0036)."""

from __future__ import annotations

import pytest

from foot_predictor.ingestion.football_data_odds import (
    AVANT_CLOTURE,
    CLOTURE,
    implied_probability_over,
    odds_value,
    select_odds,
)


def test_market_average_comes_first():
    row = {"Avg>2.5": "1.90", "Avg<2.5": "1.95", "B365>2.5": "1.8", "B365<2.5": "2.0"}
    odds = select_odds(row, AVANT_CLOTURE)
    assert (odds.over, odds.under, odds.column, odds.n_odds) == (1.90, 1.95, "Avg", None)


def test_betbrain_aggregate_carries_its_number_of_odds():
    row = {"BbAv>2.5": "2.10", "BbAv<2.5": "1.72", "BbOU": "37", "BbMx>2.5": "2.30", "BbMx<2.5": "1.80"}
    odds = select_odds(row, AVANT_CLOTURE)
    assert (odds.column, odds.n_odds) == ("BbAv", 37)


def test_one_bookmaker_when_no_average_counts_one():
    row = {"Avg>2.5": "", "Avg<2.5": "1.9", "B365>2.5": "1.8", "B365<2.5": "2.0", "GB>2.5": "1.7", "GB<2.5": "2.1"}
    odds = select_odds(row, AVANT_CLOTURE)
    assert (odds.column, odds.n_odds) == ("B365", 1)  # moyenne incomplète : colonne suivante


def test_maximum_columns_are_never_used():
    assert select_odds({"Max>2.5": "2.0", "Max<2.5": "2.0", "BbMx>2.5": "2", "BbMx<2.5": "2"}, AVANT_CLOTURE) is None


def test_closing_odds_only_from_c_columns():
    row = {"Avg>2.5": "1.90", "Avg<2.5": "1.95", "AvgC>2.5": "1.85", "AvgC<2.5": "2.00"}
    assert select_odds(row, CLOTURE).column == "AvgC"
    assert select_odds({"Avg>2.5": "1.90", "Avg<2.5": "1.95"}, CLOTURE) is None  # jamais de clôture inventée


@pytest.mark.parametrize("value", [None, "", "abc", "1", "0.95", "-2"])
def test_unreadable_or_impossible_odds_are_absent(value):
    assert odds_value(value) is None


def test_no_odds_at_all_gives_none():
    assert select_odds({"Div": "E0", "FTHG": "1"}, AVANT_CLOTURE) is None


def test_margin_is_removed_by_proportional_normalisation():
    # Cotes justes (sans marge) : 2,0 et 2,0 -> 0,5 ; avec marge, la somme des inverses dépasse 1.
    assert implied_probability_over(2.0, 2.0) == pytest.approx(0.5)
    p = implied_probability_over(1.80, 2.00)
    assert p == pytest.approx((1 / 1.8) / (1 / 1.8 + 1 / 2.0))
    assert 1 / 1.8 + 1 / 2.0 > 1  # la marge existe bien avant normalisation
