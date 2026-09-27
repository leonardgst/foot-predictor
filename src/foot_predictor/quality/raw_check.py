"""Contrôle qualité du brut API-FOOTBALL, par palier (rapport de cadrage, G.9).

Lit **uniquement** le dossier brut (ADR-0003) : fichiers `.json.gz`, journal
`_manifest/*.jsonl`, file de travail `_queue/api_football.sqlite` ouverte en
lecture seule. Aucun appel réseau, aucune base de données, aucune écriture
dans le dossier brut. Écrit un rapport Markdown daté dans `reports/data_quality/`.

    uv run python -m foot_predictor.quality.raw_check --palier P1 --raw-dir C:/foot-predictor/data/raw

Contrôles, par championnat-saison du palier (sauf mention contraire) :

- complétude : matchs listés contre attendu, matchs terminés ayant un détail ;
- détails : 2 compositions, 11 titulaires et 1 gardien titulaire par équipe,
  `players` et `events` non vides, selon la couverture déclarée par `/leagues` ;
- cohérence : buts dans `events` = score ;
- identifiants, sur tout le palier : `player.id` présent partout, titulaires
  présents dans les profils, identifiant associé à plusieurs noms, doublons
  probables de personnes ;
- plausibilité : minutes entre 0 et 130, note entre 3 et 10 ;
- journal, sur tout le dossier brut : tâches failed et suspect, fichiers dont
  le sha256 ne correspond pas au journal.

Chaque contrôle reçoit un statut :

- OK ;
- À REGARDER : anomalies à examiner, le plus souvent des données telles que
  l'API les fournit ; une recollecte n'y changerait rien ;
- BLOQUANT : collecte incomplète ou fichier corrompu. À traiter avant de
  commencer le palier suivant (ADR-0002).

Le rapport commence par un résumé, dont le verdict est le pire des statuts.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from foot_predictor.collect.api_football import SOURCE, tasks
from foot_predictor.collect.api_football.coverage import LeagueCoverage, latest_leagues_file, load_coverage
from foot_predictor.collect.api_football.plan import DEFAULT_CONFIG_PATH, Block, CollectConfig, ConfigError, load_config
from foot_predictor.collect.api_football.queue import QUEUE_RELATIVE_PATH
from foot_predictor.rawstore.manifest import MANIFEST_DIR
from foot_predictor.rawstore.store import SUFFIX, VERSION_SEPARATOR, latest_version, read_envelope, sha256_file

DEFAULT_RAW_DIR = Path("data") / "raw"
DEFAULT_OUTPUT_DIR = Path("reports") / "data_quality"
DEFAULT_MAX_ITEMS = 50

# Seuils (rapport G.9).
DETAIL_RATE_THRESHOLD = 0.99  # compositions, players, events : ≥ 99 % sur les saisons couvertes
THRESHOLD_LABEL = f"{DETAIL_RATE_THRESHOLD * 100:g} %"
MINUTES_RANGE = (0, 130)
RATING_RANGE = (3.0, 10.0)

# Score attribué sur tapis vert : ni compositions ni événements attendus.
AWARDED_STATUSES = frozenset({"AWD", "WO"})
# Événements « Goal » qui ne changent pas le score.
MISSED_PENALTY = "Missed Penalty"
SHOOTOUT_COMMENT = "Penalty Shootout"

OK, WATCH, BLOCK = "OK", "À REGARDER", "BLOQUANT"
SEVERITY = {OK: 0, WATCH: 1, BLOCK: 2}

# Contrôles des détails : (clé, libellé, drapeau de couverture de /leagues).
DETAIL_CHECKS = (
    ("two_lineups", "2 compos", "fixtures.lineups"),
    ("eleven_starters", "11 titulaires", "fixtures.lineups"),
    ("one_keeper", "1 gardien", "fixtures.lineups"),
    ("players", "players", "fixtures.statistics_players"),
    ("events", "events", "fixtures.events"),
)
DETAIL_LABELS = {key: label for key, label, _ in DETAIL_CHECKS}

# Familles d'anomalies listées dans le rapport.
ISSUE_FAMILIES = (
    "lists", "missing_details", "lineups", "players_events", "goals",
    "missing_ids", "not_in_profiles", "minutes", "ratings",
)


# --- périmètre ------------------------------------------------------------------------


@dataclass(frozen=True)
class LeagueSeason:
    tier: str
    block: Block
    league: int
    season: int


def block_seasons(block: Block, league: int, coverage: dict[int, LeagueCoverage] | None) -> list[int]:
    """Saisons d'une compétition retenues par le planificateur.

    Mêmes règles que `Planner._seasons` (`collect/api_football/plan.py`) :
    bornes du bloc, saisons déclarées par `/leagues`, drapeau `requires_coverage`.
    Ainsi, le contrôle n'attend pas une saison que le collecteur n'a pas planifiée.
    """
    spec = block.seasons
    cov = coverage.get(league) if coverage is not None else None
    if coverage is not None and cov is None:
        return []
    if spec.first is None:
        if cov is None:
            return []
        years = sorted(year for year in cov.seasons if year <= spec.last)
    else:
        years = list(range(int(spec.first), spec.last + 1))
        if cov is not None:
            years = [year for year in years if cov.has_season(year)]
    if spec.requires_coverage and cov is not None:
        years = [year for year in years if cov.flag(year, spec.requires_coverage)]
    return years


def league_seasons(
    config: CollectConfig, tiers: list[str], coverage: dict[int, LeagueCoverage] | None
) -> tuple[list[LeagueSeason], list[str]]:
    """Championnat-saisons des paliers demandés, et remarques sur le périmètre."""
    scope: list[LeagueSeason] = []
    notes: list[str] = []
    for tier in tiers:
        blocks = config.tiers[tier]
        if not blocks:
            notes.append(f"{tier} : aucun bloc défini dans la configuration.")
        for block in blocks:
            for league in block.leagues:
                if coverage is not None and league not in coverage:
                    notes.append(f"{tier}/{block.name} : compétition {league} absente de /leagues, ignorée.")
                    continue
                if coverage is None and block.seasons.first is None:
                    notes.append(f"{tier}/{block.name} : saisons de {league} inconnues sans /leagues, ignorée.")
                    continue
                scope.extend(LeagueSeason(tier, block, league, season)
                             for season in block_seasons(block, league, coverage))
    return scope, notes


# --- lecture du brut ------------------------------------------------------------------------


def version_stamp(path: Path) -> str:
    """Horodatage de version contenu dans le nom (`<stem>__<horodatage>.json.gz`)."""
    return path.name.removesuffix(SUFFIX).rpartition(VERSION_SEPARATOR)[2]


def latest_versions(directory: Path) -> list[Path]:
    """Dernière version de chaque fichier d'un dossier (non récursif)."""
    latest: dict[str, Path] = {}
    for path in sorted(directory.glob(f"*{SUFFIX}")):
        stem = path.name.partition(VERSION_SEPARATOR)[0]
        latest[stem] = path  # le tri alphabétique suit l'ordre chronologique
    return [latest[stem] for stem in sorted(latest)]


