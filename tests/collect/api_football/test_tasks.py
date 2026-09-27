"""Clés canoniques et emplacements des fichiers bruts (rapport G.6, G.7)."""
from __future__ import annotations

import pytest

from foot_predictor.collect.api_football import tasks


def test_request_key_ignores_parameter_order():
    assert tasks.request_key("/fixtures", {"league": 39, "season": 2015}) == tasks.request_key(
        "/fixtures", {"season": 2015, "league": 39}
    )
    assert tasks.request_key("/fixtures", {"league": 39, "season": 2015}) != tasks.request_key(
        "/fixtures", {"league": 39, "season": 2016}
    )


def test_fixtures_detail_task_sorts_ids_and_locates_file():
    task = tasks.fixtures_detail_task("P1", 39, 2015, [192299, 192297, 192298])

    assert task.params == {"ids": "192297-192298-192299"}
    assert task.endpoint == "/fixtures"
    assert task.rel_dir == "api_football/fixtures_detail/league=39/season=2015"
    assert len(task.stem) == 12
    assert task.key == tasks.fixtures_detail_task("P1", 39, 2015, [192297, 192298, 192299]).key


@pytest.mark.parametrize("size", [0, 21])
def test_fixtures_detail_task_rejects_bad_batch_size(size):
    with pytest.raises(ValueError):
        tasks.fixtures_detail_task("P1", 39, 2015, list(range(1, size + 1)))


def test_locations_follow_report_g7():
    assert tasks.leagues_task("P1").rel_dir == "api_football/leagues"
    listing = tasks.fixtures_list_task("P1", 39, 2023)
    assert (listing.rel_dir, listing.stem) == ("api_football/fixtures_list/league=39", "season=2023")
    players = tasks.players_task("P1", 39, 2023, 3)
    assert (players.rel_dir, players.stem) == ("api_football/players/league=39/season=2023", "page=03")
    coachs = tasks.team_task("P1", "coachs", 33)
    assert (coachs.rel_dir, coachs.stem, coachs.params) == ("api_football/coachs", "team=33", {"team": 33})


def test_expectations_and_priorities():
    assert tasks.team_task("P1", "transfers", 33).expects_results is False
    assert tasks.team_task("P1", "coachs", 33).expects_results is True
    assert tasks.PRIORITY["fixtures_list"] < tasks.PRIORITY["fixtures_detail"] < tasks.PRIORITY["players"]
    assert tasks.parse_ids("1-2-3") == [1, 2, 3]
