"""Rafraîchissement d'une saison en cours (commande `refresh`), sans aucun appel réseau."""
from __future__ import annotations

import copy
import datetime as dt

import pytest

from foot_predictor.collect.api_football import cli, tasks
from foot_predictor.collect.api_football.coverage import coverage_from_body
from foot_predictor.collect.api_football.plan import Planner, parse_config
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.collect.api_football.refresh import apply_refresh, build_refresh_plan, plan_lines
from foot_predictor.collect.api_football.runner import Runner
from foot_predictor.rawstore import manifest

from .fakes import FakeApi, FakeClock, FakeSession, fixture_item, leagues_response, load_real_fixtures, make_client

REAL_IDS = sorted(f["fixture"]["id"] for f in load_real_fixtures())
NOW = dt.datetime(2026, 10, 10, 8, 0, tzinfo=dt.timezone.utc)
CONFIG = {"reserve": 500, "tiers": {"P1": {"blocks": [
    {"name": "top5", "kind": "league", "leagues": [39], "seasons": {"first": 2015, "last": 2015},
     "endpoints": ["fixtures_list", "fixtures_detail", "teams", "injuries"]},
]}}}


def future(item: dict) -> dict:
    item["fixture"]["date"] = "2099-01-01T15:00:00+00:00"
    return item


@pytest.fixture
def config():
    return parse_config(copy.deepcopy(CONFIG))


@pytest.fixture
def api():
    """Liste de mi-saison : 5 matchs terminés, 999 joué mais pas encore
    terminé dans la liste, 998 à venir."""
    fake = FakeApi()
    fake.listings[(39, 2015)] = ([fixture_item(i) for i in REAL_IDS]
                                 + [fixture_item(999, status="NS"), future(fixture_item(998, status="NS"))])
    fake.teams[(39, 2015)] = [33, 47]
    played = copy.deepcopy(load_real_fixtures()[0])
    played["fixture"]["id"] = 999
    fake.details[999] = played
    return fake


def run_once(raw_dir, api, config):
    session = FakeSession(handler=api)
    with WorkQueue.in_raw_dir(raw_dir) as queue:
        if not queue.planned_tiers():
            Planner(config, raw_dir, queue).plan("P1")
        Runner(make_client(session, FakeClock(), reserve=config.reserve), queue, raw_dir, config).run()
    return session.calls


def test_refresh_collects_only_the_matches_that_became_terminal(tmp_path, api, config):
    calls = run_once(tmp_path, api, config)
    assert [e for e, p in calls if "ids" in p] == ["/fixtures"]  # un seul lot : les 5 matchs terminés

    # Quelques jours plus tard, 999 est terminé.
    api.listings[(39, 2015)][-2]["fixture"]["status"]["short"] = "FT"
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        plan = build_refresh_plan(config, tmp_path, queue, 2015, ["P1"], now=NOW)
        assert sorted(item.task.task_type for item in plan.to_queue) == ["fixtures_list", "injuries", "teams"]
        assert plan.overdue == {39: 1}  # 999 (date passée) ; pas 998 (à venir)
        assert (plan.list_requests, plan.max_detail_batches, plan.max_requests) == (3, 1, 5)
        assert apply_refresh(queue, plan) == (0, 3)

    calls = run_once(tmp_path, api, config)

    kinds = ["detail" if "ids" in p else e for e, p in calls]
    assert kinds == ["/status", "/fixtures", "/teams", "detail", "/injuries"]
    assert calls[3][1] == {"ids": "999"}  # seulement le match devenu terminal
    assert len(calls) <= plan.max_requests
    # Rien n'est écrasé : deux versions de la liste, toutes deux dans le journal.
    listing = tasks.fixtures_list_task("P1", 39, 2015)
    versions = sorted((tmp_path / listing.rel_dir).glob(f"{listing.stem}__*.json.gz"))
    assert len(versions) == 2
    logged = {e["file"] for e in manifest.read_entries(tmp_path, "api_football")}
    assert {v.relative_to(tmp_path).as_posix() for v in versions} <= logged
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        assert queue.deferred_summary() == [("NS", 1)]  # 998 reste de côté
    # Un nouveau run ne redemande rien.
    assert [e for e, _ in run_once(tmp_path, api, config)] == ["/status"]


def test_refresh_is_idempotent_until_run(tmp_path, api, config):
    run_once(tmp_path, api, config)
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        first = build_refresh_plan(config, tmp_path, queue, 2015, ["P1"], now=NOW)
        apply_refresh(queue, first)
        second = build_refresh_plan(config, tmp_path, queue, 2015, ["P1"], now=NOW)
    assert {item.action for item in second.items} == {"déjà en attente"}
    assert second.to_queue == [] and second.max_requests == 0


def test_failed_tasks_are_left_to_requeue(tmp_path, api, config):
    api.errors[("/injuries", (("league", 39), ("season", 2015)))] = {"plan": "non couvert"}
    run_once(tmp_path, api, config)
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        plan = build_refresh_plan(config, tmp_path, queue, 2015, ["P1"], now=NOW)
        apply_refresh(queue, plan)
        injuries = tasks.league_season_task("P1", "injuries", 39, 2015)
        assert queue.status_of(injuries) == "failed"
    assert any("requeue --status failed" in line for line in plan_lines(plan))