class RawReader:
    """Lecture seule des fichiers bruts.

    Un fichier illisible (gzip tronqué, JSON invalide) est noté, sans arrêter
    le contrôle. Une réponse dont `errors` est non vide est ignorée : elle
    correspond à une tâche `failed`, signalée dans la partie « journal ».
    """

    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = Path(raw_dir)
        self.unreadable: list[str] = []

    def body(self, path: Path) -> dict | None:
        try:
            envelope = read_envelope(path)
        except (OSError, EOFError, ValueError) as exc:  # BadGzipFile est un OSError, JSONDecodeError un ValueError
            message = f"{path.relative_to(self.raw_dir).as_posix()} : {exc}"
            if message not in self.unreadable:  # un même fichier peut être relu (listes de référence des coupes)
                self.unreadable.append(message)
            return None
        body = envelope.get("body") if isinstance(envelope, dict) else None
        if not isinstance(body, dict) or body.get("errors"):
            return None
        return body

    def latest_body(self, rel_dir: str, stem: str) -> dict | None:
        path = latest_version(self.raw_dir, rel_dir, stem)
        return None if path is None else self.body(path)

    def files_by_version(self, rel_dir: str) -> list[Path]:
        """Tous les fichiers d'un dossier, du plus ancien au plus récent."""
        directory = self.raw_dir / rel_dir
        if not directory.is_dir():
            return []
        return sorted(directory.glob(f"*{SUFFIX}"), key=lambda path: (version_stamp(path), path.name))


def fixture_id(item: dict) -> int | None:
    value = (item.get("fixture") or {}).get("id")
    return int(value) if value is not None else None


def status_short(item: dict) -> str | None:
    return ((item.get("fixture") or {}).get("status") or {}).get("short")


def team_ids(item: dict) -> set[int]:
    teams = item.get("teams") or {}
    return {side["id"] for side in (teams.get("home"), teams.get("away")) if side and side.get("id") is not None}


def expected_regular_season(items: list[dict]) -> tuple[int, int, int | None]:
    """(matchs de saison régulière, équipes, nombre attendu).

    Hypothèse : championnat aller-retour, chaque équipe reçoit chacune des
    autres une fois, soit n × (n - 1) matchs. Les barrages et phases finales
    (`round` autre que « Regular Season - ... ») sont exclus. Les formats
    différents (Suisse, Écosse, Belgique, MLS...) sortent donc en « à regarder ».
    """
    regular = [item for item in items
               if str((item.get("league") or {}).get("round") or "").startswith("Regular Season")]
    teams: set[int] = set()
    for item in regular:
        teams |= team_ids(item)
    n = len(teams)
    return len(regular), n, (n * (n - 1) if n else None)


def goals_from_events(events: list[dict], home_id: int | None, away_id: int | None) -> tuple[int, int]:
    """Buts par équipe d'après `events`.

    Un but contre son camp est rattaché par l'API à l'équipe qui en profite.
    Les penalties manqués et les tirs au but ne comptent pas dans le score.
    """
    home = away = 0
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "Goal":
            continue
        if event.get("detail") == MISSED_PENALTY or event.get("comments") == SHOOTOUT_COMMENT:
            continue
        team = (event.get("team") or {}).get("id")
        if team is not None and team == home_id:
            home += 1
        elif team is not None and team == away_id:
            away += 1
    return home, away


# --- noms de joueurs ------------------------------------------------------------------------

_TRANSLITERATION = str.maketrans({
    "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "ß": "ss", "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe", "đ": "d", "Đ": "d", "ı": "i", "þ": "th", "Þ": "th",
})
# Mots trop courants pour rapprocher deux noms à eux seuls.
_PARTICLES = frozenset({
    "de", "da", "do", "di", "du", "del", "della", "der", "den", "des", "dos", "das",
    "van", "von", "le", "la", "el", "al", "ben", "bin", "jr", "junior", "filho",
})


def normalize_name(name: str) -> str:
    """Minuscules, sans accents ni ponctuation : « K. Mbappé » → « k mbappe »."""
    text = unicodedata.normalize("NFKD", name.translate(_TRANSLITERATION))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def name_tokens(name: str) -> frozenset[str]:
    """Mots significatifs : ni initiale, ni particule."""
    return frozenset(token for token in normalize_name(name).split() if len(token) >= 2 and token not in _PARTICLES)


def compatible_names(a: str, b: str) -> bool:
    """Deux variantes du même nom partagent au moins un mot significatif :
    « S. Romero » et « Sergio Romero » oui, « S. Romero » et « D. Blind » non."""
    return normalize_name(a) == normalize_name(b) or bool(name_tokens(a) & name_tokens(b))


def name_groups(names: Iterable[str]) -> list[list[str]]:
    """Regroupe les noms compatibles de proche en proche. Plus d'un groupe
    pour un même identifiant : noms incompatibles, à regarder."""
    groups: list[list[str]] = []
    for name in sorted(set(names)):
        merged = [group for group in groups if any(compatible_names(name, other) for other in group)]
        kept = [group for group in groups if all(group is not m for m in merged)]
        groups = kept + [sorted([name, *(n for group in merged for n in group)])]
    return sorted(groups)


