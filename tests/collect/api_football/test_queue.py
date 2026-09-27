"""File de travail SQLite : ajout sans doublon, statuts, reprise, remise en file."""
from __future__ import annotations

import pytest

from foot_predictor.collect.api_football import tasks
from foot_predictor.collect.api_football.queue import MAX_TASK_ATTEMPTS, WorkQueue


@pytest.fixture
def queue(tmp_path):
    with WorkQueue.in_raw_dir(tmp_path) as q:
        yield q


def test_queue_file_lives_under_raw_dir(tmp_path, queue):
    assert queue.path == tmp_path / "_queue" / "api_football.sqlite"
    assert queue.path.exists()


def test_add_ignores_duplicates(queue):
    listing = tasks.fixtures_list_task("P1", 39, 2015)
    assert queue.add([listing, tasks.fixtures_list_task("P1", 39, 2016)]) == 2
    assert queue.add([listing]) == 0
    assert queue.contains(listing)


def test_pending_order_follows_tier_then_priority(queue):
    queue.add([
        tasks.players_task("P1", 39, 2015),
        tasks.fixtures_list_task("P2", 39, 2010),
        tasks.fixtures_detail_task("P1", 39, 2015, [1, 2]),
        tasks.fixtures_list_task("P1", 39, 2015),
    ])
    order = [(t.tier, t.task_type) for t in queue.list_pending()]
    assert order == [("P1", "fixtures_list"), ("P1", "fixtures_detail"), ("P1", "players"), ("P2", "fixtures_list")]


def test_rerun_only_replays_pending(tmp_path):
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        queue.add([tasks.fixtures_list_task("P1", 39, s) for s in (2015, 2016, 2017, 2018)])
        first, second, third, _ = queue.list_pending()
        queue.mark_done(first.id, "f1")
        queue.mark_failed(second.id, '{"plan": "x"}', "f2")
        queue.mark_suspect(third.id, "results = 0", "f3")

    # Réouverture : l'état a survécu, seul le 4e reste à faire.
    with WorkQueue.in_raw_dir(tmp_path) as queue:
        pending = queue.list_pending()
        assert [t.params["season"] for t in pending] == [2018]
        assert queue.get(second.id).status == "failed"
        assert queue.get(third.id).last_error == "results = 0"


def test_transient_failures_become_failed_after_max_attempts(queue):
    queue.add([tasks.fixtures_list_task("P1", 39, 2015)])
    (task,) = queue.list_pending()
    statuses = [queue.record_transient_failure(task.id, "HTTP 503") for _ in range(MAX_TASK_ATTEMPTS)]
    assert statuses == ["pending"] * (MAX_TASK_ATTEMPTS - 1) + ["failed"]


def test_requeue(queue):
    queue.add([tasks.fixtures_list_task("P1", 39, 2015), tasks.team_task("P1", "coachs", 33)])
    listing, coachs = queue.list_pending()
    queue.mark_suspect(listing.id, "results = 0", "f")
    queue.mark_failed(coachs.id, "HTTP 404")

    assert queue.requeue("suspect", task_type="coachs") == 0
    assert queue.requeue("suspect") == 1
    requeued = queue.get(listing.id)
    assert (requeued.status, requeued.attempts, requeued.last_error) == ("pending", 0, "results = 0")
    with pytest.raises(ValueError):
        queue.requeue("done")


def test_detail_fixture_ids_and_deferred(queue):
    queue.add([tasks.fixtures_detail_task("P1", 39, 2015, [3, 1]), tasks.fixtures_detail_task("P1", 39, 2015, [7])])
    assert queue.detail_fixture_ids() == {1, 3, 7}

    queue.add_deferred([(10, 39, 2026, "NS", "2026-10-04"), (11, 39, 2026, "NS", None), (12, 39, 2026, "PST", None)])
    assert queue.deferred_summary() == [("NS", 2), ("PST", 1)]
    queue.remove_deferred([10])
    assert queue.deferred_summary() == [("NS", 1), ("PST", 1)]


def test_counts_and_planned_tiers(queue):
    queue.add([tasks.fixtures_list_task("P1", 39, 2015)])
    queue.mark_tier_planned("P1")
    assert queue.counts() == [("P1", "fixtures_list", "pending", 1)]
    assert queue.planned_tiers() == ["P1"]
