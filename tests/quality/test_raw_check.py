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

    def leagues(self, flags_by_league: dict[int, dict], years: tuple[int, ...] = (2015,)) -> None:
        response = [{"league": {"id": league, "name": f"Compétition {league}", "type": "League"},
                     "country": {"name": "England"},
                     "seasons": [{"year": year, "coverage": flags} for year in years]}
                    for league, flags in flags_by_league.items()]
        task = tasks.leagues_task("P0")
        self.write(task.rel_dir, task.stem, body(response), endpoint="/leagues")

    def fixtures_list(self, league: int, items: list[dict], tier: str = "P1", season: int = 2015) -> None:
        task = tasks.fixtures_list_task(tier, league, season)
        self.write(task.rel_dir, task.stem, body(items), params=task.params)
        self.done(task)

    def details(self, league: int, items: list[dict], tier: str = "P1", season: int = 2015) -> store.StoredFile:
        task = tasks.fixtures_detail_task(tier, league, season, [item["fixture"]["id"] for item in items])
        stored = self.write(task.rel_dir, task.stem, body(items), params=task.params)
        self.done(task)
        return stored

    def profiles(self, league: int, response: list[dict], page: int = 1, total: int = 1,
                 tier: str = "P1", season: int = 2015) -> None:
        task = tasks.players_task(tier, league, season, page)
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
                  "Un identifiant", "Doublons", "Collisions : deux équipes", "Collisions : deux fois",
                  "Collisions : deux dates", "Minutes", "Note", "Intégrité", "Tâches"):
        assert status_of(result, label) == OK, label
    assert result.verdict == WATCH
    # Les 5 vrais matchs : aucune collision (joueur présent en composition et en statistiques, même équipe).
    assert result.collisions == [] and result.birth_corrections == []
    assert result.appearances > 0
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


# --- collisions d'identifiants (ADR-0008, règle 3) -------------------------------------------------

# P1 (championnat 39) et P3 (championnat 88), contrôlables ensemble.
MULTI_CONFIG = {
    "tiers": {
        "P1": {"blocks": [
            {"name": "top5", "kind": "league", "leagues": [39], "seasons": {"first": 2015, "last": 2016},
             "endpoints": ["fixtures_list", "fixtures_detail", "players"]},
        ]},
        "P3": {"blocks": [
            {"name": "autres", "kind": "league", "leagues": [88], "seasons": {"first": 2015, "last": 2016},
             "endpoints": ["fixtures_list", "fixtures_detail", "players"]},
        ]},
    }
}


def synthetic(fid: int, date: str, home: int, away: int, home_ids: list, away_ids: list,
              home_stats: list | None = None, away_stats: list | None = None, league: int = 39) -> dict:
    """Détail de match minimal : compositions (titulaires) et statistiques joueurs.

    Un joueur s'écrit `id` (numéro de maillot = id % 100) ou `(id, numéro)`. Par
    défaut, les statistiques reprennent les titulaires de chaque équipe."""
    def team(team_id: int) -> dict:
        return {"id": team_id, "name": f"Équipe {team_id}"}

    def split(player) -> tuple[int, int]:
        return player if isinstance(player, tuple) else (player, player % 100)

    def lineup(team_id: int, players: list) -> dict:
        return {"team": team(team_id), "substitutes": [], "startXI": [
            {"player": {"id": pid, "name": f"Joueur {pid}", "pos": "M", "number": number}}
            for pid, number in map(split, players)]}

    def stats(team_id: int, players: list) -> dict:
        return {"team": team(team_id), "players": [
            {"player": {"id": pid, "name": f"Joueur {pid}"}, "statistics": [{"games": {"minutes": 90, "number": number}}]}
            for pid, number in map(split, players)]}

    return {
        "fixture": {"id": fid, "date": f"{date}T15:00:00+00:00", "status": {"short": "FT"}},
        "league": {"id": league, "round": "Regular Season - 1"},
        "teams": {"home": team(home), "away": team(away)},
        "goals": {"home": 0, "away": 0}, "score": {},
        "lineups": [lineup(home, home_ids), lineup(away, away_ids)],
        "players": [stats(home, home_stats if home_stats is not None else home_ids),
                    stats(away, away_stats if away_stats is not None else away_ids)],
        "events": [],
    }


