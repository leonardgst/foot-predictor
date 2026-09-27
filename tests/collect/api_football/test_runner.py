"""Runner de bout en bout contre une fausse API : stockage, statuts, reprise."""
from __future__ import annotations

import gzip

import pytest

from foot_predictor.collect.api_football import tasks
from foot_predictor.collect.api_football.plan import Planner, parse_config
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.collect.api_football.runner import Runner, dry_run_lines
from foot_predictor.rawstore import manifest, store

from .fakes import TEST_KEY, FakeApi, FakeClock, FakeResponse, FakeSession, fixture_item, load_real_fixtures, make_client

REAL_IDS = sorted(f["fixture"]["id"] for f in load_real_fixtures())
LISTING = ("/fixtures", (("league", 39), ("season", 2015)))


def make_config(endpoints=("fixtures_list", "fixtures_detail")):
    return parse_config({"reserve": 500, "tiers": {"P1": {"blocks": [{
        "name": "top5", "kind": "league", "leagues": [39], "seasons": {"first": 2015, "last": 2015},
        "endpoints": list(endpoints)}]}}})


@pytest.fixture
def api():
    fake = FakeApi()
    fake.listings[(39, 2015)] = [fixture_item(i) for i in REAL_IDS] + [fixture_item(999, status="NS")]
    return fake


def run_once(raw_dir, api, cfg, *, remaining_day=7000, **client_kwargs):
    session = FakeSession(handler=api, remaining_day=remaining_day)
    client = make_client(session, FakeClock(), reserve=cfg.reserve, **client_kwargs)
    with WorkQueue.in_raw_dir(raw_dir) as queue:
        if not queue.planned_tiers():
            Planner(cfg, raw_dir, queue).plan("P1")
        report = Runner(client, queue, raw_dir, cfg).run()
    return report, session


def all_tasks(raw_dir):
    with WorkQueue.in_raw_dir(raw_dir) as queue:
        rows = queue._conn.execute("SELECT id FROM tasks ORDER BY id").fetchall()
        return [queue.get(row[0]) for row in rows]


def test_full_flow_with_real_payloads(tmp_path, api):
    report, session = run_once(tmp_path, api, make_config())

    assert report.stop_reason is None
    # /status, liste, puis un lot de 5 créé par la relance automatique du plan.
    assert [c[0] for c in session.calls] == ["/status", "/fixtures", "/fixtures"]
    assert session.calls[2][1] == {"ids": "-".join(str(i) for i in REAL_IDS)}
    assert {t.task_type: t.status for t in all_tasks(tmp_path)} == {"fixtures_list": "done", "fixtures_detail": "done"}

    entries = manifest.read_entries(tmp_path, "api_football")
    assert [e["endpoint"] for e in entries] == ["/status", "/fixtures", "/fixtures"]
    detail = entries[-1]
    assert detail["fixture_ids"] == REAL_IDS and detail["results"] == 5
    assert detail["quota_remaining_day"] is not None
    envelope = store.read_envelope(tmp_path / detail["file"])
    by_id = lambda items: sorted(items, key=lambda f: f["fixture"]["id"])  # noqa: E731
    assert by_id(envelope["body"]["response"]) == by_id(load_real_fixtures())  # réponse intacte
    assert detail["file"].startswith("api_football/fixtures_detail/league=39/season=2015/")

    # Relancer ne rejoue rien.
    report, session = run_once(tmp_path, api, make_config())
    assert [c[0] for c in session.calls] == ["/status"]


def test_api_key_never_written_to_disk(tmp_path, api):
    run_once(tmp_path, api, make_config())
    for path in tmp_path.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            if path.suffix == ".gz":
                data = gzip.decompress(data)
            assert TEST_KEY.encode() not in data, path


def test_errors_give_failed_without_retry(tmp_path, api):
    api.errors[LISTING] = {"plan": "Free plans do not have access to this season"}

    report, session = run_once(tmp_path, api, make_config())

    (listing,) = all_tasks(tmp_path)
    assert listing.status == "failed" and "plan" in listing.last_error
    assert listing.file is not None  # réponse stockée pour la traçabilité
    assert manifest.read_entries(tmp_path, "api_football")[-1]["errors"] == {"plan": "Free plans do not have access to this season"}
    _, session = run_once(tmp_path, api, make_config())
    assert [c[0] for c in session.calls] == ["/status"]


