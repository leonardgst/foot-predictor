"""Verrou de collecte (`rawstore/lock.py`), sans processus réel à part celui des tests."""
from __future__ import annotations

import datetime as dt
import json
import os
import socket

import pytest

from foot_predictor.rawstore.lock import (
    STALE_AFTER,
    CollectLock,
    LockHeldError,
    LockInfo,
    is_stale,
    lock_path,
    pid_alive,
    read_lock,
)

NOW = dt.datetime(2026, 10, 10, 9, 0, tzinfo=dt.timezone.utc)


def alive(pid: int) -> bool:
    return True


def dead(pid: int) -> bool:
    return False


def make_lock(raw, command="run", *, pid=111, alive_fn=alive, now=NOW, **kwargs) -> CollectLock:
    return CollectLock(raw, command, pid=pid, alive=alive_fn, now=lambda: now, sleep=lambda s: None, **kwargs)


def write_lock(raw, *, pid=222, started=NOW, host=None, command="refresh"):
    path = lock_path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "command": command, "host": host or socket.gethostname(),
                                "started_at": started.isoformat()}), encoding="utf-8")


def test_lock_is_created_then_removed(tmp_path):
    with make_lock(tmp_path, "run --max-requests 5") as lock:
        info = read_lock(tmp_path)
        assert (info.pid, info.command, info.started_at) == (111, "run --max-requests 5", NOW)
        assert lock.acquired
    assert read_lock(tmp_path) is None
    assert not lock_path(tmp_path).exists()


def test_lock_is_released_on_error(tmp_path):
    with pytest.raises(RuntimeError), make_lock(tmp_path):
        raise RuntimeError("plantage")
    assert read_lock(tmp_path) is None


def test_second_command_is_refused_while_the_first_runs(tmp_path):
    with make_lock(tmp_path, "run"):
        with pytest.raises(LockHeldError, match="« run », PID 111"):
            make_lock(tmp_path, "refresh", pid=222).acquire()
        assert read_lock(tmp_path).pid == 111  # le verrou du premier est intact


def test_stale_lock_of_a_dead_process_is_replaced(tmp_path):
    write_lock(tmp_path, pid=222)
    with make_lock(tmp_path, pid=333, alive_fn=dead):
        assert read_lock(tmp_path).pid == 333


def test_old_lock_is_stale_even_if_the_pid_was_reused(tmp_path):
    write_lock(tmp_path, pid=222, started=NOW - STALE_AFTER - dt.timedelta(minutes=1))
    with make_lock(tmp_path, pid=333, alive_fn=alive):
        assert read_lock(tmp_path).pid == 333


def test_lock_of_another_machine_is_not_judged_by_its_pid(tmp_path):
    write_lock(tmp_path, pid=222, host="autre-machine")
    with pytest.raises(LockHeldError):
        make_lock(tmp_path, pid=333, alive_fn=dead).acquire()


def test_unreadable_lock_is_held_for_a_minute_then_replaced(tmp_path):
    path = lock_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")  # créé, pas encore écrit
    mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
    with pytest.raises(LockHeldError):
        make_lock(tmp_path, now=mtime + dt.timedelta(seconds=10)).acquire()
    with make_lock(tmp_path, now=mtime + dt.timedelta(minutes=5)):
        assert read_lock(tmp_path).pid == 111


def test_waiting_command_gets_the_lock_when_it_is_released(tmp_path):
    write_lock(tmp_path, pid=222)
    clock = {"now": NOW}
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += dt.timedelta(seconds=seconds)
        if len(sleeps) == 3:
            lock_path(tmp_path).unlink()  # le refresh se termine

    lock = CollectLock(tmp_path, "t60", pid=333, alive=alive, now=lambda: clock["now"], sleep=sleep,
                       wait=dt.timedelta(minutes=10), poll_seconds=30)
    with lock:
        assert read_lock(tmp_path).pid == 333
    assert sleeps == [30, 30, 30]


def test_waiting_gives_up_after_the_deadline(tmp_path):
    write_lock(tmp_path, pid=222)
    clock = {"now": NOW}

    def sleep(seconds):
        clock["now"] += dt.timedelta(seconds=seconds)

    lock = CollectLock(tmp_path, "t60", pid=333, alive=alive, now=lambda: clock["now"], sleep=sleep,
                       wait=dt.timedelta(minutes=2), poll_seconds=30)
    with pytest.raises(LockHeldError):
        lock.acquire()
    assert clock["now"] - NOW == dt.timedelta(minutes=2)


def test_release_never_removes_someone_elses_lock(tmp_path):
    lock = make_lock(tmp_path, pid=111)
    lock.acquire()
    write_lock(tmp_path, pid=999)  # remplacé entre-temps (cas théorique)
    lock.release()
    assert read_lock(tmp_path).pid == 999


def test_is_stale_rules():
    host = socket.gethostname()
    assert not is_stale(LockInfo(5, "run", NOW, host), NOW, alive)
    assert is_stale(LockInfo(5, "run", NOW, host), NOW, dead)
    assert is_stale(LockInfo(5, "run", NOW - STALE_AFTER - dt.timedelta(seconds=1), host), NOW, alive)


def test_pid_alive_on_this_machine():
    assert pid_alive(os.getpid())
    assert not pid_alive(0)
    assert not pid_alive(2**31 - 2)  # PID qui n'existe pas
