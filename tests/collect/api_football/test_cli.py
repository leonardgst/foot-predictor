"""Commandes du collecteur, avec une fausse API (aucun appel réseau)."""
from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.collect.api_football import cli
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.rawstore import manifest
from foot_predictor.rawstore.backup import verify

from .fakes import FakeApi, FakeClock, FakeSession, fixture_item, load_real_fixtures, make_client

REAL_IDS = sorted(f["fixture"]["id"] for f in load_real_fixtures())


@pytest.fixture
def api():
    fake = FakeApi()
    fake.listings[(39, 2015)] = [fixture_item(i) for i in REAL_IDS]
    fake.listings[(45, 2015)] = [fixture_item(6000, league=45)]
    fake.listings[(999, 2015)] = [fixture_item(7000, league=999)]
    return fake


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "collecte.yaml"
    path.write_text(
        "reserve: 500\n"
        "tiers:\n"
        "  P1:\n"
        "    blocks:\n"
        "      - {name: top5, kind: league, leagues: [39], seasons: {first: 2015, last: 2015},\n"
        "         endpoints: [fixtures_list, fixtures_detail]}\n"
        "      - {name: coupes, kind: cup, leagues: [45, 999], seasons: {first: 2015, last: 2015},\n"
        "         endpoints: [fixtures_list]}\n",
        encoding="utf-8",
    )
    return path


def run_cli(tmp_path, config_file, api, *args):
    raw_dir = tmp_path / "raw"
    sessions = []

    def factory(config, max_requests):
        session = FakeSession(handler=api)
        sessions.append(session)
        return make_client(session, FakeClock(), reserve=config.reserve, max_requests=max_requests)

    code = cli.main(["--raw-dir", str(raw_dir), "--config", str(config_file), *args], client_factory=factory)
    calls = [c for s in sessions for c in s.calls]
    return code, raw_dir, calls


def test_coverage_writes_table_without_account_details(tmp_path, config_file, api, capsys):
    output = tmp_path / "couverture.md"
    code, raw_dir, calls = run_cli(tmp_path, config_file, api, "coverage", "--output", str(output))

    assert code == 0
    assert [c[0] for c in calls] == ["/status", "/leagues"]
    text = output.read_text(encoding="utf-8")
    assert "Premier League" in text and "FA Cup" in text
    assert "| P1 | coupes | 999 | ⚠️ absent de /leagues" in text
    assert "| 2013 | 2013-08-01 | 2014-05-31 | oui | non |" in text  # compositions absentes en 2013
    assert "test@example.org" not in text
    assert "Identifiants absents de /leagues : [999]" in capsys.readouterr().out
    # La réponse /leagues est stockée : le plan s'en sert ensuite.
    assert list((raw_dir / "api_football" / "leagues").glob("all__*.json.gz"))


def test_plan_then_dry_run_then_run_then_status(tmp_path, config_file, api, capsys):
    code, raw_dir, calls = run_cli(tmp_path, config_file, api, "plan", "--palier", "P1")
    assert code == 0 and calls == []
    assert "Palier P1 : 3 tâches ajoutées" in capsys.readouterr().out

    code, _, calls = run_cli(tmp_path, config_file, api, "run", "--dry-run")
    assert code == 0 and calls == []
    assert "Simulation" in capsys.readouterr().out

    code, _, calls = run_cli(tmp_path, config_file, api, "run", "--max-requests", "20")
    assert code == 0
    assert len(calls) == 5  # /status, 3 listes, 1 lot de détails
    assert "Requêtes envoyées : 5" in capsys.readouterr().out

    code, _, calls = run_cli(tmp_path, config_file, api, "status")
    out = capsys.readouterr().out
    assert code == 0 and calls == []
    assert "P1 : 4/4 (100.0 %)" in out
    assert "fixtures_detail" in out


