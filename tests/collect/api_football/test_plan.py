"""Planification : lots de 20, matchs déjà présents, statuts, coupes, couverture."""
from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.collect.api_football import tasks
from foot_predictor.collect.api_football.coverage import coverage_from_body
from foot_predictor.collect.api_football.plan import (
    ConfigError,
    Planner,
    load_config,
    parse_config,
)
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.collect.api_football.runner import manifest_extra
from foot_predictor.rawstore import manifest, store

from .fakes import api_body, fixture_item, leagues_response, load_real_fixtures

T0 = dt.datetime(2026, 10, 2, 8, 0, tzinfo=dt.timezone.utc)
REAL_IDS = sorted(f["fixture"]["id"] for f in load_real_fixtures())  # 192297 à 192301


def config(*blocks, tier="P1", terminal=("FT", "AET", "PEN", "AWD", "WO")):
    return parse_config({"reserve": 500, "terminal_statuses": list(terminal), "tiers": {tier: {"blocks": list(blocks)}}})


def league_block(endpoints=("fixtures_list", "fixtures_detail"), leagues=(39,), first=2015, last=2015, **extra):
    return {"name": "top5", "kind": "league", "leagues": list(leagues),
            "seasons": {"first": first, "last": last}, "endpoints": list(endpoints), **extra}


def save(raw_dir, task, response_items, *, when=T0, errors=None):
    """Stocke une réponse comme le ferait le runner (fichier + journal)."""
    envelope = store.build_envelope(
        endpoint=task.endpoint, params=task.params, fetched_at=when, http_status=200,
        headers_quota={}, body=api_body(response_items, errors=errors),
    )
    stored = store.write_envelope(raw_dir, task.rel_dir, task.stem, envelope, when)
    manifest.append_entry(raw_dir, "api_football", manifest.entry_for_stored(
        envelope, stored, source="api_football", duration_ms=1, extra=manifest_extra(envelope)))


@pytest.fixture
def queue(tmp_path):
    with WorkQueue.in_raw_dir(tmp_path) as q:
        yield q


def detail_batches(queue):
    return [tasks.parse_ids(t.params["ids"]) for t in queue.list_pending() if t.task_type == "fixtures_detail"]


def test_real_config_file_is_valid():
    cfg = load_config()
    assert set(cfg.tiers) == {"P1", "P2", "P3", "P4"}
    assert cfg.reserve == 500
    assert cfg.tiers["P4"] == []
    p1_leagues = {league for block in cfg.tiers["P1"] for league in block.leagues}
    assert {39, 140, 78, 135, 61, 40, 141, 79, 136, 62, 2, 3, 848, 45, 48, 143, 81, 137, 66} == p1_leagues


def test_first_pass_plans_listings_and_waits_for_details(tmp_path, queue):
    cfg = config(league_block(endpoints=("fixtures_list", "fixtures_detail", "teams", "players", "coachs")))
    report = Planner(cfg, tmp_path, queue).plan("P1")

    assert dict(report.added) == {"fixtures_list": 1, "teams": 1, "players": 1}
    assert report.waiting == {"fixtures_detail": 1, "coachs/transfers": 1}
    assert queue.planned_tiers() == ["P1"]
    # Idempotent : relancer n'ajoute rien.
    assert Planner(cfg, tmp_path, queue).plan("P1").total_added == 0


def test_details_are_split_into_batches_of_20(tmp_path, queue):
    items = [fixture_item(i) for i in REAL_IDS] + [fixture_item(1000 + i) for i in range(40)]
    save(tmp_path, tasks.fixtures_list_task("P1", 39, 2015), items)

    report = Planner(config(league_block()), tmp_path, queue).plan("P1")

    batches = detail_batches(queue)
    assert [len(b) for b in batches] == [20, 20, 5]
    assert sorted(i for b in batches for i in b) == sorted([f["fixture"]["id"] for f in items])
    assert report.added["fixtures_detail"] == 3