@dataclass(frozen=True)
class Profile:
    name: str | None
    firstname: str | None
    lastname: str | None
    birth: str | None

    def label(self) -> str:
        full = " ".join(part for part in (self.firstname, self.lastname) if part)
        return f"{self.name or '?'} ({full})" if full and full != self.name else (self.name or "?")


def probable_duplicates(profiles: dict[int, Profile]) -> list[tuple[str, list[int]]]:
    """Même nom normalisé (nom affiché, ou prénom et nom) et même date de
    naissance, identifiants différents : (date de naissance, identifiants)."""
    groups: dict[tuple[str, str], set[int]] = defaultdict(set)
    for player_id, profile in profiles.items():
        if not profile.birth:
            continue
        for label in (profile.name or "", f"{profile.firstname or ''} {profile.lastname or ''}"):
            key = normalize_name(label)
            if key:
                groups[(key, profile.birth)].add(player_id)
    seen: set[frozenset[int]] = set()
    duplicates = []
    for (_, birth), ids in sorted(groups.items()):
        if len(ids) > 1 and frozenset(ids) not in seen:
            seen.add(frozenset(ids))
            duplicates.append((birth, sorted(ids)))
    return duplicates


# --- résultats --------------------------------------------------------------------------------


@dataclass
class Rate:
    ok: int = 0
    total: int = 0

    def add(self, passed: bool) -> None:
        self.total += 1
        self.ok += int(passed)

    def merge(self, other: Rate) -> None:
        self.ok += other.ok
        self.total += other.total


@dataclass
class Issue:
    league: int
    season: int
    fixture: int | None
    text: str


@dataclass
class SeasonResult:
    scope: LeagueSeason
    name: str
    list_found: bool = False
    listed: int = 0
    regular: int = 0
    teams: int = 0
    expected: int | None = None
    to_detail: int = 0  # matchs terminés dont le détail est attendu
    detailed: int = 0
    awarded: int = 0  # scores sur tapis vert (exclus des contrôles de détail)
    coverage: dict[str, bool | None] = field(default_factory=dict)  # clé de contrôle -> drapeau
    rates: dict[str, Rate] = field(default_factory=lambda: {key: Rate() for key, _, _ in DETAIL_CHECKS})
    goals: Rate = field(default_factory=Rate)
    profiles: str = "—"  # pages de profils trouvées / attendues

    @property
    def list_expected(self) -> bool:
        return "fixtures_list" in self.scope.block.endpoints

    @property
    def count_ok(self) -> bool:
        return self.expected is None or self.regular == self.expected


@dataclass
class JournalResult:
    manifests: int = 0
    verified: int = 0
    mismatched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unlisted: list[str] = field(default_factory=list)
    bad_lines: list[str] = field(default_factory=list)
    queue_found: bool = False
    queue_error: str | None = None
    task_counts: Counter = field(default_factory=Counter)  # statut -> nombre, paliers contrôlés
    problems: list[dict] = field(default_factory=list)  # tâches failed et suspect


@dataclass
class CheckLine:
    family: str
    label: str
    status: str
    detail: str


@dataclass
class CheckResult:
    tiers: list[str]
    raw_dir: Path
    generated_at: dt.datetime
    coverage_file: str | None
    notes: list[str]
    seasons: list[SeasonResult]
    issues: dict[str, list[Issue]]
    names: dict[int, Counter]
    profiles: dict[int, Profile]
    profiles_expected: bool
    profiles_checked: int
    unreadable: list[str]
    journal: JournalResult
    league_names: dict[int, str]

    # Calculés une fois, à la première lecture (résumé et rapport s'en servent).

    @cached_property
    def name_conflicts(self) -> list[tuple[int, list[list[str]]]]:
        conflicts = []
        for player_id, names in sorted(self.names.items()):
            if len(names) > 1:
                groups = name_groups(names)
                if len(groups) > 1:
                    conflicts.append((player_id, groups))
        return conflicts

    @cached_property
    def duplicates(self) -> list[tuple[str, list[int]]]:
        return probable_duplicates(self.profiles)

    @cached_property
    def checks(self) -> list[CheckLine]:
        return summary_lines(self)

    @property
    def verdict(self) -> str:
        return _worst(*(line.status for line in self.checks))


# --- contrôle ---------------------------------------------------------------------------------------