def profile(pid: int, birth: str | None, name: str | None = None) -> dict:
    name = name or f"Joueur {pid}"
    first, _, last = name.partition(" ")
    return {"player": {"id": pid, "name": name, "firstname": first, "lastname": last, "birth": {"date": birth}}}


def build_multi(raw_dir: Path, p1: list[dict], p3: list[dict], profiles_p1=(), profiles_p3=(),
                season: int = 2015) -> RawBuilder:
    """P1 et P3 pour une saison ; l'autre saison du périmètre a une liste vide."""
    builder = RawBuilder(raw_dir)
    builder.leagues({39: FLAGS, 88: FLAGS}, years=(2015, 2016))
    for league, tier, details, profiles in ((39, "P1", p1, profiles_p1), (88, "P3", p3, profiles_p3)):
        for other in {2015, 2016} - {season}:
            builder.fixtures_list(league, [], tier=tier, season=other)
        builder.fixtures_list(league, listing_of(details), tier=tier, season=season)
        if details:
            builder.details(league, details, tier=tier, season=season)
        builder.profiles(league, list(profiles), tier=tier, season=season)
    return builder


@pytest.fixture
def multi_config():
    return parse_config(copy.deepcopy(MULTI_CONFIG))


def collision_ids(result, kind: str) -> set[int]:
    return {c.player for c in result.collisions_of(kind)}


def test_same_day_collision_is_found_only_when_tiers_are_checked_together(tmp_path, multi_config):
    raw = tmp_path / "raw"
    p1 = [synthetic(1001, "2015-08-15", 1, 2, [501, 11], [21])]
    p3 = [synthetic(3001, "2015-08-15", 3, 4, [501, 31], [41]),   # 501 : deux équipes le même jour
          synthetic(3002, "2015-08-16", 3, 4, [11], [42])]        # 11 : autre équipe, le lendemain
    build_multi(raw, p1, p3).queue.close()

    together = RawChecker(raw, multi_config, ["P1", "P3"]).run(now=NOW)
    alone = RawChecker(raw, multi_config, ["P1"]).run(now=NOW)

    [case] = together.collisions_of(raw_check.SAME_DAY)
    assert (case.player, case.tiers) == (501, ("P1", "P3"))
    assert "match 1001" in case.text and "match 3001" in case.text
    assert status_of(together, "Collisions : deux équipes") == WATCH
    assert alone.collisions == []
    assert status_of(alone, "Collisions : deux équipes") == OK


def test_same_team_on_the_same_day_is_not_a_collision(tmp_path, multi_config):
    raw = tmp_path / "raw"
    # Même joueur, même équipe, deux matchs le même jour : pas deux personnes (hors du périmètre de la règle).
    p1 = [synthetic(1001, "2015-08-15", 1, 2, [501], [21]), synthetic(1002, "2015-08-15", 1, 3, [501], [31])]
    build_multi(raw, p1, []).queue.close()

    result = RawChecker(raw, multi_config, ["P1", "P3"]).run(now=NOW)

    assert collision_ids(result, raw_check.SAME_DAY) == set()