def test_unexpected_zero_results_give_suspect(tmp_path, api):
    api.empty.add(LISTING)
    run_once(tmp_path, api, make_config())
    (listing,) = all_tasks(tmp_path)
    assert listing.status == "suspect"


def test_zero_results_allowed_for_transfers(tmp_path, api):
    api.teams[(39, 2015)] = [33]
    api.empty.add(("/transfers", (("team", 33),)))
    run_once(tmp_path, api, make_config(("teams", "transfers")))
    assert {t.task_type: t.status for t in all_tasks(tmp_path)} == {"teams": "done", "transfers": "done"}


def test_incomplete_detail_batch_is_suspect(tmp_path, api):
    del api.details[REAL_IDS[0]]
    run_once(tmp_path, api, make_config())
    detail = [t for t in all_tasks(tmp_path) if t.task_type == "fixtures_detail"][0]
    assert detail.status == "suspect" and str(REAL_IDS[0]) in detail.last_error


def test_players_pagination(tmp_path, api):
    api.player_pages[(39, 2015)] = 3
    report, session = run_once(tmp_path, api, make_config(("players",)))

    pages = sorted(c[1]["page"] for c in session.calls if c[0] == "/players")
    assert pages == [1, 2, 3]
    stems = sorted(p.name.split("__")[0] for p in (tmp_path / "api_football/players/league=39/season=2015").iterdir())
    assert stems == ["page=01", "page=02", "page=03"]
    assert all(t.status == "done" for t in all_tasks(tmp_path))


def test_stops_under_reserve_and_resumes_next_day(tmp_path, api):
    # Quota restant 503 : /status (502), liste (501), lot (500) -> arrêt sous la réserve.
    api.teams[(39, 2015)] = [33]
    cfg = make_config(("fixtures_list", "fixtures_detail", "teams", "coachs"))
    report, session = run_once(tmp_path, api, cfg, remaining_day=503)

    assert "réserve" in report.stop_reason
    assert len(session.calls) == 3
    assert any(t.status == "pending" for t in all_tasks(tmp_path))

    report, session = run_once(tmp_path, api, cfg, remaining_day=7500)  # lendemain
    assert report.stop_reason is None
    assert all(t.status == "done" for t in all_tasks(tmp_path))


def test_max_requests_stops_cleanly(tmp_path, api):
    report, session = run_once(tmp_path, api, make_config(), max_requests=2)
    assert "maximal" in report.stop_reason
    assert len(session.calls) == 2
    assert report.requests == 2


def test_persistent_5xx_keeps_task_pending_then_failed(tmp_path, api):
    def broken(endpoint, params):
        return FakeResponse(503, {}) if endpoint == "/fixtures" else api(endpoint, params)

    for expected in ("pending", "pending", "failed"):
        session = FakeSession(handler=broken)
        with WorkQueue.in_raw_dir(tmp_path) as queue:
            if not queue.planned_tiers():
                Planner(make_config(), tmp_path, queue).plan("P1")
            Runner(make_client(session, FakeClock()), queue, tmp_path, make_config()).run()
        (listing,) = all_tasks(tmp_path)
        assert listing.status == expected
        # Une seule série de 3 tentatives par lancement : pas de boucle infinie.
        assert len([c for c in session.calls if c[0] == "/fixtures"]) == 3


def test_daily_quota_error_stops_and_keeps_task_pending(tmp_path, api):
    api.errors[LISTING] = {"requests": "You have reached the request limit for the day"}
    report, _ = run_once(tmp_path, api, make_config())
    assert "Quota du jour" in report.stop_reason
    (listing,) = all_tasks(tmp_path)
    assert listing.status == "pending"


def test_dry_run_sends_nothing(tmp_path):
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        assert "Aucune tâche pending" in "\n".join(dry_run_lines(queue))
        queue.add([tasks.fixtures_list_task("P1", 39, 2015), tasks.players_task("P1", 39, 2015)])
        text = "\n".join(dry_run_lines(queue))
    assert "fixtures_list" in text and "players" in text and "Total" in text
