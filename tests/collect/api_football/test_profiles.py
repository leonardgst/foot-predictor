"""Profils ciblés (`plan-profiles` et tâches `player_profile`), sans aucun appel réseau."""
from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

import pytest

from foot_predictor.collect.api_football import cli, tasks
from foot_predictor.collect.api_football.plan import parse_config
from foot_predictor.collect.api_football.profiles import build_profile_plan, known_birth_ids, starter_ids
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.collect.api_football.runner import Runner
from foot_predictor.rawstore import manifest, store

from .fakes import FakeClock, FakeSession, make_client, ok, status_body

CONFIG = {"reserve": 500, "tiers": {
    "P1": {"blocks": [
        {"name": "top5", "kind": "league", "leagues": [39], "seasons": {"first": 2015, "last": 2016},
         "endpoints": ["fixtures_list", "fixtures_detail", "players"]},
        {"name": "d2", "kind": "league", "leagues": [40], "seasons": {"first": 2015, "last": 2016},
         "endpoints": ["fixtures_list", "fixtures_detail", "players"]},
        {"name": "coupes", "kind": "cup", "leagues": [45], "seasons": {"first": 2015, "last": 2016},
         "endpoints": ["fixtures_list", "fixtures_detail"], "detail_teams_from": "P1"},
    ]},
    "P2": {"blocks": [
        {"name": "ancien", "kind": "league", "leagues": [39], "seasons": {"first": 2013, "last": 2014},
         "endpoints": ["fixtures_list", "fixtures_detail"]},
    ]},
    "P3": {"blocks": [
        {"name": "autres", "kind": "league", "leagues": [88], "seasons": {"first": 2015, "last": 2016},
         "endpoints": ["fixtures_list", "fixtures_detail", "players"]},
    ]},
}}
T0 = dt.datetime(2026, 9, 29, 8, 0, tzinfo=dt.timezone.utc)


class Raw:
    """Écrit des fichiers bruts au format de l'ADR-0003 (horodatages distincts)."""

    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir
        self.clock = T0

    def write(self, task: tasks.Task, response: list) -> None:
        self.clock += dt.timedelta(seconds=1)
        envelope = store.build_envelope(endpoint=task.endpoint, params=task.params, fetched_at=self.clock,
                                        http_status=200, headers_quota={},
                                        body={"errors": [], "results": len(response), "response": response})
        store.write_envelope(self.raw_dir, task.rel_dir, task.stem, envelope, self.clock)

    def match(self, league: int, season: int, fid: int, home: list[int], away: list[int]) -> None:
        def lineup(ids):
            return {"startXI": [{"player": {"id": pid, "name": f"J{pid}"}} for pid in ids],
                    "substitutes": [{"player": {"id": 7777, "name": "Remplaçant"}}]}
        self.write(tasks.fixtures_detail_task("P1", league, season, [fid]),
                   [{"fixture": {"id": fid}, "lineups": [lineup(home), lineup(away)]}])

    def page(self, league: int, season: int, births: dict[int, str | None]) -> None:
        self.write(tasks.players_task("P1", league, season),
                   [{"player": {"id": pid, "name": f"J{pid}", "birth": {"date": birth}}} for pid, birth in births.items()])


@pytest.fixture
def config():
    return parse_config(copy.deepcopy(CONFIG))


@pytest.fixture
def raw(tmp_path):
    """Titulaires : top 5 (1, 2, 3, 100), D2 (2, 4, 5), coupe (6), P2 (9), P3 (10, 11, 0).

    Dates connues : 1 (page top 5), 4 (page P3 : un autre palier suffit),
    11 (profil ciblé déjà reçu). 5 a un profil sans date : il reste à demander.
    """
    r = Raw(tmp_path)
    r.match(39, 2015, 1001, [1, 2], [3])
    r.match(39, 2016, 1002, [100], [1])
    r.match(40, 2015, 2001, [2, 4], [5])
    r.match(45, 2015, 4501, [6], [1])     # coupe : pas de profils
    r.match(39, 2014, 901, [9], [1])      # P2 (avant 2015) : hors des blocs à profils
    r.match(88, 2016, 8801, [10, 0], [11])
    r.page(39, 2015, {1: "1990-01-01"})
    r.page(40, 2015, {5: None})
    r.page(88, 2016, {4: "1992-02-02"})
    r.write(tasks.player_profile_task("P3", 11), [{"player": {"id": 11, "birth": {"date": "1995-05-05"}}}])
    return tmp_path