def test_status_quota_line():
    today = dt.date(2026, 10, 2)
    entries = [
        {"timestamp": "2026-10-01T22:00:00+00:00", "quota_remaining_day": 100},
        {"timestamp": "2026-10-02T08:30:00+00:00", "quota_remaining_day": 6500},
        {"timestamp": "2026-10-02T08:31:00+00:00", "quota_remaining_day": None},
    ]
    assert "6500" in cli.quota_line(entries, today) and "08:30" in cli.quota_line(entries, today)
    assert "quota plein" in cli.quota_line(entries[:1], today)
    assert "inconnu" in cli.quota_line([], today)


def test_status_lists_problems_and_deferred(tmp_path, config_file, api, capsys):
    api.listings[(39, 2015)].append(fixture_item(5000, status="PST"))
    api.empty.add(("/fixtures", (("league", 45), ("season", 2015))))
    run_cli(tmp_path, config_file, api, "plan", "--palier", "P1")
    run_cli(tmp_path, config_file, api, "run")
    capsys.readouterr()

    run_cli(tmp_path, config_file, api, "status")
    out = capsys.readouterr().out
    assert "suspect" in out and "results = 0" in out
    assert "Matchs non terminaux mis de côté : 1 (PST 1)" in out


def test_requeue_command(tmp_path, config_file, api, capsys):
    api.empty.add(("/fixtures", (("league", 45), ("season", 2015))))
    run_cli(tmp_path, config_file, api, "plan", "--palier", "P1")
    run_cli(tmp_path, config_file, api, "run")

    code, raw_dir, _ = run_cli(tmp_path, config_file, api, "requeue", "--status", "suspect")
    assert code == 0
    assert "1 tâche(s) suspect remise(s) en pending" in capsys.readouterr().out
    with WorkQueue.in_raw_dir(raw_dir) as queue:
        assert [t.params for t in queue.list_pending()] == [{"league": 45, "season": 2015}]


def test_backup_command_verifies_sha256(tmp_path, config_file, api, capsys):
    run_cli(tmp_path, config_file, api, "plan", "--palier", "P1")
    run_cli(tmp_path, config_file, api, "run")
    dest = tmp_path / "externe"

    code, _, _ = run_cli(tmp_path, config_file, api, "backup", "--dest", str(dest))
    assert code == 0
    assert "Sauvegarde vérifiée." in capsys.readouterr().out

    # Une copie corrompue est détectée (code retour 1).
    corrupted = sorted(dest.rglob("*.json.gz"))[0]
    corrupted.write_bytes(b"x")
    dest2 = tmp_path / "externe2"
    code, raw_dir, _ = run_cli(tmp_path, config_file, api, "backup", "--dest", str(dest2))
    assert code == 0  # l'original est sain
    assert not verify(dest).ok

    # Destination non vide : refus.
    code, _, _ = run_cli(tmp_path, config_file, api, "backup", "--dest", str(dest))
    assert code == 2


def test_rebuild_manifest_command(tmp_path, config_file, api, capsys):
    run_cli(tmp_path, config_file, api, "plan", "--palier", "P1")
    code, raw_dir, _ = run_cli(tmp_path, config_file, api, "run")
    original = manifest.read_entries(raw_dir, "api_football")

    code, _, _ = run_cli(tmp_path, config_file, api, "rebuild-manifest")
    assert code == 0
    rebuilt_file = next((raw_dir / "_manifest").glob("api_football.rebuilt-*.jsonl"))
    rebuilt = manifest.read_manifest_file(rebuilt_file)
    strip = lambda e: {k: v for k, v in e.items() if k != "duration_ms"}  # noqa: E731
    assert sorted(map(strip, rebuilt), key=lambda e: e["file"]) == sorted(map(strip, original), key=lambda e: e["file"])


def test_missing_key_is_reported(tmp_path, config_file, monkeypatch, capsys):
    class NoKey:
        api_football_key = None

    monkeypatch.setattr("foot_predictor.config.get_settings", lambda: NoKey())
    code = cli.main(["--raw-dir", str(tmp_path / "raw"), "--config", str(config_file), "run"])
    assert code == 2
    assert "API_FOOTBALL_KEY absente" in capsys.readouterr().err
