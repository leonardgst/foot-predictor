"""Palier P4 : lots `/sidelined`, `refresh --league` et classements, sans aucun appel réseau."""
from __future__ import annotations

import copy
import datetime as dt

import pytest

from foot_predictor.collect.api_football import cli, tasks
from foot_predictor.collect.api_football.plan import parse_config
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.collect.api_football.refresh import build_refresh_plan
from foot_predictor.collect.api_football.sidelined import build_sidelined_plan, queued_players
from foot_predictor.rawstore import store

CONFIG = {"reserve": 500, "tiers": {
    "P1": {"blocks": [
        {"name": "top5", "kind": "league", "leagues": [39], "seasons": {"first": 2015, "last": 2016},
         "endpoints": ["fixtures_list", "fixtures_detail"]},
    ]},
    "P3": {"blocks": [
        {"name": "autres", "kind": "league", "leagues": [88, 253], "seasons": {"first": 2017, "last": 2017},
         "endpoints": ["fixtures_list", "fixtures_detail"]},
    ]},
}}
T0 = dt.datetime(2026, 9, 29, 8, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def config():
    return parse_config(copy.deepcopy(CONFIG))


def write_match(raw, league, season, fid, starters, when):
    task = tasks.fixtures_detail_task("P1", league, season, [fid])
    body = {"errors": [], "response": [{"fixture": {"id": fid}, "lineups": [
        {"startXI": [{"player": {"id": pid}} for pid in starters]}]}]}
    envelope = store.build_envelope(endpoint="/fixtures", params=task.params, fetched_at=when, http_status=200,
                                    headers_quota={}, body=body)
    store.write_envelope(raw, task.rel_dir, task.stem, envelope, when)


def test_sidelined_batch_task_groups_up_to_20_players():
    task = tasks.sidelined_batch_task("P4", [30, 10, 20])
    assert (task.endpoint, task.params, task.rel_dir) == ("/sidelined", {"players": "10-20-30"}, "api_football/sidelined/lots")
    assert task.key == tasks.sidelined_batch_task("P4", [10, 20, 30]).key
    assert not task.expects_results  # un joueur peut n'avoir aucune indisponibilité
    with pytest.raises(ValueError):
        tasks.sidelined_batch_task("P4", list(range(21)))


def test_plan_sidelined_freezes_batches_and_never_requeues_a_player(tmp_path, config):
    write_match(tmp_path, 39, 2015, 1, list(range(1, 26)), T0)          # 25 titulaires
    write_match(tmp_path, 39, 2014, 2, [900], T0)                       # hors des saisons du bloc
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        plan = build_sidelined_plan(config, tmp_path, queue)
        assert (plan.starters, plan.already, len(plan.new)) == (25, 0, 25)
        assert [t.params["players"].count("-") + 1 for t in plan.tasks()] == [20, 5]
        assert queue.add(plan.tasks()) == 2

        # Nouveaux matchs (après un refresh) : seuls les nouveaux titulaires sont mis en lot.
        write_match(tmp_path, 39, 2016, 3, [5, 26, 27], T0 + dt.timedelta(days=1))
        again = build_sidelined_plan(config, tmp_path, queue)
        assert (again.already, again.new) == (25, [26, 27])
        assert queued_players(queue) == set(range(1, 26))


def test_plan_sidelined_cli_dry_run_changes_nothing(tmp_path, config, capsys):
    import yaml

    config_path = tmp_path / "collecte.yaml"
    config_path.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    raw = tmp_path / "raw"
    write_match(raw, 39, 2015, 1, [1, 2, 3], T0)
    base = ["--raw-dir", str(raw), "--config", str(config_path)]

    assert cli.main([*base, "plan-sidelined", "--dry-run"]) == 0
    assert "Lots de 20 (1 requête chacun) : 1" in capsys.readouterr().out
    assert not (raw / "_queue").exists()
    assert cli.main([*base, "plan-sidelined"]) == 0
    with WorkQueue.in_raw_dir(raw) as queue:
        assert [(t.tier, t.task_type, t.params) for t in queue.list_pending()] == [("P4", "sidelined", {"players": "1-2-3"})]


def test_refresh_can_be_limited_to_one_league(tmp_path, config):
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        everything = build_refresh_plan(config, tmp_path, queue, 2017, ["P3"])
        only_mls = build_refresh_plan(config, tmp_path, queue, 2017, ["P3"], leagues=[253])
    assert sorted(i.task.params["league"] for i in everything.items) == [88, 253]
    assert [(i.task.task_type, i.task.params) for i in only_mls.items] == [("fixtures_list", {"league": 253, "season": 2017})]