def test_same_match_collisions_and_their_false_positives(tmp_path, multi_config):
    raw = tmp_path / "raw"
    swapped_home, swapped_away = [51, 52, 53, 54, 55, 56], [61, 62, 63]
    p1 = [
        synthetic(1001, "2015-08-15", 1, 2, [601, 11], [601, 21]),  # 601 dans les deux compositions
        synthetic(1002, "2015-08-22", 1, 2, [12, 602], [22], home_stats=[12, 602, 602]),  # entrée répétée
        synthetic(1003, "2015-08-29", 1, 2, [(603, 4), 13], [23], home_stats=[(603, 4), (603, 5), 13]),  # 2 numéros
        synthetic(1004, "2015-09-05", 1, 2, [604, 14], [24], home_stats=[14], away_stats=[24, 604]),  # cas isolé
        # Statistiques rattachées à l'équipe adverse dans tout le match : faux positif.
        synthetic(1005, "2015-09-12", 1, 2, swapped_home, swapped_away, home_stats=swapped_away, away_stats=swapped_home),
        synthetic(1006, "2015-09-19", 1, 2, [0, 15], [0, 25]),  # identifiant 0 : joueur inconnu de l'API
        synthetic(1007, "2015-09-26", 1, 2, [16], [26]),  # composition + statistiques, même équipe : normal
    ]
    build_multi(raw, p1, []).queue.close()

    result = RawChecker(raw, multi_config, ["P1"]).run(now=NOW)

    cases = {c.player: c.subtype for c in result.collisions_of(raw_check.SAME_MATCH)}
    assert cases == {601: raw_check.TWO_TEAMS, 603: raw_check.SAME_TEAM, 604: raw_check.TWO_TEAMS}
    false = {(c.player, c.subtype) for c in result.false_positives}
    assert false == {(602, raw_check.REPEATED_ENTRY),
                     *((pid, raw_check.SWAPPED_STATS) for pid in swapped_home + swapped_away)}
    assert result.unknown_id_entries == 4  # 2 compositions + 2 statistiques
    # 601, déjà en collision dans son match, n'est pas compté une seconde fois au titre du « même jour ».
    assert collision_ids(result, raw_check.SAME_DAY) == set()
    assert status_of(result, "Collisions : deux fois") == WATCH
    summary = raw_check.render_summary(result)
    assert "statistiques rattachées à l'équipe adverse dans tout le match : 9 cas, 1 match(s)" in summary
    assert "même entrée répétée (même équipe, même numéro) : 1 cas, 1 match(s)" in summary


def test_swapped_statistics_do_not_create_same_day_collisions(tmp_path, multi_config):
    raw = tmp_path / "raw"
    home, away = [51, 52, 53, 54, 55], [61, 62, 63, 64, 65]
    # La composition fait foi : chaque joueur reste dans son équipe, le même jour, dans les deux paliers.
    p1 = [synthetic(1001, "2015-08-15", 1, 2, home, away, home_stats=away, away_stats=home)]
    p3 = [synthetic(3001, "2015-08-15", 1, 2, [51], [61], league=88)]
    build_multi(raw, p1, p3).queue.close()

    result = RawChecker(raw, multi_config, ["P1", "P3"]).run(now=NOW)

    assert result.collisions == []
    assert len(result.false_positives) == 10


def test_two_birth_dates_are_a_collision_but_a_later_correction_is_set_apart(tmp_path, multi_config):
    raw = tmp_path / "raw"
    builder = build_multi(raw, [], [], profiles_p1=[profile(701, "1990-01-01"), profile(702, "1991-02-02")],
                          profiles_p3=[profile(701, "1993-03-03")])  # 701 : deux dates la même saison
    builder.profiles(39, [profile(702, "1991-02-20"), profile(703, "1992-01-01")], season=2016)  # 702 corrigé
    builder.queue.close()

    together = RawChecker(raw, multi_config, ["P1", "P3"]).run(now=NOW)
    alone = RawChecker(raw, multi_config, ["P1"]).run(now=NOW)

    [birth] = together.collisions_of(raw_check.BIRTH)
    assert (birth.player, birth.tiers) == (701, ("P1", "P3"))
    assert [c.player for c in together.birth_corrections] == [702]
    assert "1 date(s) corrigée(s)" in next(l.detail for l in together.checks if l.label.startswith("Collisions : deux dates"))
    assert alone.collisions_of(raw_check.BIRTH) == []  # la seconde date de 701 est en P3
    assert [c.player for c in alone.birth_corrections] == [702]