class RawChecker:
    def __init__(self, raw_dir: Path, config: CollectConfig, tiers: list[str]) -> None:
        self.raw_dir = Path(raw_dir)
        self.config = config
        self.tiers = tiers
        self.reader = RawReader(self.raw_dir)
        self.coverage = load_coverage(self.raw_dir)
        self.issues: dict[str, list[Issue]] = {family: [] for family in ISSUE_FAMILIES}
        self.names: dict[int, Counter] = defaultdict(Counter)
        self.profiles: dict[int, Profile] = {}
        self.profiles_checked = 0
        self._reference_cache: dict[tuple[str, int], set[int]] = {}

    def run(self, now: dt.datetime | None = None) -> CheckResult:
        scope, notes = league_seasons(self.config, self.tiers, self.coverage)
        if self.coverage is None:
            notes.insert(0, "Couverture inconnue (aucune réponse /leagues) : toutes les saisons "
                            "configurées sont attendues et tous les détails sont contrôlés.")
        seasons = [self._check_league_season(ls) for ls in scope]
        leagues_file = latest_leagues_file(self.raw_dir)
        return CheckResult(
            tiers=self.tiers,
            raw_dir=self.raw_dir,
            generated_at=now or dt.datetime.now(dt.timezone.utc),
            coverage_file=leagues_file.relative_to(self.raw_dir).as_posix() if leagues_file else None,
            notes=notes,
            seasons=seasons,
            issues=self.issues,
            names=dict(self.names),
            profiles=self.profiles,
            profiles_expected=any("players" in ls.block.endpoints for ls in scope),
            profiles_checked=self.profiles_checked,
            unreadable=self.reader.unreadable,
            journal=check_journal(self.raw_dir, self.tiers),
            league_names={league: cov.name for league, cov in (self.coverage or {}).items()},
        )

    def _issue(self, family: str, ls: LeagueSeason, fixture: int | None, text: str) -> None:
        self.issues[family].append(Issue(ls.league, ls.season, fixture, text))

    # --- un championnat-saison ------------------------------------------------------

    def _check_league_season(self, ls: LeagueSeason) -> SeasonResult:
        cov = self.coverage.get(ls.league) if self.coverage else None
        result = SeasonResult(ls, name=cov.name if cov else str(ls.league))
        result.coverage = {key: (cov.flag(ls.season, flag) if cov else None) for key, _, flag in DETAIL_CHECKS}

        listing = tasks.fixtures_list_task(ls.tier, ls.league, ls.season)
        body = self.reader.latest_body(listing.rel_dir, listing.stem)
        if body is None:
            if result.list_expected:
                self._issue("lists", ls, None, "liste de matchs absente (ou réponse en erreur)")
            return result
        items = [item for item in body.get("response") or [] if isinstance(item, dict) and fixture_id(item) is not None]
        result.list_found = True
        result.listed = len(items)
        if ls.block.kind == "league":
            result.regular, result.teams, result.expected = expected_regular_season(items)
            if not result.count_ok:
                self._issue("lists", ls, None, f"{result.regular} matchs de saison régulière pour "
                                               f"{result.teams} équipes, {result.expected} attendus")

        if "fixtures_detail" not in ls.block.endpoints:
            return result
        terminal = [item for item in items if status_short(item) in self.config.terminal_statuses]
        if ls.block.detail_teams_from:
            reference = self._reference_teams(ls.block.detail_teams_from, ls.season)
            terminal = [item for item in terminal if team_ids(item) & reference]
        expected = {fixture_id(item): item for item in terminal}
        result.to_detail = len(expected)
        starters: dict[int, tuple[int, str]] = {}
        seen: set[int] = set()
        # Un lot à la fois (20 matchs au plus), pour ne pas charger une saison
        # entière en mémoire. Le plus récent d'abord : une recollecte l'emporte
        # sur la version précédente du même match.
        rel_dir = f"{SOURCE}/fixtures_detail/league={ls.league}/season={ls.season}"
        for path in reversed(self.reader.files_by_version(rel_dir)):
            for detail in (self.reader.body(path) or {}).get("response") or []:
                fid = fixture_id(detail) if isinstance(detail, dict) else None
                if fid is None or fid in seen or fid not in expected:
                    continue
                seen.add(fid)
                result.detailed += 1
                self._check_fixture(ls, result, detail, status_short(expected[fid]), starters)
        for fid, item in expected.items():
            if fid not in seen:
                teams = item.get("teams") or {}
                self._issue("missing_details", ls, fid,
                            f"{status_short(item)}, {(teams.get('home') or {}).get('name', '?')} - "
                            f"{(teams.get('away') or {}).get('name', '?')}, "
                            f"{str((item.get('fixture') or {}).get('date') or '?')[:10]}")

        if "players" in ls.block.endpoints:
            self._check_profiles(ls, result, starters)
        return result

    def _reference_teams(self, reference_tier: str, season: int) -> set[int]:
        """Équipes des championnats du palier de référence, cette saison (même
        filtre que le planificateur pour les coupes)."""
        key = (reference_tier, season)
        if key not in self._reference_cache:
            teams: set[int] = set()
            for block in self.config.tiers.get(reference_tier, []):
                if block.kind != "league":
                    continue
                for league in block.leagues:
                    listing = tasks.fixtures_list_task(reference_tier, league, season)
                    for item in (self.reader.latest_body(listing.rel_dir, listing.stem) or {}).get("response") or []:
                        if isinstance(item, dict):
                            teams |= team_ids(item)
            self._reference_cache[key] = teams
        return self._reference_cache[key]

    # --- un match ------------------------------------------------------------------------

    def _check_fixture(
        self, ls: LeagueSeason, result: SeasonResult, item: dict, status: str | None,
        starters: dict[int, tuple[int, str]],
    ) -> None:
        fid = fixture_id(item)
        lineups = [lineup for lineup in item.get("lineups") or [] if isinstance(lineup, dict)]
        teams_stats = [team for team in item.get("players") or [] if isinstance(team, dict)]
        events = [event for event in item.get("events") or [] if isinstance(event, dict)]
        self._collect_identifiers(ls, fid, lineups, teams_stats, events, starters)
        self._check_plausibility(ls, fid, teams_stats)
        if status in AWARDED_STATUSES:
            result.awarded += 1
            return

        if result.coverage["two_lineups"] is not False:
            self._check_lineups(ls, result, fid, lineups, teams_stats)
        if result.coverage["players"] is not False:
            filled = len(teams_stats) == 2 and all(team.get("players") for team in teams_stats)
            result.rates["players"].add(filled)
            if not filled:
                self._issue("players_events", ls, fid, "players vide ou incomplet")
        if result.coverage["events"] is not False:
            result.rates["events"].add(bool(events))
            if not events:
                self._issue("players_events", ls, fid, "events vide")

        goals = item.get("goals") or {}
        if events and goals.get("home") is not None and goals.get("away") is not None:
            teams = item.get("teams") or {}
            counted = goals_from_events(events, (teams.get("home") or {}).get("id"), (teams.get("away") or {}).get("id"))
            score = (int(goals["home"]), int(goals["away"]))
            result.goals.add(counted == score)
            if counted != score:
                self._issue("goals", ls, fid, f"score {score[0]}-{score[1]}, buts dans events {counted[0]}-{counted[1]}")

    def _check_lineups(
        self, ls: LeagueSeason, result: SeasonResult, fid: int, lineups: list[dict], teams_stats: list[dict]
    ) -> None:
        result.rates["two_lineups"].add(len(lineups) == 2)
        if len(lineups) != 2:
            self._issue("lineups", ls, fid, f"{len(lineups)} composition(s) au lieu de 2")
        # Poste absent de la composition (anciennes saisons) : repli sur le poste des statistiques joueurs.
        stats_positions = {
            (entry.get("player") or {}).get("id"): ((entry.get("statistics") or [{}])[0].get("games") or {}).get("position")
            for team in teams_stats for entry in team.get("players") or [] if isinstance(entry, dict)
        }
        for lineup in lineups:
            team = (lineup.get("team") or {}).get("name") or "?"
            starting = [entry.get("player") or {} for entry in lineup.get("startXI") or [] if isinstance(entry, dict)]
            result.rates["eleven_starters"].add(len(starting) == 11)
            if len(starting) != 11:
                self._issue("lineups", ls, fid, f"{team} : {len(starting)} titulaire(s)")
            keepers = sum(1 for player in starting if (player.get("pos") or stats_positions.get(player.get("id"))) == "G")
            result.rates["one_keeper"].add(keepers == 1)
            if keepers != 1:
                self._issue("lineups", ls, fid, f"{team} : {keepers} gardien(s) titulaire(s)")

    def _collect_identifiers(
        self, ls: LeagueSeason, fid: int, lineups: list[dict], teams_stats: list[dict], events: list[dict],
        starters: dict[int, tuple[int, str]],
    ) -> None:
        players: list[tuple[str, dict]] = []
        for lineup in lineups:
            for place in ("startXI", "substitutes"):
                for entry in lineup.get(place) or []:
                    player = (entry or {}).get("player") or {}
                    players.append((place, player))
                    if place == "startXI" and player.get("id") is not None:
                        starters.setdefault(player["id"], (fid, player.get("name") or "?"))
        for team in teams_stats:
            players += [("players", (entry or {}).get("player") or {}) for entry in team.get("players") or []]
        for event in events:
            for role in ("player", "assist"):
                player = event.get(role) or {}
                # Passeur absent (id et nom nuls) : normal, pas une anomalie.
                if player.get("name"):
                    players.append((f"events.{role}", player))

        for place, player in players:
            player_id, name = player.get("id"), player.get("name")
            if player_id is None:
                self._issue("missing_ids", ls, fid, f"{place} : {name or 'nom absent'}")
            elif name:
                self.names[int(player_id)][name] += 1

    def _check_plausibility(self, ls: LeagueSeason, fid: int, teams_stats: list[dict]) -> None:
        low_min, high_min = MINUTES_RANGE
        low_rating, high_rating = RATING_RANGE
        for team in teams_stats:
            for entry in team.get("players") or []:
                player = (entry or {}).get("player") or {}
                who = f"{player.get('name') or '?'} ({player.get('id')})"
                for stat in (entry or {}).get("statistics") or []:
                    games = (stat or {}).get("games") or {}
                    minutes, rating = games.get("minutes"), games.get("rating")
                    if minutes is not None and not (isinstance(minutes, int) and low_min <= minutes <= high_min):
                        self._issue("minutes", ls, fid, f"{who} : {minutes} minutes")
                    if rating in (None, "", "-", "–"):
                        continue
                    try:
                        value = float(rating)
                    except (TypeError, ValueError):
                        self._issue("ratings", ls, fid, f"{who} : note illisible {rating!r}")
                        continue
                    if not low_rating <= value <= high_rating:
                        self._issue("ratings", ls, fid, f"{who} : note {rating}")

    # --- profils joueurs --------------------------------------------------------------------

    def _check_profiles(self, ls: LeagueSeason, result: SeasonResult, starters: dict[int, tuple[int, str]]) -> None:
        """Lit les pages `/players` du championnat-saison. Si elles sont toutes
        là, vérifie que chaque titulaire a un profil."""
        directory = self.raw_dir / SOURCE / "players" / f"league={ls.league}" / f"season={ls.season}"
        if not directory.is_dir():
            result.profiles = "0/?"
            return
        pages: set[int] = set()
        total: int | None = None
        ids: set[int] = set()
        for path in latest_versions(directory):
            body = self.reader.body(path)
            if body is None:
                continue
            paging = body.get("paging") or {}
            page = int(paging.get("current") or 0)
            pages.add(page)
            if page == 1 and paging.get("total") is not None:
                total = int(paging["total"])
            for entry in body.get("response") or []:
                player = (entry or {}).get("player") or {}
                if player.get("id") is None:
                    self._issue("missing_ids", ls, None, f"profil /players : {player.get('name') or 'nom absent'}")
                    continue
                player_id = int(player["id"])
                ids.add(player_id)
                self.profiles[player_id] = Profile(
                    name=player.get("name"),
                    firstname=player.get("firstname"),
                    lastname=player.get("lastname"),
                    birth=(player.get("birth") or {}).get("date"),
                )
                if player.get("name"):
                    self.names[player_id][player["name"]] += 1

        complete = total is not None and all(page in pages for page in range(1, total + 1))
        result.profiles = f"{len(pages)}/{total if total is not None else '?'}"
        if not complete:
            return
        self.profiles_checked += 1
        for player_id, (fid, name) in sorted(starters.items()):
            if player_id not in ids:
                self._issue("not_in_profiles", ls, fid, f"titulaire {name} ({player_id}) sans profil")