def test_fixtures_already_in_manifest_or_queue_are_skipped(tmp_path, queue):
    save(tmp_path, tasks.fixtures_list_task("P1", 39, 2015), [fixture_item(i) for i in REAL_IDS + [2000, 2001]])
    # Les 5 matchs réels ont déjà leur détail dans le journal (champ fixture_ids).
    save(tmp_path, tasks.fixtures_detail_task("P1", 39, 2015, REAL_IDS), load_real_fixtures())
    # 2000 est déjà dans un lot en file.
    queue.add([tasks.fixtures_detail_task("P1", 39, 2015, [2000])])

    report = Planner(config(league_block()), tmp_path, queue).plan("P1")

    assert report.added["fixtures_detail"] == 1
    assert [b for b in detail_batches(queue) if b != [2000]] == [[2001]]
    assert report.skipped["match déjà présent ou déjà en lot"] == 6


def test_detail_with_errors_does_not_count_as_present(tmp_path, queue):
    save(tmp_path, tasks.fixtures_list_task("P1", 39, 2015), [fixture_item(REAL_IDS[0])])
    save(tmp_path, tasks.fixtures_detail_task("P1", 39, 2015, [REAL_IDS[0]]), [], errors={"plan": "x"})

    Planner(config(league_block()), tmp_path, queue).plan("P1")

    assert detail_batches(queue) == [[REAL_IDS[0]]]


def test_non_terminal_fixtures_are_listed_apart(tmp_path, queue):
    items = [fixture_item(1, status="FT"), fixture_item(2, status="AET"), fixture_item(3, status="PEN"),
             fixture_item(4, status="AWD"), fixture_item(5, status="WO"), fixture_item(6, status="NS"),
             fixture_item(7, status="PST"), fixture_item(8, status="1H")]
    save(tmp_path, tasks.fixtures_list_task("P1", 39, 2026), items)

    report = Planner(config(league_block(first=2026, last=2026)), tmp_path, queue).plan("P1")

    assert detail_batches(queue) == [[1, 2, 3, 4, 5]]
    assert report.deferred == 3
    assert dict(queue.deferred_summary()) == {"NS": 1, "PST": 1, "1H": 1}


def test_cup_details_only_for_matches_with_a_followed_team(tmp_path, queue):
    league_items = [fixture_item(10, home=33, away=47), fixture_item(11, home=50, away=51)]
    cup_items = [fixture_item(20, league=45, home=33, away=900),  # Man United : suivi
                 fixture_item(21, league=45, home=901, away=902),  # deux clubs amateurs
                 fixture_item(22, league=45, home=903, away=51)]   # équipe 51 : suivie
    save(tmp_path, tasks.fixtures_list_task("P1", 39, 2015), league_items)
    save(tmp_path, tasks.fixtures_list_task("P1", 45, 2015), cup_items)
    cup = {"name": "coupes", "kind": "cup", "leagues": [45], "seasons": {"first": 2015, "last": 2015},
           "endpoints": ["fixtures_list", "fixtures_detail"], "detail_teams_from": "P1"}

    report = Planner(config(league_block(), cup), tmp_path, queue).plan("P1")

    assert sorted(detail_batches(queue)) == [[10, 11], [20, 22]]
    assert report.skipped["coupe : aucune équipe suivie"] == 1


def test_cup_waits_while_league_listing_is_pending(tmp_path, queue):
    save(tmp_path, tasks.fixtures_list_task("P1", 45, 2015), [fixture_item(20, league=45)])
    cup = {"name": "coupes", "kind": "cup", "leagues": [45], "seasons": {"first": 2015, "last": 2015},
           "endpoints": ["fixtures_list", "fixtures_detail"], "detail_teams_from": "P1"}

    report = Planner(config(league_block(), cup), tmp_path, queue).plan("P1")

    assert detail_batches(queue) == []
    assert report.waiting["fixtures_detail"] == 2  # le championnat (liste absente) et la coupe


