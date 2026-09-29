"""Calendrier (G3) et huis clos (G0). Sans base."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.features import huis_clos
from foot_predictor.features.rest import compute_rest

LEAGUE, CUP, EUROPE = 39, 45, 2  # Premier League, FA Cup, Ligue des champions


def match(mid, day, home, away, league=LEAGUE, season=2018, status="played"):
    return {
        "match_id": mid,
        "match_day": dt.date.fromisoformat(day),
        "api_league_id": league,
        "season_year": season,
        "home_team_id": home,
        "away_team_id": away,
        "status": status,
    }


def row(result, match_id, team):
    return result[(result["match_id"] == match_id) & (result["team_id"] == team)].iloc[0]


def test_rest_days_count_every_competition():
    rows = [
        match(1, "2018-09-01", 1, 2),
        match(2, "2018-09-05", 1, 3, league=CUP),
        match(3, "2018-09-08", 1, 2),
    ]
    result = compute_rest(pd.DataFrame(rows))
    assert row(result, 3, 1)["rest_days"] == 3  # le match de coupe compte
    assert row(result, 3, 2)["rest_days"] == 7
    assert row(result, 3, 1)["matches_last_14d"] == 2


def test_without_cups_only_league_matches_count():
    rows = [match(1, "2018-09-01", 1, 2), match(3, "2018-09-08", 1, 2)]
    assert row(compute_rest(pd.DataFrame(rows)), 3, 1)["rest_days"] == 7


def test_european_match_in_the_previous_four_days():
    rows = [
        match(1, "2018-09-18", 1, 9, league=EUROPE),
        match(2, "2018-09-22", 1, 2),  # J − 4 : compte
        match(3, "2018-09-27", 1, 2),  # J − 9 : ne compte pas
    ]
    result = compute_rest(pd.DataFrame(rows))
    assert bool(row(result, 2, 1)["european_match_last_4d"]) is True
    assert bool(row(result, 3, 1)["european_match_last_4d"]) is False
    assert bool(row(result, 2, 2)["european_match_last_4d"]) is False


def test_the_next_match_is_never_used():
    """Ajouter un match après J ne change rien aux lignes du jour J."""
    base = [match(1, "2018-09-01", 1, 2), match(2, "2018-09-08", 1, 2)]
    before = compute_rest(pd.DataFrame(base))
    after = compute_rest(pd.DataFrame([*base, match(3, "2018-09-09", 1, 3, league=CUP)]))
    pd.testing.assert_series_equal(row(before, 2, 1), row(after, 2, 1), check_names=False)


def test_same_day_matches_and_unplayed_matches_do_not_count():
    rows = [
        match(1, "2018-09-08", 1, 3, league=CUP),  # même jour
        match(2, "2018-09-05", 1, 4, league=CUP, status="postponed"),  # non joué
        match(3, "2018-09-08", 1, 2),
    ]
    target = row(compute_rest(pd.DataFrame(rows)), 3, 1)
    assert np.isnan(target["rest_days"]) and target["matches_last_14d"] == 0


def test_reliability_flag_before_the_first_reliable_season():
    rows = [match(1, "2014-09-01", 1, 2, season=2014), match(2, "2015-09-01", 1, 2, season=2015)]
    result = compute_rest(pd.DataFrame(rows))
    assert not row(result, 1, 1)["rest_reliable"]
    assert row(result, 2, 1)["rest_reliable"]
    spain = compute_rest(pd.DataFrame([match(3, "2017-09-01", 5, 6, league=140, season=2017)]))
    assert not row(spain, 3, 5)["rest_reliable"]  # Copa del Rey absente avant 2018-19


def test_behind_closed_doors_periods():
    periods = huis_clos.load_periods()
    leagues = [39, 39, 40, 61, 61]
    days = ["2020-06-20", "2020-12-10", "2020-09-19", "2020-09-15", "2021-02-01"]
    assert list(huis_clos.behind_closed_doors(leagues, days, periods)) == [1, 0, 0, 0, 1]
    # 2020-12-10 : période incertaine (paliers) ; 2020-09-19 : jour des matchs pilotes du Championship,
    # incertain, qui l'emporte sur la période sûre ; 2020-09-15 : jauge réduite en France.


def test_every_period_cites_a_source_and_is_ordered():
    for period in huis_clos.load_periods():
        assert period.start <= period.end and period.source


def test_invalid_yaml_is_refused(tmp_path):
    path = tmp_path / "hc.yaml"
    path.write_text(
        "sources: {s: https://exemple}\nperiods:\n  - {leagues: [39], start: 2020-05-01, end: 2020-04-01, "
        "status: huis_clos, source: s}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        huis_clos.load_periods(path)