# --- journal et file de travail ----------------------------------------------------------------


def read_manifest_tolerant(path: Path) -> tuple[list[dict], list[str]]:
    """Lignes du journal. Une ligne illisible est notée, pas fatale : si une
    collecte tourne, la dernière ligne peut être en cours d'écriture."""
    entries, bad = [], []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                bad.append(f"{path.name}, ligne {number}")
    return entries, bad


def check_journal(raw_dir: Path, tiers: list[str]) -> JournalResult:
    """sha256 de chaque fichier cité par les journaux, et tâches de la file.

    La vérification des sha256 porte sur tout le dossier brut (comme `backup`),
    la file sur les paliers contrôlés.
    """
    raw_dir = Path(raw_dir)
    result = JournalResult()
    listed: set[str] = set()
    for manifest in sorted((raw_dir / MANIFEST_DIR).glob("*.jsonl")):
        if ".rebuilt-" in manifest.name:
            continue
        result.manifests += 1
        entries, bad = read_manifest_tolerant(manifest)
        result.bad_lines += bad
        for entry in entries:
            relative = entry.get("file")
            if not relative:
                continue
            listed.add(relative)
            path = raw_dir / relative
            if not path.exists():
                result.missing.append(relative)
            elif sha256_file(path) != entry.get("sha256"):
                result.mismatched.append(relative)
            else:
                result.verified += 1
    for path in sorted(raw_dir.rglob(f"*{SUFFIX}")):
        relative = path.relative_to(raw_dir).as_posix()
        if relative not in listed:
            result.unlisted.append(relative)

    queue_path = raw_dir / QUEUE_RELATIVE_PATH
    if not queue_path.exists():
        return result
    result.queue_found = True
    try:
        read_queue(queue_path, tiers, result)
    except sqlite3.Error as exc:
        result.queue_error = str(exc)
    return result


