"""Contrôle qualité du brut (rapport G.9), sur les 5 matchs réels de
`tests/fixtures/api_football/`, rangés dans un dossier brut temporaire.

Aucun appel réseau, aucune base de données.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pytest

from foot_predictor.collect.api_football import tasks
from foot_predictor.collect.api_football.coverage import coverage_from_body
from foot_predictor.collect.api_football.plan import parse_config
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.quality import raw_check
from foot_predictor.quality.raw_check import BLOCK, OK, WATCH, RawChecker
from foot_predictor.rawstore import manifest, store

FIXTURES_FILE = Path(__file__).resolve().parents[1] / "fixtures" / "api_football" / "payloads_fixtures.jsonl"
T0 = dt.datetime(2026, 10, 8, 8, 0, 0, tzinfo=dt.timezone.utc)
NOW = dt.datetime(2026, 10, 8, 20, 0, 0, tzinfo=dt.timezone.utc)

CONFIG = {
    "tiers": {
        "P1": {"blocks": [
            {"name": "top5", "kind": "league", "leagues": [39], "seasons": {"first": 2015, "last": 2015},
             "endpoints": ["fixtures_list", "fixtures_detail", "players"]},
            {"name": "coupes", "kind": "cup", "leagues": [45], "seasons": {"first": 2015, "last": 2015},
             "endpoints": ["fixtures_list", "fixtures_detail"], "detail_teams_from": "P1"},
        ]},
        "P2": {"blocks": [
            {"name": "ancien", "kind": "league", "leagues": [39], "seasons": {"last": 2014, "requires_coverage": "fixtures.lineups"},
             "endpoints": ["fixtures_list", "fixtures_detail"]},
        ]},
    }
}
FLAGS = {"fixtures": {"events": True, "lineups": True, "statistics_fixtures": True, "statistics_players": True},
         "players": True, "injuries": True, "standings": True}


def load_real_fixtures() -> list[dict]:
    with open(FIXTURES_FILE, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def list_item(fixture_id: int, home: int, away: int, status: str = "FT", round_: str = "Regular Season - 1") -> dict:
    return {
        "fixture": {"id": fixture_id, "date": "2015-08-15T14:00:00+00:00", "status": {"short": status}},
        "league": {"round": round_},
        "teams": {"home": {"id": home, "name": f"Équipe {home}"}, "away": {"id": away, "name": f"Équipe {away}"}},
        "goals": {"home": 0, "away": 0},
    }


def listing_of(details: list[dict]) -> list[dict]:
    """Ce que /fixtures?league&season renvoie : le détail sans compositions ni événements."""
    return [{key: item[key] for key in ("fixture", "league", "teams", "goals", "score")} for item in details]


def profiles_of(details: list[dict]) -> list[dict]:
    """Un profil /players par joueur ayant des statistiques dans ces matchs."""
    profiles = {}
    for item in details:
        for team in item["players"]:
            for entry in team["players"]:
                player = entry["player"]
                first, _, last = player["name"].partition(" ")
                profiles[player["id"]] = {"player": {
                    "id": player["id"], "name": player["name"], "firstname": first, "lastname": last,
                    "birth": {"date": f"1990-01-{player['id'] % 28 + 1:02d}"},
                }}
    return list(profiles.values())


class RawBuilder:
    """Dossier brut conforme à ADR-0003 : fichiers, journal et file de travail."""

    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir
        self.clock = T0
        self.queue = WorkQueue.in_raw_dir(raw_dir)

    def write(self, rel_dir: str, stem: str, body: dict, endpoint: str = "/fixtures", params: dict | None = None) -> store.StoredFile:
        self.clock += dt.timedelta(seconds=1)
        envelope = store.build_envelope(endpoint=endpoint, params=params or {}, fetched_at=self.clock,
                                        http_status=200, headers_quota={}, body=body)
        stored = store.write_envelope(self.raw_dir, rel_dir, stem, envelope, self.clock)
        manifest.append_entry(self.raw_dir, "api_football",
                              manifest.entry_for_stored(envelope, stored, source="api_football", duration_ms=1))
        return stored

    def leagues(self, flags_by_league: dict[int, dict]) -> None:
        response = [{"league": {"id": league, "name": f"Compétition {league}", "type": "League"},
                     "country": {"name": "England"},
                     "seasons": [{"year": 2015, "coverage": flags}]}
                    for league, flags in flags_by_league.items()]
        task = tasks.leagues_task("P0")
        self.write(task.rel_dir, task.stem, body(response), endpoint="/leagues")

    def fixtures_list(self, league: int, items: list[dict], tier: str = "P1") -> None:
        task = tasks.fixtures_list_task(tier, league, 2015)
        self.write(task.rel_dir, task.stem, body(items), params=task.params)
        self.done(task)

    def details(self, league: int, items: list[dict], tier: str = "P1") -> store.StoredFile:
        task = tasks.fixtures_detail_task(tier, league, 2015, [item["fixture"]["id"] for item in items])
        stored = self.write(task.rel_dir, task.stem, body(items), params=task.params)
        self.done(task)
        return stored

    def profiles(self, league: int, response: list[dict], page: int = 1, total: int = 1) -> None:
        task = tasks.players_task("P1", league, 2015, page)
        self.write(task.rel_dir, task.stem, body(response, paging={"current": page, "total": total}),
                   endpoint="/players", params=task.params)
        self.done(task)

    def done(self, task: tasks.Task) -> None:
        if self.queue.add([task]):  # une recollecte réutilise la tâche existante
            queued = next(t for t in self.queue.list_pending() if t.params == task.params and t.task_type == task.task_type)
            self.queue.mark_done(queued.id, "x")


def body(response: list, paging: dict | None = None) -> dict:
    return {"errors": [], "results": len(response), "paging": paging or {"current": 1, "total": 1}, "response": response}


@pytest.fixture
def config():
    return parse_config(copy.deepcopy(CONFIG))


@pytest.fixture
def real():
    return load_real_fixtures()


def build_clean(raw_dir: Path, real: list[dict]) -> RawBuilder:
    builder = RawBuilder(raw_dir)
    builder.leagues({39: FLAGS, 45: FLAGS})
    builder.fixtures_list(39, listing_of(real) + [list_item(999001, 33, 47, status="NS")])
    builder.details(39, real)
    builder.profiles(39, profiles_of(real))
    builder.fixtures_list(45, [])
    return builder


def run_check(raw_dir: Path, config, tiers=("P1",)):
    return RawChecker(raw_dir, config, list(tiers)).run(now=NOW)


def status_of(result, label_start: str) -> str:
    return next(line.status for line in result.checks if line.label.startswith(label_start))


# --- dossier sain --------------------------------------------------------------------


def test_clean_raw_dir_passes_every_check_but_the_expected_count(tmp_path, config, real):
    raw = tmp_path / "raw"
    build_clean(raw, real).queue.close()

    result = run_check(raw, config)

    season = next(s for s in result.seasons if s.scope.league == 39)
    assert (season.listed, season.regular, season.teams, season.expected) == (6, 6, 10, 90)
    assert (season.to_detail, season.detailed) == (5, 5)
    assert all(rate.ok == rate.total > 0 for rate in season.rates.values())
    assert (season.goals.ok, season.goals.total) == (5, 5)
    assert season.profiles == "1/1"
    # 6 matchs pour 10 équipes : le nombre attendu (90) n'est pas atteint, rien d'autre.
    assert status_of(result, "Matchs listés") == WATCH
    for label in ("Matchs terminés", "Compositions", "players et events", "Buts", "player.id", "Titulaires",
                  "Un identifiant", "Doublons", "Minutes", "Note", "Intégrité", "Tâches"):
        assert status_of(result, label) == OK, label
    assert result.verdict == WATCH
    # « S. Romero » (composition) et « Sergio Romero » (statistiques) : variante tolérée, pas un conflit.
    assert result.names[884].keys() >= {"S. Romero", "Sergio Romero"}
    assert result.name_conflicts == []


def test_cup_details_are_expected_only_for_tracked_teams(tmp_path, config, real):
    raw = tmp_path / "raw"
    builder = build_clean(raw, real)
    # Seconde liste de coupe, plus récente : c'est elle qui compte.
    builder.fixtures_list(45, [list_item(700001, 33, 5000, round_="3rd Round"),
                               list_item(700002, 5001, 5002, round_="3rd Round")])
    builder.queue.close()

    result = run_check(raw, config)

    cup = next(s for s in result.seasons if s.scope.league == 45)
    assert cup.expected is None  # pas de nombre attendu pour une coupe
    assert (cup.to_detail, cup.detailed) == (1, 0)
    assert [i.fixture for i in result.issues["missing_details"]] == [700001]
    assert status_of(result, "Matchs terminés") == BLOCK


def test_uncovered_checks_are_skipped(tmp_path, config, real):
    raw = tmp_path / "raw"
    builder = RawBuilder(raw)
    no_events = copy.deepcopy(FLAGS)
    no_events["fixtures"]["events"] = False
    builder.leagues({39: no_events, 45: FLAGS})
    stripped = copy.deepcopy(real)
    for item in stripped:
        item["events"] = []
    builder.fixtures_list(39, listing_of(stripped))
    builder.details(39, stripped)
    builder.queue.close()

    result = run_check(raw, config)

    season = next(s for s in result.seasons if s.scope.league == 39)
    assert season.rates["events"].total == 0
    assert raw_check._rate_cell(season, "events") == "n. c."
    assert result.issues["players_events"] == []


# --- anomalies ---------------------------------------------------------------------------


def test_anomalies_are_detected_and_listed(tmp_path, config, real):
    raw = tmp_path / "raw"
    broken = copy.deepcopy(real)
    a, b, c, d, e = broken
    del a["lineups"][0]["startXI"][10]  # 10 titulaires
    b["lineups"][1]["startXI"][0]["player"]["pos"] = "D"  # plus de gardien titulaire
    b_stats = b["players"][1]["players"]
    for entry in b_stats:
        if entry["player"]["id"] == b["lineups"][1]["startXI"][0]["player"]["id"]:
            entry["statistics"][0]["games"]["position"] = "D"
    c["players"][0]["players"][0]["statistics"][0]["games"]["rating"] = "2.5"
    c["players"][0]["players"][1]["statistics"][0]["games"]["minutes"] = 140
    c["lineups"][0]["substitutes"][0]["player"]["id"] = None
    d["events"].append({"type": "Goal", "detail": "Normal Goal", "team": {"id": d["teams"]["home"]["id"]},
                        "player": {"id": 1, "name": "X. Test"}, "assist": {"id": None, "name": None}})
    e["lineups"][0]["startXI"][0]["player"]["name"] = "D. Blind"  # nom incompatible avec l'identifiant
    e["players"] = []

    builder = RawBuilder(raw)
    builder.leagues({39: FLAGS, 45: FLAGS})
    builder.fixtures_list(39, listing_of(broken) + [list_item(999002, 33, 47)])  # terminé, sans détail
    stored = builder.details(39, broken)
    profiles = profiles_of(real)
    missing_starter = a["lineups"][1]["startXI"][5]["player"]["id"]
    profiles = [p for p in profiles if p["player"]["id"] != missing_starter]
    twin = copy.deepcopy(profiles[0])
    twin["player"]["id"] = 424242
    profiles.append(twin)
    builder.profiles(39, profiles)
    builder.fixtures_list(45, [])
    failed = tasks.team_task("P1", "coachs", 33)
    suspect = tasks.team_task("P1", "transfers", 33)
    builder.queue.add([failed, suspect])
    for queued in builder.queue.list_pending():
        if queued.task_type == "coachs":
            builder.queue.mark_failed(queued.id, "errors : {'plan': 'x'}")
        else:
            builder.queue.mark_suspect(queued.id, "results = 0", "y")
    builder.queue.close()
    # Fichier modifié après coup : son sha256 ne correspond plus au journal.
    corrupted = raw / next((raw / "api_football" / "fixtures_list" / "league=45").glob("*.json.gz")).relative_to(raw)
    corrupted.write_bytes(store.encode_envelope({"body": {"errors": [], "response": []}}))

    result = run_check(raw, config)
    issues = {family: [i.text for i in items] for family, items in result.issues.items()}

    assert [i.fixture for i in result.issues["missing_details"]] == [999002]
    assert any("10 titulaire(s)" in text for text in issues["lineups"])
    assert any("0 gardien(s)" in text for text in issues["lineups"])
    assert issues["players_events"] == ["players vide ou incomplet"]
    assert issues["goals"] == ["score 4-2, buts dans events 5-2"]
    assert any("note 2.5" in text for text in issues["ratings"])
    assert any("140 minutes" in text for text in issues["minutes"])
    assert any(text.startswith("substitutes") for text in issues["missing_ids"])
    assert any(f"({missing_starter}) sans profil" in text for text in issues["not_in_profiles"])
    conflict_ids = [player_id for player_id, _ in result.name_conflicts]
    assert e["lineups"][0]["startXI"][0]["player"]["id"] in conflict_ids
    assert [ids for _, ids in result.duplicates] == [sorted([profiles[0]["player"]["id"], 424242])]
    assert result.journal.mismatched == [corrupted.relative_to(raw).as_posix()]
    assert [p["status"] for p in result.journal.problems] == ["failed", "suspect"]

    assert status_of(result, "Matchs terminés") == BLOCK
    assert status_of(result, "Intégrité") == BLOCK
    assert status_of(result, "Tâches") == BLOCK
    for label in ("Compositions", "players et events", "Buts", "player.id", "Titulaires", "Un identifiant",
                  "Doublons", "Minutes", "Note"):
        assert status_of(result, label) == WATCH, label
    assert result.verdict == BLOCK
    assert stored.path.exists()

    # Le résumé versionné ne contient que des compteurs ; les listes nominatives vont dans les détails.
    summary = raw_check.render_summary(result)
    details = raw_check.render_details(result)
    player_names = {entry["player"]["name"] for item in broken for team in item["players"] for entry in team["players"]}
    player_names |= {entry["player"]["name"] for item in broken for lineup in item["lineups"]
                     for entry in lineup["startXI"] + lineup["substitutes"]}
    assert [name for name in player_names if name in summary] == []
    anomalous_ids = {424242, missing_starter, *conflict_ids}
    assert [pid for pid in anomalous_ids if re.search(rf"\b{pid}\b", summary)] == []
    assert "D. Blind" in details and "424242" in details and str(missing_starter) in details
    assert "999002" in details and "999002" not in summary  # match sans détail : listé dans les détails seulement
    # Anomalies par championnat-saison : liste, sans détail, compos, players/events, buts, sans id,
    # hors profils, minutes, notes.
    assert "| P1 | Compétition 39 (39) | 2015 | 1 | 1 | 2 | 1 | 1 | 1 | 1 | 1 | 1 |" in summary
    assert "failed coachs : 1" in summary and "team" not in summary


def test_most_recent_detail_version_wins(tmp_path, config, real):
    raw = tmp_path / "raw"
    builder = RawBuilder(raw)
    builder.leagues({39: FLAGS, 45: FLAGS})
    builder.fixtures_list(39, listing_of(real))
    broken = copy.deepcopy(real)
    broken[0]["lineups"] = []
    builder.details(39, broken)
    builder.details(39, real)  # recollecte du même lot : nouvelle version horodatée
    builder.queue.close()

    result = run_check(raw, config)

    season = next(s for s in result.seasons if s.scope.league == 39)
    assert (season.to_detail, season.detailed) == (5, 5)
    assert result.issues["lineups"] == []


def test_awarded_matches_are_excluded_from_detail_checks(tmp_path, config, real):
    raw = tmp_path / "raw"
    awarded = copy.deepcopy(real[0])
    awarded["fixture"]["status"]["short"] = "AWD"
    awarded["lineups"], awarded["events"], awarded["players"] = [], [], []
    builder = RawBuilder(raw)
    builder.leagues({39: FLAGS, 45: FLAGS})
    builder.fixtures_list(39, listing_of([awarded]))
    builder.details(39, [awarded])
    builder.queue.close()

    season = next(s for s in run_check(raw, config).seasons if s.scope.league == 39)

    assert (season.detailed, season.awarded) == (1, 1)
    assert all(rate.total == 0 for rate in season.rates.values())


def test_missing_list_and_unreadable_file_are_blocking(tmp_path, config, real):
    raw = tmp_path / "raw"
    builder = RawBuilder(raw)
    builder.leagues({39: FLAGS, 45: FLAGS})
    builder.fixtures_list(39, listing_of(real))
    stored = builder.details(39, real)
    builder.queue.close()
    stored.path.write_bytes(b"pas du gzip")

    result = run_check(raw, config)

    assert status_of(result, "Matchs listés") == BLOCK  # liste de la coupe 45 absente
    assert any("liste de matchs absente" in i.text for i in result.issues["lists"])
    assert len(result.unreadable) == 1
    assert status_of(result, "Intégrité") == BLOCK


# --- fonctions unitaires -------------------------------------------------------------------


def test_goals_from_events_handles_own_goals_missed_penalties_and_shootouts():
    events = [
        {"type": "Goal", "detail": "Own Goal", "team": {"id": 1}},
        {"type": "Goal", "detail": "Penalty", "team": {"id": 2}},
        {"type": "Goal", "detail": "Missed Penalty", "team": {"id": 2}},
        {"type": "Goal", "detail": "Penalty", "team": {"id": 1}, "comments": "Penalty Shootout"},
        {"type": "Card", "detail": "Yellow Card", "team": {"id": 1}},
    ]
    assert raw_check.goals_from_events(events, 1, 2) == (1, 1)


def test_expected_regular_season_ignores_playoffs():
    items = [list_item(i, home, away) for i, (home, away) in enumerate(
        [(1, 2), (2, 1), (1, 3), (3, 1), (2, 3), (3, 2)])]
    items.append(list_item(99, 1, 2, round_="Promotion Play-offs - Final"))
    assert raw_check.expected_regular_season(items) == (6, 3, 6)


@pytest.mark.parametrize(("a", "b", "expected"), [
    ("S. Romero", "Sergio Romero", True),
    ("M. Ødegaard", "Martin Odegaard", True),
    ("K. De Bruyne", "Kevin De Bruyne", True),
    ("Neymar", "Neymar Jr", True),
    ("S. Romero", "D. Blind", False),
    ("M. de Ligt", "J. de Jong", False),  # la particule seule ne suffit pas
])
def test_compatible_names(a, b, expected):
    assert raw_check.compatible_names(a, b) is expected


def test_name_groups_merge_variants_step_by_step():
    assert raw_check.name_groups(["S. Romero", "Sergio Romero", "Romero"]) == [["Romero", "S. Romero", "Sergio Romero"]]
    assert len(raw_check.name_groups(["S. Romero", "D. Blind"])) == 2


def test_probable_duplicates_need_same_name_and_same_birth_date():
    profiles = {
        1: raw_check.Profile("J. Smith", "John", "Smith", "1990-01-01"),
        2: raw_check.Profile("John Smith", "John", "Smith", "1990-01-01"),
        3: raw_check.Profile("J. Smith", "John", "Smith", "1991-05-05"),
        4: raw_check.Profile("J. Smith", None, None, None),
    }
    assert raw_check.probable_duplicates(profiles) == [("1990-01-01", [1, 2])]


def test_block_seasons_follow_the_planner_rules():
    config = parse_config(copy.deepcopy(CONFIG))
    p2 = config.tiers["P2"][0]
    coverage = coverage_from_body({"response": [{"league": {"id": 39}, "seasons": [
        {"year": 2012, "coverage": {"fixtures": {"lineups": False}}},
        {"year": 2013, "coverage": {"fixtures": {"lineups": True}}},
        {"year": 2015, "coverage": {"fixtures": {"lineups": True}}},
    ]}]})
    assert raw_check.block_seasons(p2, 39, coverage) == [2013]
    assert raw_check.block_seasons(p2, 39, None) == []  # saisons inconnues sans /leagues
    top5 = config.tiers["P1"][0]
    assert raw_check.block_seasons(top5, 39, coverage) == [2015]
    assert raw_check.block_seasons(top5, 39, None) == [2015]


def test_latest_versions_keeps_the_most_recent_file_of_each_stem(tmp_path):
    for name in ("page=01__20261001T000000000000Z", "page=01__20261002T000000000000Z", "page=02__20261001T000000000000Z"):
        (tmp_path / f"{name}.json.gz").write_bytes(b"")
    assert [p.name for p in raw_check.latest_versions(tmp_path)] == [
        "page=01__20261002T000000000000Z.json.gz", "page=02__20261001T000000000000Z.json.gz"]


def test_manifest_with_a_truncated_last_line_is_read(tmp_path):
    path = tmp_path / "api_football.jsonl"
    path.write_text('{"file": "a"}\n{"file": "b"}\n{"file": "c', encoding="utf-8")
    entries, bad = raw_check.read_manifest_tolerant(path)
    assert [e["file"] for e in entries] == ["a", "b"]
    assert bad == ["api_football.jsonl, ligne 3"]


# --- ligne de commande et lecture seule ------------------------------------------------------------


def snapshot(directory: Path) -> dict[str, tuple[str, int]]:
    return {path.relative_to(directory).as_posix(): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def write_config(tmp_path: Path) -> Path:
    import yaml

    path = tmp_path / "collecte.yaml"
    path.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    return path


def test_main_writes_a_dated_report_and_leaves_the_raw_dir_untouched(tmp_path, real, capsys):
    raw = tmp_path / "raw"
    build_clean(raw, real).queue.close()
    before = snapshot(raw)
    out = tmp_path / "reports"

    code = raw_check.main(["--raw-dir", str(raw), "--config", str(write_config(tmp_path)),
                           "--palier", "P1", "--output-dir", str(out)])

    assert code == 0  # à regarder, rien de bloquant
    assert snapshot(raw) == before
    [report] = list(out.glob("raw_check_P1_*.md"))
    [details] = list((out / "details").glob("raw_check_P1_*_details.md"))
    assert details.name == report.name.replace(".md", "_details.md")
    text = report.read_text(encoding="utf-8")
    assert text.startswith("# Contrôle qualité du brut API-FOOTBALL : P1")
    assert text.index("## Résumé") < text.index("## 1. Complétude")
    assert "**Verdict : À REGARDER**" in text
    assert "--palier P1" in text
    assert f"details/{details.name}" in text
    assert details.read_text(encoding="utf-8").startswith("# Contrôle qualité du brut API-FOOTBALL : P1, listes détaillées")
    output = capsys.readouterr().out
    assert "Verdict : À REGARDER" in output and str(details) in output


def test_main_returns_1_when_blocking(tmp_path, real):
    raw = tmp_path / "raw"
    builder = build_clean(raw, real)
    builder.fixtures_list(39, listing_of(real) + [list_item(999003, 33, 47)])  # match terminé sans détail
    builder.queue.close()

    code = raw_check.main(["--raw-dir", str(raw), "--config", str(write_config(tmp_path)),
                           "--output-dir", str(tmp_path / "reports")])

    assert code == 1
    assert list((tmp_path / "reports").glob("raw_check_tous_*.md"))


def test_main_refuses_to_write_inside_the_raw_dir(tmp_path, real, capsys):
    raw = tmp_path / "raw"
    build_clean(raw, real).queue.close()
    before = snapshot(raw)

    code = raw_check.main(["--raw-dir", str(raw), "--config", str(write_config(tmp_path)),
                           "--output-dir", str(raw / "rapports")])

    assert code == 2
    assert "dossier brut" in capsys.readouterr().err
    assert snapshot(raw) == before


def test_main_rejects_unknown_tier(tmp_path, capsys):
    (tmp_path / "raw").mkdir()
    code = raw_check.main(["--raw-dir", str(tmp_path / "raw"), "--config", str(write_config(tmp_path)),
                           "--palier", "P9"])
    assert code == 2
    assert "P9" in capsys.readouterr().err
