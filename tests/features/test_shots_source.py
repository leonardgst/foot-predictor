"""Source des tirs de l'xg_proxy (ADR-0035) : API depuis 2015-16 si complète, sinon football-data. Sans base."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from foot_predictor.features import xg_proxy
from foot_predictor.features.rolling import compute_rolling

COEF = xg_proxy.XgProxyCoefficients(on_target=0.3, off_target=0.0, n_team_matches=0, seasons="test")


def one(season=2018, api=(12, 5, 9, 3), fd=(10, 4, 8, 2)) -> pd.DataFrame:
    """Un match ; `api` et `fd` : (tirs dom., cadrés dom., tirs ext., cadrés ext.), None pour une valeur absente."""
    return pd.DataFrame(
        [
            {
                "season_year": season,
                "home_shots_api": api[0], "home_sot_api": api[1], "away_shots_api": api[2], "away_sot_api": api[3],
                "home_shots_fd": fd[0], "home_sot_fd": fd[1], "away_shots_fd": fd[2], "away_sot_fd": fd[3],
            }
        ]
    )  # fmt: skip


def values(selected: pd.DataFrame) -> tuple:
    row = selected.iloc[0]
    return tuple(None if pd.isna(row[c]) else int(row[c]) for c in ("home_shots", "home_sot", "away_shots", "away_sot"))


def test_api_is_used_from_2015_16_when_all_four_values_exist():
    selected = xg_proxy.select_shots(one())
    assert values(selected) == (12, 5, 9, 3)
    assert selected.loc[0, "shots_source"] == "api"


def test_incomplete_api_falls_back_to_football_data_for_the_whole_match():
    """Jamais une équipe d'une source et l'autre de l'autre : le choix se fait par match."""
    selected = xg_proxy.select_shots(one(api=(12, 5, 9, None)))
    assert values(selected) == (10, 4, 8, 2)
    assert selected.loc[0, "shots_source"] == "football_data"


def test_api_is_ignored_before_2015_16():
    selected = xg_proxy.select_shots(one(season=2014))
    assert values(selected) == (10, 4, 8, 2)
    assert selected.loc[0, "shots_source"] == "football_data"


def test_no_source_leaves_values_and_source_empty_never_zero():
    selected = xg_proxy.select_shots(one(api=(None,) * 4, fd=(None,) * 4))
    assert values(selected) == (None, None, None, None)
    assert pd.isna(selected.loc[0, "shots_source"])


def test_partial_football_data_is_kept_as_is():
    selected = xg_proxy.select_shots(one(api=(None,) * 4, fd=(10, 4, None, None)))
    assert values(selected) == (10, 4, None, None)
    assert selected.loc[0, "shots_source"] == "football_data"


def test_missing_api_columns_mean_football_data():
    frame = one().drop(columns=["home_shots_api", "home_sot_api", "away_shots_api", "away_sot_api", "season_year"])
    selected = xg_proxy.select_shots(frame)
    assert values(selected) == (10, 4, 8, 2)
    assert selected.loc[0, "shots_source"] == "football_data"


def test_rolling_xg_proxy_reads_the_selected_shots():
    """Le glissant d'une équipe se nourrit des tirs cadrés de l'API quand elle est retenue."""

    def match(mid, day, season, api_sot):
        return {
            "match_id": mid, "match_day": dt.date.fromisoformat(day), "competition_id": 1, "api_league_id": 135,
            "season_year": season, "home_team_id": 1, "away_team_id": 2, "home_goals_90": 1, "away_goals_90": 0,
            "status": "played", "excluded": False,
            "home_shots_api": 10, "home_sot_api": api_sot, "away_shots_api": 10, "away_sot_api": 0,
            "home_shots_fd": 10, "home_sot_fd": 1, "away_shots_fd": 10, "away_sot_fd": 0,
        }  # fmt: skip

    for season, expected_sot in ((2018, 6), (2014, 1)):
        rows = [match(1, "2019-01-05", season, 6), match(2, "2019-01-12", season, 6)]
        result = compute_rolling(pd.DataFrame(rows), COEF, half_lives=(60,), prior_weight=0.0)
        second = result[(result["match_id"] == 2) & (result["team_id"] == 1)].iloc[0]
        assert np.isclose(second["xgp_for_ewm_h60"], 0.3 * expected_sot)