def test_season_tasks_follow_blocks_and_coverage(tmp_path, config):
    coverage = coverage_from_body({"response": leagues_response()})  # 2015 : injuries non couvert
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        planner = Planner(config, tmp_path, queue, coverage=coverage)
        found = planner.season_tasks("P1", 2015, ("fixtures_list", "teams", "injuries"))
        assert [t.task_type for t in found] == ["fixtures_list", "teams"]
        assert planner.season_tasks("P1", 2014, ("fixtures_list",)) == []  # hors des bornes du bloc
        assert queue.counts() == []  # rien n'est écrit


def test_queue_reopen_only_touches_done_and_suspect(tmp_path):
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        done, suspect, failed, pending = (tasks.team_task("P1", "coachs", team) for team in (1, 2, 3, 4))
        queue.add([done, suspect, failed, pending])
        ids = {t.params["team"]: t.id for t in queue.list_pending()}
        queue.mark_done(ids[1], "a")
        queue.mark_suspect(ids[2], "results = 0", "b")
        queue.mark_failed(ids[3], "errors")

        assert queue.reopen(t.key for t in (done, suspect, failed, pending)) == 2

        assert [queue.status_of(t) for t in (done, suspect, failed, pending)] == ["pending", "pending", "failed", "pending"]
        assert queue.get(ids[1]).file == "a"  # la réponse précédente reste référencée jusqu'au run


def test_overdue_deferred_counts_past_matches_of_the_given_leagues(tmp_path):
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        queue.add_deferred([
            (1, 39, 2026, "NS", "2026-10-04T14:00:00+00:00"),
            (2, 39, 2026, "NS", "2026-10-18T14:00:00+00:00"),  # à venir
            (3, 39, 2026, "PST", "2026-09-20T14:00:00"),  # sans fuseau : UTC
            (4, 61, 2026, "NS", "2026-10-04T14:00:00+00:00"),  # autre compétition
            (5, 39, 2025, "NS", "2025-10-04T14:00:00+00:00"),  # autre saison
            (6, 39, 2026, "TBD", None),
        ])
        assert queue.overdue_deferred(2026, [39], NOW) == {39: 2}


# --- ligne de commande ---------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "collecte.yaml"
    path.write_text(
        "reserve: 500\n"
        "tiers:\n"
        "  P1:\n"
        "    blocks:\n"
        "      - {name: top5, kind: league, leagues: [39], seasons: {first: 2015, last: 2015},\n"
        "         endpoints: [fixtures_list, fixtures_detail, teams, injuries]}\n"
        "  P2:\n"
        "    blocks: []\n",
        encoding="utf-8",
    )
    return path


def cli_run(tmp_path, config_file, api, *args):
    sessions = []

    def factory(config, max_requests):
        session = FakeSession(handler=api)
        sessions.append(session)
        return make_client(session, FakeClock(), reserve=config.reserve, max_requests=max_requests)

    code = cli.main(["--raw-dir", str(tmp_path / "raw"), "--config", str(config_file), *args], client_factory=factory)
    return code, [c for s in sessions for c in s.calls]


def statuses(raw_dir):
    with WorkQueue.in_raw_dir(raw_dir) as queue:
        return sorted((task_type, status) for _, task_type, status, _ in queue.counts())


@pytest.fixture
def collected(tmp_path, config_file, api):
    cli_run(tmp_path, config_file, api, "plan", "--palier", "P1")
    cli_run(tmp_path, config_file, api, "run")
    return tmp_path / "raw"


def test_cli_dry_run_shows_cost_and_changes_nothing(tmp_path, config_file, api, collected, capsys):
    before = statuses(collected)
    capsys.readouterr()

    code, calls = cli_run(tmp_path, config_file, api, "refresh", "--season", "2015", "--dry-run")

    out = capsys.readouterr().out
    assert code == 0 and calls == []
    assert "aucune requête" in out and "au plus" in out and "Simulation : file inchangée." in out
    assert statuses(collected) == before


def test_cli_asks_for_confirmation(tmp_path, config_file, api, collected, monkeypatch, capsys):
    before = statuses(collected)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert cli_run(tmp_path, config_file, api, "refresh", "--season", "2015")[0] == 0
    assert statuses(collected) == before
    assert "Annulé" in capsys.readouterr().out

    monkeypatch.setattr("builtins.input", lambda prompt: "o")
    code, calls = cli_run(tmp_path, config_file, api, "refresh", "--season", "2015", "--palier", "P1")
    assert code == 0 and calls == []
    assert ("fixtures_list", "pending") in statuses(collected)
    assert "3 tâche(s) remise(s) en file" in capsys.readouterr().out


def test_cli_closed_input_means_no(tmp_path, config_file, api, collected, monkeypatch):
    before = statuses(collected)

    def closed(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)
    cli_run(tmp_path, config_file, api, "refresh", "--season", "2015")
    assert statuses(collected) == before


def test_cli_yes_then_run_fetches_the_new_lists(tmp_path, config_file, api, collected):
    code, _ = cli_run(tmp_path, config_file, api, "refresh", "--season", "2015", "--yes")
    assert code == 0
    _, calls = cli_run(tmp_path, config_file, api, "run")
    assert [e for e, p in calls if "ids" not in p] == ["/status", "/fixtures", "/teams", "/injuries"]


def test_cli_refuses_a_tier_never_planned(tmp_path, config_file, api, collected, capsys):
    code, _ = cli_run(tmp_path, config_file, api, "refresh", "--season", "2015", "--palier", "P2", "--yes")
    assert code == 2
    assert "jamais planifié" in capsys.readouterr().err


def test_cli_without_any_planned_tier(tmp_path, config_file, api, capsys):
    code, _ = cli_run(tmp_path, config_file, api, "refresh", "--season", "2015")
    assert code == 0
    assert "Aucun palier planifié" in capsys.readouterr().out