def read_queue(path: Path, tiers: list[str], result: JournalResult) -> None:
    """Ouvre la file SQLite en lecture seule (`mode=ro`) : ni création de
    table, ni verrou d'écriture. Une collecte peut tourner en même temps."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    placeholders = ", ".join("?" for _ in tiers)
    with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=10)) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            f"SELECT status, COUNT(*) AS n FROM tasks WHERE tier IN ({placeholders}) GROUP BY status", tiers
        ):
            result.task_counts[row["status"]] = row["n"]
        rows = conn.execute(
            "SELECT tier, task_type, params, status, attempts, last_error, file FROM tasks"
            f" WHERE status IN ('failed', 'suspect') AND tier IN ({placeholders})"
            " ORDER BY status, tier, task_type, id",
            tiers,
        ).fetchall()
        result.problems = [dict(row) for row in rows]


# --- résumé ---------------------------------------------------------------------------------------


def _pct(ok: int, total: int) -> str:
    return f"{100 * ok / total:.1f} %" if total else "—"


def _worst(*statuses: str) -> str:
    return max(statuses, key=SEVERITY.__getitem__, default=OK)


def summary_lines(result: CheckResult) -> list[CheckLine]:
    lines: list[CheckLine] = []
    seasons = result.seasons
    issues = result.issues

    # Complétude
    absent = [s for s in seasons if s.list_expected and not s.list_found]
    counted = [s for s in seasons if s.expected is not None]
    off = [s for s in counted if not s.count_ok]
    status = BLOCK if absent else WATCH if off else OK
    lines.append(CheckLine("Complétude", "Matchs listés contre attendu", status,
                           f"{len(seasons) - len(absent)}/{len(seasons)} listes présentes ; "
                           f"{len(counted) - len(off)}/{len(counted)} championnats au nombre attendu"))
    to_detail = sum(s.to_detail for s in seasons)
    detailed = sum(s.detailed for s in seasons)
    lines.append(CheckLine("Complétude", "Matchs terminés ayant un détail", BLOCK if detailed < to_detail else OK,
                           f"{detailed}/{to_detail} ({_pct(detailed, to_detail)})"))

    # Détails
    for label, keys, family in (
        ("Compositions : 2 par match, 11 titulaires et 1 gardien par équipe",
         ("two_lineups", "eleven_starters", "one_keeper"), "lineups"),
        ("players et events non vides", ("players", "events"), "players_events"),
    ):
        parts, below = [], set()
        for key in keys:
            total = Rate()
            for season in seasons:
                rate = season.rates[key]
                total.merge(rate)
                if rate.total and rate.ok < DETAIL_RATE_THRESHOLD * rate.total:
                    below.add((season.scope.league, season.scope.season))
            parts.append(f"{DETAIL_LABELS[key]} {_pct(total.ok, total.total)}")
        detail = " ; ".join(parts)
        if below:
            detail += f" ; {len(below)} championnat-saison(s) sous {THRESHOLD_LABEL}"
        lines.append(CheckLine("Détails", label, WATCH if below else OK,
                               detail + f" ; {len(issues[family])} anomalie(s) listée(s)"))

    # Cohérence
    goals = Rate()
    for season in seasons:
        goals.merge(season.goals)
    lines.append(CheckLine("Cohérence", "Buts dans events = score", WATCH if goals.ok < goals.total else OK,
                           f"{goals.ok}/{goals.total} matchs conformes"))

    # Identifiants
    lines.append(CheckLine("Identifiants", "player.id présent partout", WATCH if issues["missing_ids"] else OK,
                           f"{len(issues['missing_ids'])} entrée(s) sans identifiant"))
    if not result.profiles_expected:
        status, detail = OK, "sans objet (aucun profil prévu dans ce périmètre)"
    elif result.profiles_checked == 0:
        status, detail = WATCH, "non vérifiable : aucun championnat-saison n'a toutes ses pages de profils"
    else:
        status = WATCH if issues["not_in_profiles"] else OK
        detail = (f"{len(issues['not_in_profiles'])} titulaire(s) sans profil, "
                  f"sur {result.profiles_checked} championnat-saison(s) aux profils complets")
    lines.append(CheckLine("Identifiants", "Titulaires présents dans les profils", status, detail))
    conflicts = result.name_conflicts
    variants = sum(1 for names in result.names.values() if len(names) > 1)
    lines.append(CheckLine("Identifiants", "Un identifiant, un seul joueur", WATCH if conflicts else OK,
                           f"{len(conflicts)} identifiant(s) aux noms incompatibles ; "
                           f"{variants} avec des variantes tolérées, sur {len(result.names)} joueurs"))
    duplicates = result.duplicates
    lines.append(CheckLine("Identifiants", "Doublons probables (même nom, même naissance)",
                           WATCH if duplicates else OK,
                           f"{len(duplicates)} groupe(s), sur {len(result.profiles)} profils"))

    # Plausibilité
    lines.append(CheckLine("Plausibilité", f"Minutes entre {MINUTES_RANGE[0]} et {MINUTES_RANGE[1]}",
                           WATCH if issues["minutes"] else OK, f"{len(issues['minutes'])} anomalie(s)"))
    lines.append(CheckLine("Plausibilité", f"Note entre {RATING_RANGE[0]:g} et {RATING_RANGE[1]:g}",
                           WATCH if issues["ratings"] else OK, f"{len(issues['ratings'])} anomalie(s)"))

    # Journal
    journal = result.journal
    integrity = BLOCK if (journal.mismatched or journal.missing or result.unreadable) else OK
    if integrity == OK and (journal.unlisted or journal.bad_lines or not journal.manifests):
        integrity = WATCH
    lines.append(CheckLine("Journal", "Intégrité des fichiers (sha256)", integrity,
                           f"{journal.verified} conformes ; {len(journal.mismatched)} sha256 différent(s) ; "
                           f"{len(journal.missing)} absent(s) ; {len(result.unreadable)} illisible(s) ; "
                           f"{len(journal.unlisted)} hors journal"))
    counts = journal.task_counts
    if not journal.queue_found or journal.queue_error:
        status = WATCH
        detail = f"file illisible : {journal.queue_error}" if journal.queue_error else "file de travail absente"
    else:
        status = _worst(BLOCK if counts["failed"] else OK, WATCH if counts["suspect"] or counts["pending"] else OK)
        detail = ", ".join(f"{name} {counts[name]}" for name in ("done", "pending", "failed", "suspect"))
    lines.append(CheckLine("Journal", "Tâches de la file (failed, suspect)", status, detail))
    return lines


# --- rapport Markdown --------------------------------------------------------------------------------


def _md(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _rate_cell(season: SeasonResult, key: str) -> str:
    if season.coverage.get(key) is False:
        return "n. c."
    rate = season.rates[key]
    return _pct(rate.ok, rate.total)


def _truncated(items: list[str], max_items: int) -> list[str]:
    lines = [f"- {item}" for item in items[:max_items]]
    if len(items) > max_items:
        lines.append(f"- … et {len(items) - max_items} autre(s)")
    return lines


def render_markdown(result: CheckResult, max_items: int = DEFAULT_MAX_ITEMS, command: str | None = None) -> str:
    names = result.league_names

    def where(issue: Issue) -> str:
        match = f", match {issue.fixture}" if issue.fixture is not None else ""
        return f"{names.get(issue.league, issue.league)} ({issue.league}) {issue.season}{match} : {issue.text}"

    def issue_block(family: str, title: str) -> list[str]:
        items = result.issues[family]
        if not items:
            return [f"{title} : aucun cas.", ""]
        return [f"{title} ({len(items)}) :", "", *_truncated([_md(where(i)) for i in items], max_items), ""]

    label = ", ".join(result.tiers)
    lines = [
        f"# Contrôle qualité du brut API-FOOTBALL : {label}",
        "",
        f"Généré le {result.generated_at:%Y-%m-%d %H:%M} UTC par `{command or 'python -m foot_predictor.quality.raw_check'}`.",
        f"Dossier brut : `{result.raw_dir.as_posix()}` (lecture seule). Seuils : rapport de cadrage, G.9.",
        f"Couverture : `{result.coverage_file}`." if result.coverage_file else "Couverture : inconnue (aucune réponse /leagues).",
        "",
        "## Résumé",
        "",
        f"**Verdict : {result.verdict}**",
        "",
        "| Famille | Contrôle | Statut | Détail |",
        "|---|---|---|---|",
    ]
    lines += [f"| {c.family} | {_md(c.label)} | {c.status} | {_md(c.detail)} |" for c in result.checks]
    lines += [
        "",
        "OK : rien à faire. À REGARDER : anomalies à examiner, souvent des données telles que l'API "
        "les fournit. BLOQUANT : collecte incomplète ou fichier corrompu, à traiter avant le palier suivant (ADR-0002).",
        "",
    ]
    if result.notes:
        lines += ["Remarques sur le périmètre :", "", *_truncated([_md(n) for n in result.notes], max_items), ""]

    # 1. Complétude
    lines += [
        "## 1. Complétude",
        "",
        "Attendu : n × (n - 1) matchs de saison régulière pour n équipes (aller-retour) ; "
        "rien pour les coupes. Détails attendus : matchs terminés (dans les coupes, seulement "
        "ceux d'une équipe suivie). « Tapis vert » : scores attribués (AWD, WO), exclus des contrôles de détail.",
        "",
        "| Palier | Compétition | Saison | Listés | Saison régulière | Équipes | Attendu | Terminés à détailler | Avec détail | Tapis vert |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in result.seasons:
        if not s.list_found:
            cells = ["**absente**", "", "", "", "", "", ""]
        else:
            cells = [s.listed, s.regular if s.expected is not None else "—", s.teams or "—",
                     s.expected if s.expected is not None else "—", s.to_detail,
                     f"{s.detailed} ({_pct(s.detailed, s.to_detail)})", s.awarded]
        lines.append(f"| {s.scope.tier} | {_md(s.name)} ({s.scope.league}) | {s.scope.season} | "
                     + " | ".join(str(c) for c in cells) + " |")
    lines += ["", *issue_block("lists", "Listes à regarder"), *issue_block("missing_details", "Matchs terminés sans détail")]

    # 2. Détails
    lines += [
        "## 2. Détails des matchs",
        "",
        f"Taux par championnat-saison ; seuil {THRESHOLD_LABEL}. « n. c. » : non couvert d'après /leagues "
        "(non contrôlé). Compositions : taux par équipe pour les titulaires et le gardien.",
        "",
        "| Palier | Compétition | Saison | Détails | " + " | ".join(lab for _, lab, _ in DETAIL_CHECKS) + " | Profils (pages) |",
        "|---|---|---|---|" + "---|" * len(DETAIL_CHECKS) + "---|",
    ]
    for s in result.seasons:
        if s.detailed or s.list_found:
            cells = [s.detailed, *(_rate_cell(s, key) for key, _, _ in DETAIL_CHECKS), s.profiles]
            lines.append(f"| {s.scope.tier} | {_md(s.name)} ({s.scope.league}) | {s.scope.season} | "
                         + " | ".join(str(c) for c in cells) + " |")
    lines += ["", *issue_block("lineups", "Compositions à regarder"), *issue_block("players_events", "players ou events vides")]

    # 3. Cohérence
    lines += [
        "## 3. Cohérence : buts dans events = score",
        "",
        "Buts comptés : événements `Goal` hors penalties manqués et tirs au but ; un but contre son camp "
        "compte pour l'équipe qui en profite. Score : champ `goals` (prolongation comprise).",
        "",
        *issue_block("goals", "Écarts"),
    ]

    # 4. Identifiants
    lines += ["## 4. Identifiants", "", *issue_block("missing_ids", "Entrées sans player.id"),
              *issue_block("not_in_profiles", "Titulaires sans profil /players")]
    conflicts = result.name_conflicts
    lines += [
        "Identifiants associés à plusieurs noms incompatibles (variantes du type « S. Romero » / "
        f"« Sergio Romero » tolérées) ({len(conflicts)}) :" if conflicts else
        "Identifiants associés à plusieurs noms incompatibles : aucun.",
        "",
    ]
    if conflicts:
        lines += _truncated([f"{player_id} : " + _md(" | ".join(" / ".join(g) for g in groups))
                             for player_id, groups in conflicts], max_items) + [""]
    duplicates = result.duplicates
    lines += [f"Doublons probables : même nom et même date de naissance, identifiants différents ({len(duplicates)}) :"
              if duplicates else "Doublons probables : aucun.", ""]
    if duplicates:
        lines += _truncated([f"né le {birth} : " + _md(" ; ".join(f"{pid} {result.profiles[pid].label()}" for pid in ids))
                             for birth, ids in duplicates], max_items) + [""]

    # 5. Plausibilité
    lines += ["## 5. Plausibilité", "", *issue_block("minutes", "Minutes hors bornes"),
              *issue_block("ratings", "Notes hors bornes")]

    # 6. Journal
    journal = result.journal
    lines += [
        "## 6. Journal et file de travail",
        "",
        f"sha256 vérifiés sur tout le dossier brut ({journal.manifests} journal(aux)) : {journal.verified} conformes.",
        "",
    ]
    for title, items in (("sha256 différent du journal", journal.mismatched),
                         ("Cités par le journal mais absents du disque", journal.missing),
                         ("Illisibles", result.unreadable),
                         ("Présents sur le disque mais absents du journal (normal pendant une collecte)", journal.unlisted),
                         ("Lignes de journal illisibles", journal.bad_lines)):
        if items:
            lines += [f"{title} ({len(items)}) :", "", *_truncated([f"`{_md(i)}`" for i in items], max_items), ""]
    if not journal.queue_found:
        lines += ["File de travail absente : tâches non vérifiées.", ""]
    elif journal.queue_error:
        lines += [f"File de travail illisible : {_md(journal.queue_error)}", ""]
    else:
        counts = journal.task_counts
        lines += ["Tâches des paliers contrôlés : " + ", ".join(f"{k} {counts[k]}" for k in ("done", "pending", "failed", "suspect")) + ".", ""]
        if journal.problems:
            lines += ["| Statut | Palier | Type | Paramètres | Tentatives | Raison | Fichier |", "|---|---|---|---|---|---|---|"]
            for row in journal.problems[:max_items]:
                lines.append(f"| {row['status']} | {row['tier']} | {row['task_type']} | `{_md(row['params'])}` | "
                             f"{row['attempts']} | {_md(row['last_error'] or '')} | {_md(row['file'] or '')} |")
            if len(journal.problems) > max_items:
                lines.append(f"\n… et {len(journal.problems) - max_items} autre(s).")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# --- ligne de commande --------------------------------------------------------------------------------


def report_path(output_dir: Path, tiers: list[str], all_tiers: bool, when: dt.datetime) -> Path:
    label = "tous" if all_tiers else "-".join(tiers)
    return Path(output_dir) / f"raw_check_{label}_{when:%Y-%m-%d}.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m foot_predictor.quality.raw_check",
        description="Contrôle qualité du brut API-FOOTBALL (rapport G.9). Lecture seule du dossier brut, "
                    "aucun appel réseau.",
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="dossier brut (défaut : data/raw)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="fichier des paliers")
    parser.add_argument("--palier", action="append", dest="tiers",
                        help="palier à contrôler (P1, P2...) ; répétable ; défaut : tous")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="dossier du rapport (défaut : reports/data_quality)")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS,
                        help="nombre maximal d'éléments par liste d'anomalies")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Code de retour : 0 si aucun contrôle bloquant, 1 sinon, 2 en cas d'erreur d'usage."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        tiers = args.tiers or list(config.tiers)
        unknown = [tier for tier in tiers if tier not in config.tiers]
        if unknown:
            raise ConfigError(f"Palier(s) inconnu(s) : {', '.join(unknown)} (connus : {', '.join(config.tiers)})")
        if not args.raw_dir.is_dir():
            raise FileNotFoundError(f"Dossier brut introuvable : {args.raw_dir}")
        if args.output_dir.resolve().is_relative_to(args.raw_dir.resolve()):
            raise ValueError("Le rapport ne peut pas être écrit dans le dossier brut (lecture seule).")
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2

    result = RawChecker(args.raw_dir, config, tiers).run()
    command = "python -m foot_predictor.quality.raw_check " + " ".join(f"--palier {t}" for t in tiers) \
        if args.tiers else "python -m foot_predictor.quality.raw_check"
    markdown = render_markdown(result, args.max_items, command)
    target = report_path(args.output_dir, tiers, not args.tiers, result.generated_at)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")

    print(f"Verdict : {result.verdict}")
    for line in result.checks:
        print(f"  [{line.status}] {line.family} - {line.label} : {line.detail}")
    print(f"Rapport écrit dans {target}")
    return 1 if result.verdict == BLOCK else 0


if __name__ == "__main__":
    sys.exit(main())