@pytest.mark.parametrize(("seasons", "expected"), [
    ({"1990-01-01": {2015, 2016}}, None),
    ({"1990-01-01": {2015, 2016}, "1990-01-10": {2017, 2018}}, "correction"),
    ({"1990-01-01": {2015, 2017}, "1990-01-10": {2016}}, raw_check.BIRTH),  # alternance
    ({"1990-01-01": {2015}, "1990-01-10": {2015}}, raw_check.BIRTH),  # même saison
    ({"1990-01-01": {2015}, "1990-01-10": {2016}, "1990-01-20": {2017}}, raw_check.BIRTH),  # trois dates
])
def test_classify_births(seasons, expected):
    assert raw_check.classify_births(seasons) == expected


def test_inter_tier_duplicates_are_flagged(tmp_path, multi_config):
    raw = tmp_path / "raw"
    build_multi(raw, [], [], profiles_p1=[profile(801, "1995-05-05", "Jean Dupont")],
                profiles_p3=[profile(802, "1995-05-05", "Jean Dupont")]).queue.close()

    together = RawChecker(raw, multi_config, ["P1", "P3"]).run(now=NOW)
    alone = RawChecker(raw, multi_config, ["P1"]).run(now=NOW)

    assert [ids for _, ids in together.duplicates] == [[801, 802]]
    assert together.duplicate_tiers([801, 802]) == ("P1+P3", True)
    assert "dont 1 inter-paliers" in next(l.detail for l in together.checks if l.label.startswith("Doublons"))
    assert alone.duplicates == []


def test_appearances_group_players_seen_with_two_teams_on_one_day():
    appearances = raw_check.Appearances()
    for row in [(5, 100, 1, 10, 0), (5, 100, 1, 11, 0),   # même équipe, même jour : rien
                (6, 100, 1, 12, 0), (6, 100, 2, 13, 1),   # deux équipes : collision
                (6, 101, 3, 14, 1), (7, 100, 2, 13, 1)]:
        appearances.add(*row)
    assert appearances.same_day_groups() == [[(6, 100, 1, 12, 0), (6, 100, 2, 13, 1)]]
    assert raw_check.Appearances().same_day_groups() == []


def test_collision_reports_keep_names_and_ids_in_the_details_only(tmp_path, multi_config):
    raw = tmp_path / "raw"
    p1 = [synthetic(1001, "2015-08-15", 1, 2, [501, 601], [601])]
    p3 = [synthetic(3001, "2015-08-15", 3, 4, [501], [41])]
    build_multi(raw, p1, p3, profiles_p1=[profile(801, "1995-05-05", "Jean Dupont")],
                profiles_p3=[profile(802, "1995-05-05", "Jean Dupont"), profile(501, "1990-01-01")]).queue.close()
    config_path = tmp_path / "collecte.yaml"
    import yaml
    config_path.write_text(yaml.safe_dump(MULTI_CONFIG), encoding="utf-8")
    before = snapshot(raw)
    out = tmp_path / "reports"

    code = raw_check.main(["--raw-dir", str(raw), "--config", str(config_path),
                           "--palier", "P1", "--palier", "P3", "--output-dir", str(out)])

    assert code == 0
    assert snapshot(raw) == before  # dossier brut inchangé, octet pour octet et date de modification
    [summary_path] = list(out.glob("raw_check_P1-P3_*.md"))
    summary = summary_path.read_text(encoding="utf-8")
    details = next((out / "details").glob("*_details.md")).read_text(encoding="utf-8")
    assert "## 5. Collisions et doublons par palier" in summary
    assert "| P1+P3 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |" in summary  # même jour (501) ; doublon inter-paliers
    assert "| P1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |" in summary  # même match, deux équipes (601)
    for secret in ("Jean Dupont", "Joueur 501", "Joueur 601"):
        assert secret not in summary and secret in details
    for pid in (501, 601, 801, 802):
        assert not re.search(rf"\b{pid}\b", summary) and re.search(rf"\b{pid}\b", details)


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