def test_team_tasks_are_derived_from_teams_listing(tmp_path, queue):
    save(tmp_path, tasks.league_season_task("P1", "teams", 39, 2015), [{"team": {"id": 33}}, {"team": {"id": 47}}])
    save(tmp_path, tasks.league_season_task("P1", "teams", 39, 2016), [{"team": {"id": 33}}, {"team": {"id": 50}}])
    cfg = config(league_block(endpoints=("teams", "coachs", "transfers"), last=2016))

    report = Planner(cfg, tmp_path, queue).plan("P1")

    assert report.added["coachs"] == 3 and report.added["transfers"] == 3
    teams = sorted(t.params["team"] for t in queue.list_pending() if t.task_type == "coachs")
    assert teams == [33, 47, 50]


def test_coverage_filters_seasons_and_endpoints(tmp_path, queue):
    coverage = coverage_from_body(api_body(leagues_response()))
    cfg = config(league_block(endpoints=("fixtures_list", "injuries"), first=2014, last=2016))

    report = Planner(cfg, tmp_path, queue, coverage=coverage).plan("P1")

    planned = sorted((t.task_type, t.params["season"]) for t in queue.list_pending())
    # 2016 absente de /leagues ; injuries non couvert en 2015.
    assert planned == [("fixtures_list", 2014), ("fixtures_list", 2015), ("injuries", 2014)]
    assert report.skipped["saison absente de /leagues"] == 1
    assert report.skipped["injuries non couvert"] == 1


def test_p2_keeps_only_old_seasons_with_lineups(tmp_path, queue):
    coverage = coverage_from_body(api_body(leagues_response()))
    cfg = parse_config({"tiers": {"P2": {"blocks": [{
        "name": "historique", "kind": "league", "leagues": [39],
        "seasons": {"last": 2014, "requires_coverage": "fixtures.lineups"},
        "endpoints": ["fixtures_list"]}]}}})

    report = Planner(cfg, tmp_path, queue, coverage=coverage).plan("P2")

    assert [t.params["season"] for t in queue.list_pending()] == [2014]
    assert report.skipped["saison sans fixtures.lineups"] == 1


def test_unknown_league_in_coverage_is_skipped_with_warning(tmp_path, queue):
    coverage = coverage_from_body(api_body(leagues_response()))
    report = Planner(config(league_block(leagues=(999,))), tmp_path, queue, coverage=coverage).plan("P1")
    assert report.total_added == 0
    assert any("999" in w for w in report.warnings)


def test_warns_when_earlier_tier_is_still_pending(tmp_path, queue):
    queue.add([tasks.fixtures_list_task("P1", 39, 2015)])
    cfg = parse_config({"tiers": {"P1": {"blocks": []}, "P3": {"blocks": [league_block()]}}})
    report = Planner(cfg, tmp_path, queue).plan("P3")
    assert any("P1 a encore 1 tâches pending" in w for w in report.warnings)


def test_empty_tier_warns(tmp_path, queue):
    cfg = parse_config({"tiers": {"P4": {"blocks": []}}})
    assert any("aucun bloc" in w for w in Planner(cfg, tmp_path, queue).plan("P4").warnings)


@pytest.mark.parametrize("bad", [
    {"endpoints": ["inconnu"]},
    {"endpoints": ["coachs"]},  # coachs sans teams
    {"kind": "autre"},
    {"seasons": {"first": 2015}},  # last manquant
    {"detail_teams_from": "P9"},
])
def test_invalid_config_is_rejected(bad):
    with pytest.raises(ConfigError):
        config({**league_block(), **bad})


def test_unknown_tier_is_rejected(tmp_path, queue):
    with pytest.raises(ConfigError):
        Planner(config(league_block()), tmp_path, queue).plan("P7")
