"""Journal T-60 (commandes `t60` et `t60-report`) et verrou de la CLI, sans aucun appel réseau."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from foot_predictor.collect.api_football import cli
from foot_predictor.collect.api_football.plan import fixture_ids_in_manifest
from foot_predictor.collect.api_football.t60 import (
    Match,
    T60Collector,
    compare_lineups,
    comparison_lines,
    day_matches,
    expected_requests,
    has_lineups,
)
from foot_predictor.rawstore import manifest, store
from foot_predictor.rawstore.lock import lock_path

from .fakes import FakeClock, FakeResponse, FakeSession, make_client, ok, status_body

DAY = dt.date(2026, 10, 10)
NOON = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc)


class DayClock(FakeClock):
    """Horloge simulée : une pause fait avancer l'heure UTC d'autant."""

    def __init__(self, start: dt.datetime) -> None:
        super().__init__()
        self.utc = start

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        self.utc += dt.timedelta(seconds=seconds)


def item(fid: int, kickoff: dt.datetime, *, league: int = 39, status: str = "NS", lineups: bool = False,
         home: list[int] | None = None, away: list[int] | None = None) -> dict:
    """Élément de /fixtures, sans score (le T-60 n'en lit jamais)."""
    def lineup(team: int, ids: list[int]) -> dict:
        return {"team": {"id": team}, "startXI": [{"player": {"id": pid}} for pid in ids], "substitutes": []}

    home = home or [fid * 100 + i for i in range(11)]
    away = away or [fid * 100 + 50 + i for i in range(11)]
    return {
        "fixture": {"id": fid, "timestamp": int(kickoff.timestamp()), "date": kickoff.isoformat(),
                    "status": {"short": status}},
        "league": {"id": league, "season": 2026},
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "lineups": [lineup(1, home), lineup(2, away)] if lineups else [],
    }


class DayApi:
    """Journée simulée : A et B à 14:00, C à 17:00 (compositions jamais publiées),
    D d'une autre compétition, E déjà commencé. A et B publient leurs
    compositions 30 minutes avant le coup d'envoi."""

    def __init__(self, clock: DayClock) -> None:
        self.clock = clock
        self.kickoffs = {1: NOON + dt.timedelta(hours=2), 2: NOON + dt.timedelta(hours=2),
                         3: NOON + dt.timedelta(hours=5), 4: NOON + dt.timedelta(hours=2),
                         5: NOON - dt.timedelta(hours=1)}

    def __call__(self, endpoint: str, params: dict) -> FakeResponse:
        if endpoint == "/status":
            return FakeResponse(200, status_body())
        if "date" in params:
            assert params == {"date": "2026-10-10", "timezone": "UTC"}
            return ok([item(1, self.kickoffs[1]), item(2, self.kickoffs[2]), item(3, self.kickoffs[3]),
                       item(4, self.kickoffs[4], league=999), item(5, self.kickoffs[5], status="1H")])
        ids = [int(i) for i in params["ids"].split("-")]
        now = self.clock.utc
        return ok([item(i, self.kickoffs[i], lineups=(i != 3 and now >= self.kickoffs[i] - dt.timedelta(minutes=30)))
                   for i in ids])


def collect(tmp_path, max_requests=80):
    clock = DayClock(NOON - dt.timedelta(hours=3))
    session = FakeSession(handler=DayApi(clock))
    client = make_client(session, clock, max_requests=max_requests)
    report = T60Collector(client, tmp_path, DAY, [39, 140], now=lambda: clock.utc, sleep=clock.sleep).run()
    return report, session.calls


def test_t60_follows_top5_matches_until_lineups_or_kickoff(tmp_path):
    report, calls = collect(tmp_path)

    assert report.matches == 3  # D (autre compétition) et E (commencé) ignorés
    assert sorted(report.announced) == [1, 2] and report.missed == [3] and report.stop_reason is None
    polls = [p["ids"] for e, p in calls if "ids" in p]
    # A et B : T-40, T-35, T-30 (compositions publiées) ; C : T-40 à T-5, 8 passages.
    assert polls == ["1-2"] * 3 + ["3"] * 8
    assert report.requests == 1 + 3 + 8
    assert all(when < NOON + dt.timedelta(hours=2) for when in report.announced.values())


def test_t60_responses_are_stored_as_daily_files_and_never_count_as_details(tmp_path):
    collect(tmp_path)

    entries = manifest.read_entries(tmp_path, "api_football")
    assert entries and all(e["file"].startswith("api_football/daily/2026-10-10/") for e in entries)
    assert any(e.get("fixture_ids") == [1, 2] for e in entries)  # champ habituel du journal...
    assert fixture_ids_in_manifest(tmp_path) == set()  # ... ignoré par le planificateur


def test_t60_stops_cleanly_at_the_request_cap(tmp_path):
    report, calls = collect(tmp_path, max_requests=3)
    assert len(calls) == 3 and "maximal" in report.stop_reason
    assert report.announced == {}


def test_day_matches_keeps_only_not_started_matches_of_followed_leagues():
    body = {"response": [item(1, NOON), item(2, NOON, league=999), item(3, NOON, status="PST"),
                         item(4, NOON - dt.timedelta(hours=1))]}
    assert [m.fixture_id for m in day_matches(body, [39])] == [4, 1]  # triés par heure


def test_expected_requests_shares_batches_between_overlapping_windows():
    lead, interval = dt.timedelta(minutes=40), dt.timedelta(minutes=5)
    same_time = [Match(i, 39, NOON) for i in range(25)]
    assert expected_requests(same_time, lead, interval) == 1 + 8 * 2  # 25 matchs : 2 lots par passage
    staggered = [Match(1, 39, NOON), Match(2, 39, NOON + dt.timedelta(minutes=15))]
    assert expected_requests(staggered, lead, interval) == 1 + 11  # fenêtres fusionnées : 11 passages
    assert expected_requests([], lead, interval) == 1


def write(raw, rel_dir, stem, response, when):
    envelope = store.build_envelope(endpoint="/fixtures", params={}, fetched_at=when, http_status=200,
                                    headers_quota={}, body={"errors": [], "response": response})
    store.write_envelope(raw, rel_dir, stem, envelope, when)


def test_t60_report_compares_announced_and_final_starters(tmp_path):
    kickoff = NOON + dt.timedelta(hours=2)
    starters = list(range(100, 111))
    changed = starters[:10] + [999]  # un joueur remplacé à l'échauffement
    # Annonces : une réponse sans compositions, puis avec ; A dans deux lots différents.
    write(tmp_path, "api_football/daily/2026-10-10/lineups", "aaa", [item(1, kickoff)], NOON)
    write(tmp_path, "api_football/daily/2026-10-10/lineups", "zzz",
          [item(1, kickoff, lineups=True, home=starters), item(2, kickoff, lineups=True)], NOON + dt.timedelta(minutes=5))
    write(tmp_path, "api_football/daily/2026-10-10/lineups", "bbb",
          [item(1, kickoff, lineups=True, home=starters)], NOON + dt.timedelta(minutes=10))
    # Détail d'après-match : seulement pour A (B pas encore collecté).
    final = item(1, kickoff, status="FT", lineups=True, home=changed)
    write(tmp_path, "api_football/fixtures_detail/league=39/season=2026", "lot", [final], NOON + dt.timedelta(days=1))

    comparisons, without_detail = compare_lineups(tmp_path)

    assert without_detail == 1
    [comparison] = comparisons
    assert (comparison.fixture_id, comparison.compared, comparison.identical) == (1, 22, 21)
    assert comparison.differences == [(1, 110, 999)]
    lines = "\n".join(comparison_lines(comparisons, without_detail))
    assert "Titulaires comparés : 22 ; identiques : 21 (95.45 %)" in lines
    assert "110" not in lines and "999" not in lines  # aucun identifiant de joueur dans le bilan


def test_has_lineups_needs_two_full_elevens():
    assert has_lineups(item(1, NOON, lineups=True))
    assert not has_lineups(item(1, NOON))
    assert not has_lineups(item(1, NOON, lineups=True, home=list(range(10))))


# --- verrou dans la CLI --------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "collecte.yaml"
    path.write_text("reserve: 500\ntiers:\n  P1:\n    blocks:\n"
                    "      - {name: top5, kind: league, leagues: [39], seasons: {first: 2026, last: 2026},\n"
                    "         endpoints: [fixtures_list, fixtures_detail]}\n", encoding="utf-8")
    return path


def hold_lock(raw, pid):
    import socket

    path = lock_path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "command": "run", "host": socket.gethostname(),
                                "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}), encoding="utf-8")


def test_write_commands_refuse_a_held_lock_but_dry_runs_do_not(tmp_path, config_file, capsys):
    import os

    raw = tmp_path / "raw"
    hold_lock(raw, os.getpid())  # processus vivant : ce test lui-même
    base = ["--raw-dir", str(raw), "--config", str(config_file)]

    def no_client(config, max_requests):
        raise AssertionError("aucune requête attendue")

    assert cli.main([*base, "run", "--max-requests", "5"], client_factory=no_client) == 3
    assert "occupé" in capsys.readouterr().err
    assert cli.main([*base, "run", "--dry-run"], client_factory=no_client) == 0
    assert cli.main([*base, "lock-status"]) == 1
    assert "TENU" in capsys.readouterr().out


def test_lock_status_and_release_after_a_command(tmp_path, config_file, capsys):
    raw = tmp_path / "raw"
    base = ["--raw-dir", str(raw), "--config", str(config_file)]
    assert cli.main([*base, "plan", "--palier", "P1"]) == 0
    assert not lock_path(raw).exists()  # libéré à la fin de la commande
    assert cli.main([*base, "lock-status"]) == 0
    assert "libre" in capsys.readouterr().out
    hold_lock(raw, 2**31 - 2)  # processus disparu
    assert cli.main([*base, "lock-status"]) == 0
    assert "périmé" in capsys.readouterr().out


def test_t60_command_runs_under_the_lock_with_its_cap(tmp_path, config_file, capsys):
    raw = tmp_path / "raw"
    clock = DayClock(NOON - dt.timedelta(hours=3))
    seen_locked = []

    def handler(endpoint, params):
        seen_locked.append(lock_path(raw).exists())
        return ok([])  # journée sans match

    def factory(config, max_requests):
        assert max_requests == 7
        return make_client(FakeSession(handler=handler), clock, max_requests=max_requests)

    code = cli.main(["--raw-dir", str(raw), "--config", str(config_file), "t60", "--date", "2026-10-10",
                     "--max-requests", "7"], client_factory=factory)

    assert code == 0 and seen_locked == [True]
    assert "0 match(s) du top 5 suivis" in capsys.readouterr().out
    assert not lock_path(raw).exists()