def test_player_profile_task_is_one_request_per_player():
    task = tasks.player_profile_task("P1", 276)
    assert (task.endpoint, task.params, task.rel_dir, task.stem) == (
        "/players/profiles", {"player": 276}, "api_football/player_profiles", "player=276")
    assert task.expects_results
    assert task.key != tasks.player_profile_task("P3", 277).key
    assert task.key == tasks.player_profile_task("P3", 276).key  # même requête, quel que soit le palier


def test_known_births_and_starters_read_the_raw_dir(raw):
    assert known_birth_ids(raw) == {1, 4, 11}
    assert starter_ids(raw, 39, [2015, 2016]) == {1, 2, 3, 100}  # remplaçants exclus
    assert starter_ids(raw, 39, [2014]) == {9, 1}
    assert starter_ids(raw, 88, [2015, 2016]) == {10, 11}  # identifiant 0 écarté


def test_plan_orders_blocks_and_skips_known_births(raw, config):
    plan = build_profile_plan(config, raw, ["P1", "P2", "P3"])

    # Un joueur est rattaché au premier bloc où il est titulaire (2 : top 5, pas D2).
    assert plan.missing == {"P1/top5": [2, 3, 100], "P1/d2": [5], "P3/autres": [10]}
    assert dict(plan.starters) == {"P1/top5": 4, "P1/d2": 3, "P3/autres": 2}
    planned = plan.tasks()
    assert [(t.tier, t.params["player"]) for t in planned] == [("P1", 2), ("P1", 3), ("P1", 100), ("P1", 5), ("P3", 10)]
    assert [t.params["player"] for t in plan.tasks(limit=2)] == [2, 3]


def test_plan_can_be_restricted_to_one_tier(raw, config):
    plan = build_profile_plan(config, raw, ["P3"])
    assert plan.missing == {"P3/autres": [10]}


def snapshot(directory: Path) -> dict[str, bytes]:
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in sorted(directory.rglob("*")) if p.is_file()}


def test_cli_dry_run_changes_nothing_and_real_run_fills_the_queue(raw, tmp_path, capsys):
    import yaml

    config_path = tmp_path.parent / f"{tmp_path.name}_collecte.yaml"
    config_path.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    before = snapshot(raw)

    assert cli.main(["--raw-dir", str(raw), "--config", str(config_path), "plan-profiles", "--dry-run"]) == 0
    assert snapshot(raw) == before  # ni fichier brut, ni file créée
    out = capsys.readouterr().out
    assert "Simulation : file inchangée." in out and "P1/top5" in out

    assert cli.main(["--raw-dir", str(raw), "--config", str(config_path), "plan-profiles", "--limit", "4"]) == 0
    with WorkQueue.in_raw_dir(raw) as queue:
        pending = queue.list_pending()
    assert [(t.tier, t.task_type, t.params["player"]) for t in pending] == [
        ("P1", "player_profile", 2), ("P1", "player_profile", 3), ("P1", "player_profile", 100),
        ("P1", "player_profile", 5)]
    # Relancer n'ajoute que ce qui manque.
    assert cli.main(["--raw-dir", str(raw), "--config", str(config_path), "plan-profiles"]) == 0
    assert "Tâches ajoutées à la file : 1" in capsys.readouterr().out


def test_runner_stores_profiles_and_flags_unknown_players(tmp_path, config):
    def handler(endpoint, params):
        if endpoint == "/status":
            return ok(status_body()["response"], results=1)
        if params["player"] == 2:
            return ok([{"player": {"id": 2, "birth": {"date": "1991-01-01"}}}])
        return ok([], results=0)  # identifiant inconnu de /players/profiles

    session = FakeSession(handler=handler)
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        queue.add([tasks.player_profile_task("P1", 2), tasks.player_profile_task("P1", 3),
                   tasks.player_profile_task("P3", 10)])
        report = Runner(make_client(session, FakeClock(), reserve=500, max_requests=3), queue, tmp_path, config,
                        replan=False).run()
        statuses = {t.params["player"]: t.status for t in (queue.get(i) for i in (1, 2, 3))}

    assert [e for e, _ in session.calls] == ["/status", "/players/profiles", "/players/profiles"]
    assert report.stop_reason is not None  # plafond --max-requests atteint : P3 attend
    assert statuses == {2: "done", 3: "suspect", 10: "pending"}
    assert known_birth_ids(tmp_path) == {2}
    logged = [e for e in manifest.read_entries(tmp_path, "api_football") if e["endpoint"] == "/players/profiles"]
    assert [e["params"] for e in logged] == [{"player": 2}, {"player": 3}]
