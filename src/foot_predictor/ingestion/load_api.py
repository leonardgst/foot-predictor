"""Chargeur API-FOOTBALL : brut (lecture seule) -> `staging`, par identifiants API (ADR-0008).

Ce module prépare les lignes ; `ingestion/load.py` les écrit en base (COPY) dans
une seule transaction, après avoir vidé `staging`. Aucune correction n'est faite
en base : tout passe par les YAML de `ingestion/mappings/` (ADR-0008, règle 4).

Trois passes sur le brut :

0. **Listes** (`fixtures_list`, dernière version) : compétitions, saisons,
   équipes, matchs. Les champs du match (date, statut, scores) viennent de la
   liste, tenue à jour par `refresh` pour la saison en cours.
1. **Catalogue** (détails de match, profils) : présences de chaque joueur,
   noms, entraîneurs, dates de naissance. On en déduit les collisions « même
   jour » et « deux naissances », puis la liste des joueurs à créer.
2. **Émission** (détails de match, de nouveau) : compositions, statistiques
   joueurs, statistiques d'équipe, compteurs par équipe et par match.

Règles (ADR-0008, ADR-0009, ADR-0016, ADR-0020) :

- une entité (joueur, entraîneur, équipe, match) n'est créée qu'à partir d'un
  identifiant API ; identifiant absent ou 0 : joueur inconnu, non créé, compté ;
- l'équipe d'un joueur se lit dans la composition, pas dans les statistiques ;
- collisions exclues (joueur inconnu), sauf « deux numéros dans la même équipe »
  résolu par le numéro de la composition ; exceptions par YAML ;
- alias de joueurs appliqués (identifiant secondaire -> principal) ;
- score au temps réglementaire (`score.fulltime`) distinct du score final ;
  matchs sur tapis vert, annulés ou abandonnés exclus, avec leur motif ;
- date de naissance : pages `/players` et profils ciblés, la plus récente en cas
  de correction, aucune en cas de collision.

Les identifiants internes sont attribués dans l'ordre des identifiants API :
deux chargements du même brut donnent les mêmes lignes (déterminisme).
"""

from __future__ import annotations

import datetime as dt
from array import array
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect.api_football.plan import CollectConfig
from foot_predictor.ingestion import collisions as col
from foot_predictor.ingestion import raw_api
from foot_predictor.rawstore.store import SUFFIX, VERSION_SEPARATOR

POSITION_BUCKETS = {"G": "Goalkeeper", "D": "Defender", "M": "Midfielder", "F": "Attacker"}
TOP5_LEAGUES = frozenset({39, 140, 78, 135, 61})  # population d'évaluation (ADR-0012)
REVISION_SHARE = 0.10  # ADR-0020 : part des titularisations d'une saison perdue par exclusion
REVISION_MIN_STARTS = 10

# Statut API -> statut du référentiel, et motif d'exclusion (ADR-0009).
PLAYED = {"FT", "AET", "PEN"}
EXCLUSIONS = {"AWD": "tapis_vert", "WO": "tapis_vert", "CANC": "annule", "ABD": "abandonne"}
POSTPONED = {"PST", "SUSP", "INT"}

TEAM_STATS = {  # libellé API -> colonne de staging.team_match_stats
    "Shots on Goal": "shots_on_goal",
    "Shots off Goal": "shots_off_goal",
    "Total Shots": "shots_total",
    "Blocked Shots": "shots_blocked",
    "Shots insidebox": "shots_inside_box",
    "Shots outsidebox": "shots_outside_box",
    "Fouls": "fouls",
    "Corner Kicks": "corners",
    "Offsides": "offsides",
    "Ball Possession": "possession_pct",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Goalkeeper Saves": "goalkeeper_saves",
    "Total passes": "passes_total",
    "Passes accurate": "passes_accurate",
    "Passes %": "passes_pct",
    "expected_goals": "expected_goals",
}
TEAM_STATS_COLUMNS = list(dict.fromkeys(TEAM_STATS.values()))
TEAM_STATS_DECIMAL = {"possession_pct", "passes_pct", "expected_goals"}  # les autres sont des entiers


def match_status(short: str | None) -> tuple[str, bool, str | None]:
    """(statut du référentiel, exclu, motif). Un match en cours compte comme « scheduled »."""
    if short in PLAYED:
        return "played", False, None
    if short in EXCLUSIONS:
        return "cancelled", True, EXCLUSIONS[short]
    if short in POSTPONED:
        return "postponed", False, None
    return "scheduled", False, None


def number(value: object) -> float | None:
    """« 55% », « 1.23 », 7 ou None -> nombre (None si illisible)."""
    if value is None:
        return None
    try:
        return float(str(value).strip().rstrip("%"))
    except ValueError:
        return None


def integer(value: object) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None else None


def season_label(year: int, first: dt.date | None, last: dt.date | None) -> str:
    """« 2023-2024 » pour une saison à cheval sur deux années, « 2023 » sinon (MLS, Brésil...)."""
    return f"{year}-{year + 1}" if last is None or last.year > year else str(year)


def _version_year(path: Path) -> int:
    return int(path.name.split(VERSION_SEPARATOR)[-1][:4])


def _latest_files(directory: Path) -> list[Path]:
    latest: dict[str, Path] = {}
    for path in sorted(directory.glob(f"*{SUFFIX}")):
        latest[path.name.split(VERSION_SEPARATOR)[0]] = path
    return [latest[stem] for stem in sorted(latest)]


def csv_value(value: object) -> str:
    """Valeur pour `COPY ... (FORMAT csv)` : champ vide non entre guillemets = NULL."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    return str(value)


class Rows:
    """Lignes à écrire, par table, dans l'ordre des colonnes de `COLUMNS`.

    Sans dossier : gardées en mémoire (tests). Avec un dossier : écrites au fil de
    l'eau dans un CSV par table (environ 6 millions de lignes pour P1 à P3, trop
    pour la mémoire du portable), puis copiées en base par `COPY`.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
        self.tables: dict[str, list[tuple]] = defaultdict(list)
        self.counts: Counter = Counter()
        self._files: dict[str, object] = {}
        self._writers: dict[str, object] = {}

    def add(self, table: str, row: tuple) -> None:
        self.counts[table] += 1
        if self.directory is None:
            self.tables[table].append(row)
            return
        if table not in self._writers:
            import csv

            handle = open(self.directory / f"{table}.csv", "w", encoding="utf-8", newline="")  # noqa: SIM115
            self._files[table], self._writers[table] = handle, csv.writer(handle, lineterminator="\n")
        self._writers[table].writerow([csv_value(v) for v in row])

    def close(self) -> None:
        for handle in self._files.values():
            handle.close()
        self._files.clear()
        self._writers.clear()

    def path(self, table: str) -> Path | None:
        path = self.directory / f"{table}.csv" if self.directory else None
        return path if path and path.exists() else None


COLUMNS = {
    "competition": ("id", "name", "country", "api_league_id", "kind"),
    "season": ("id", "competition_id", "label", "start_date", "end_date", "year"),
    "team": ("id", "name", "country", "api_team_id", "origin"),
    "coach": ("id", "api_coach_id", "name"),
    "player": ("id", "full_name", "birth_date", "nationality", "api_player_id"),
    "match": (
        "id",
        "competition_id",
        "season_id",
        "match_date",
        "home_team_id",
        "away_team_id",
        "home_goals",
        "away_goals",
        "status",
        "api_fixture_id",
        "kickoff_utc",
        "status_short",
        "round",
        "home_goals_90",
        "away_goals_90",
        "home_penalties",
        "away_penalties",
        "excluded",
        "exclusion_reason",
        "origin",
    ),  # fmt: skip
    "team_match": (
        "id",
        "match_id",
        "team_id",
        "is_home",
        "goals_for",
        "goals_against",
        "xg_for",
        "xg_against",
        "coach_id",
        "formation",
        "unknown_starters",
        "collision_excluded",
    ),  # fmt: skip
    "team_match_stats": ("id", "team_match_id", *TEAM_STATS_COLUMNS),
    # Remplies par load_external (football-data) : lien vers la source d'origine.
    "competition_source_mapping": ("id", "competition_id", "source_name", "source_ref"),
    "team_source_mapping": ("id", "team_id", "source_name", "source_ref"),
    "match_source_mapping": ("id", "match_id", "source_name", "source_ref"),
    # Remplie par load_external : tirs de football-data par équipe et par match (migration 0005, ADR-0029).
    "team_match_stats_external": ("id", "source", "team_match_id", "shots", "shots_on_target"),
    "lineup": (
        "id",
        "match_id",
        "team_id",
        "player_id",
        "started",
        "position",
        "shirt_number",
        "grid",
        "position_bucket",
    ),
    "player_match_stats": (
        "id",
        "match_id",
        "player_id",
        "team_id",
        "minutes",
        "rating",
        "position_bucket",
        "goals",
        "assists",
        "shots",
        "shots_on_target",
        "key_passes",
        "pass_accuracy_pct",
        "tackles",
        "interceptions",
        "duels_total",
        "duels_won",
        "dribbles_attempts",
        "dribbles_success",
        "dribbled_past",
        "fouls_drawn",
        "fouls_committed",
        "yellow_cards",
        "red_cards",
        "shirt_number",
        "substitute",
        "captain",
    ),  # fmt: skip
}


@dataclass
class ListedMatch:
    item: dict
    league: int
    season: int


@dataclass
class ApiLoad:
    """État du chargement API : entités, correspondances API -> interne, décomptes."""

    raw_dir: Path
    config: CollectConfig
    aliases: dict[int, int] = field(default_factory=dict)
    collision_exceptions: dict[tuple[int, int], str] = field(default_factory=dict)
    progress: Callable[[str], None] = lambda _message: None

    counts: Counter = field(default_factory=Counter)
    rows: Rows = field(default_factory=Rows)
    competition_ids: dict[int, int] = field(default_factory=dict)  # league API -> interne
    season_ids: dict[tuple[int, int], int] = field(default_factory=dict)  # (league, year) -> interne
    team_ids: dict[int, int] = field(default_factory=dict)  # team API -> interne
    player_ids: dict[int, int] = field(default_factory=dict)
    coach_ids: dict[int, int] = field(default_factory=dict)
    match_ids: dict[int, int] = field(default_factory=dict)  # fixture API -> interne
    match_teams: dict[int, tuple[int, int]] = field(default_factory=dict)  # fixture -> (home API, away API)
    match_goals: dict[int, tuple] = field(default_factory=dict)  # match interne -> score final
    match_info: dict[int, dict] = field(default_factory=dict)  # fixture -> compétition, saison, date, score 90 min

    # --- passe 0 : listes ----------------------------------------------------------------

    def league_kind(self) -> dict[int, str]:
        kinds: dict[int, str] = {}
        for blocks in self.config.tiers.values():
            for block in blocks:
                for league in block.leagues:
                    kinds.setdefault(league, block.kind)
        return kinds

    def read_lists(self) -> list[ListedMatch]:
        listed: dict[int, ListedMatch] = {}
        for league, season in raw_api.league_seasons(self.raw_dir):
            for item in raw_api.fixtures_list(self.raw_dir, league, season):
                fid = raw_api.fixture_id(item)
                if fid is not None:
                    # Un match listé dans deux saisons (rare) : la dernière lue l'emporte, dans l'ordre trié.
                    listed[fid] = ListedMatch(item, league, season)
        self.counts["matches_listed"] = len(listed)
        return [listed[fid] for fid in sorted(listed)]

    def team_countries(self) -> dict[int, str]:
        countries: dict[int, str] = {}
        root = self.raw_dir / raw_api.SOURCE / "teams"
        if not root.is_dir():
            return countries
        for league_dir in sorted(root.iterdir()):
            for path in _latest_files(league_dir):
                for item in raw_api.response(path):
                    team = item.get("team") or {}
                    if team.get("id") is not None and team.get("country"):
                        countries[int(team["id"])] = team["country"]
        return countries

    def build_reference(self, listed: list[ListedMatch]) -> None:
        """Compétitions, saisons, équipes et matchs, à partir des listes."""
        kinds = self.league_kind()
        leagues: dict[int, dict] = {}
        season_dates: dict[tuple[int, int], list[dt.date]] = defaultdict(list)
        team_names: dict[int, tuple[tuple[int, int], str]] = {}
        for match in listed:
            league = match.item.get("league") or {}
            leagues.setdefault(match.league, league)
            kickoff = raw_api.kickoff(match.item)
            if kickoff is not None:
                season_dates[(match.league, match.season)].append(kickoff.date())
            else:
                season_dates.setdefault((match.league, match.season), [])
            for side in ("home", "away"):
                team = (match.item.get("teams") or {}).get(side) or {}
                if team.get("id") is None:
                    continue
                key = (match.season, match.league)
                previous = team_names.get(int(team["id"]))
                if previous is None or key >= previous[0]:  # nom de la saison la plus récente
                    team_names[int(team["id"])] = (key, team.get("name") or str(team["id"]))

        for internal, league_id in enumerate(sorted(leagues), start=1):
            league = leagues[league_id]
            self.competition_ids[league_id] = internal
            self.rows.add(
                "competition",
                (
                    internal,
                    league.get("name") or str(league_id),
                    league.get("country"),
                    league_id,
                    kinds.get(league_id),
                ),
            )
        for internal, (league_id, year) in enumerate(sorted(season_dates), start=1):
            dates = season_dates[(league_id, year)]
            first, last = (min(dates), max(dates)) if dates else (dt.date(year, 7, 1), dt.date(year + 1, 6, 30))
            self.season_ids[(league_id, year)] = internal
            self.rows.add(
                "season",
                (internal, self.competition_ids[league_id], season_label(year, first, last), first, last, year),
            )
        countries = self.team_countries()
        for internal, team_id in enumerate(sorted(team_names), start=1):
            self.team_ids[team_id] = internal
            self.rows.add("team", (internal, team_names[team_id][1], countries.get(team_id), team_id, "api"))

        for internal, match in enumerate(listed, start=1):
            self._add_match(internal, match)

    def _add_match(self, internal: int, match: ListedMatch) -> None:
        item = match.item
        fid = raw_api.fixture_id(item)
        teams = item.get("teams") or {}
        home, away = (teams.get("home") or {}).get("id"), (teams.get("away") or {}).get("id")
        if home is None or away is None:
            self.counts["matches_without_teams"] += 1
            return
        kickoff = raw_api.kickoff(item)
        short = ((item.get("fixture") or {}).get("status") or {}).get("short")
        status, excluded, reason = match_status(short)
        goals, score = item.get("goals") or {}, item.get("score") or {}
        fulltime, penalty = score.get("fulltime") or {}, score.get("penalty") or {}
        self.match_ids[fid] = internal
        self.match_teams[fid] = (int(home), int(away))
        self.match_goals[internal] = (goals.get("home"), goals.get("away"))
        # Pour l'appariement football-data (load_external) : jamais affiché ni exporté.
        self.match_info[fid] = {
            "league": match.league,
            "season": match.season,
            "date": kickoff.date() if kickoff else None,
            "goals_90": (fulltime.get("home"), fulltime.get("away")),
        }
        self.counts[f"matches_status_{status}"] += 1
        if excluded:
            self.counts[f"matches_excluded_{reason}"] += 1
        self.rows.add(
            "match",
            (
                internal,
                self.competition_ids[match.league],
                self.season_ids[(match.league, match.season)],
                kickoff or dt.datetime(match.season, 7, 1, tzinfo=dt.UTC),
                self.team_ids[int(home)],
                self.team_ids[int(away)],
                goals.get("home"),
                goals.get("away"),
                status,
                fid,
                kickoff,
                short,
                (item.get("league") or {}).get("round"),
                fulltime.get("home"),
                fulltime.get("away"),
                penalty.get("home"),
                penalty.get("away"),
                excluded,
                reason,
                "api",
            ),
        )

    # --- passe 1 : catalogue ----------------------------------------------------------------

    def details(self) -> Iterator[tuple[int, dict]]:
        """(fixture, détail) de tous les matchs listés, par compétition-saison puis identifiant."""
        for league, season in raw_api.league_seasons(self.raw_dir):
            items = {raw_api.fixture_id(i): i for i in raw_api.fixture_details(self.raw_dir, league, season)}
            for fid in sorted(f for f in items if f is not None):
                yield fid, items[fid]

    def catalog(self) -> None:
        players, days, teams, fixtures = array("q"), array("q"), array("q"), array("q")
        self.names: dict[int, Counter] = defaultdict(Counter)
        self.coach_names: dict[int, str] = {}
        self.resolved_candidates: set[tuple[int, int]] = set()  # (match, joueur) « deux numéros » résolus (2b)
        self._detailed: set[int] = set()  # matchs qui ont un détail
        seen_details = 0
        for fid, item in self.details():
            if fid not in self.match_ids:
                self.counts["details_without_list"] += 1
                continue
            seen_details += 1
            self._detailed.add(fid)
            lineups = [x for x in item.get("lineups") or [] if isinstance(x, dict)]
            stats = [x for x in item.get("players") or [] if isinstance(x, dict)]
            for lineup in lineups:
                coach = lineup.get("coach") or {}
                if coach.get("id"):
                    self.coach_names[int(coach["id"])] = coach.get("name") or str(coach["id"])
                for entry in [*(lineup.get("startXI") or []), *(lineup.get("substitutes") or [])]:
                    player = (entry or {}).get("player") or {}
                    if player.get("id") and player.get("name"):
                        self.names[int(player["id"])][player["name"]] += 1
            for block in stats:
                for entry in block.get("players") or []:
                    player = (entry or {}).get("player") or {}
                    if player.get("id") and player.get("name"):
                        self.names[int(player["id"])][player["name"]] += 1
            classified = col.classify_match(lineups, stats)
            for pid in classified.collisions:
                if classified.resolved_number(pid) is not None:
                    self.resolved_candidates.add((fid, pid))
            kickoff = raw_api.kickoff(item)
            if kickoff is None:
                continue
            day = kickoff.date().toordinal()
            for pid, team in classified.team.items():
                players.append(pid)
                days.append(day)
                teams.append(team)
                fixtures.append(fid)
        self.counts["details_loaded"] = seen_details
        self.progress(f"catalogue : {seen_details} détails, {len(players)} présences")
        self.same_day = col.same_day_collisions(players, days, teams, fixtures)
        # Joueurs qui ont au moins une présence normale hors collision « même jour ».
        presences = Counter(players.tolist())
        for pid, _ in self.same_day:
            presences[pid] -= 1
        self.with_normal_presence = {pid for pid, n in presences.items() if n > 0}

        self.births = col.BirthIndex()
        self.profile_names: dict[int, str] = {}
        self.nationalities: dict[int, str] = {}
        self._read_profiles()
        self.birth_collisions = self.births.collisions()
        self.counts["collision_ids_same_day"] = len({pid for pid, _ in self.same_day})
        self.counts["collision_ids_birth"] = len(self.birth_collisions)

    def _read_profiles(self) -> None:
        root = self.raw_dir / raw_api.SOURCE / "players"
        if root.is_dir():
            for league_dir in sorted(root.iterdir()):
                for season_dir in sorted(league_dir.iterdir()):
                    season = int(season_dir.name.split("=")[1])
                    for path in _latest_files(season_dir):
                        for item in raw_api.response(path):
                            self._profile(item.get("player") or {}, season)
        targeted = self.raw_dir / raw_api.SOURCE / "player_profiles"
        if targeted.is_dir():
            for path in _latest_files(targeted):
                # Saison inconnue : l'année de collecte, valeur actuelle de l'API (comme raw_check).
                for item in raw_api.response(path):
                    self._profile(item.get("player") or {}, _version_year(path))

    def _profile(self, player: dict, season: int) -> None:
        if not player.get("id"):
            return
        pid = int(player["id"])
        self.births.add(pid, (player.get("birth") or {}).get("date"), season)
        full = " ".join(part for part in (player.get("firstname"), player.get("lastname")) if part)
        if full or player.get("name"):
            self.profile_names[pid] = full or player["name"]
        if player.get("nationality"):
            self.nationalities[pid] = player["nationality"]

    def excluded(self, fid: int, pid: int, classified: col.MatchPlayers) -> bool:
        """Entrée (match, joueur) exclue pour collision (ADR-0020), exceptions YAML comprises."""
        override = self.collision_exceptions.get((fid, pid))
        if override is not None:
            return override == "exclude"
        if pid in self.birth_collisions or (pid, fid) in self.same_day:
            return True
        return pid in classified.collisions and classified.resolved_number(pid) is None

    def build_players(self) -> None:
        """Joueurs créés : ceux qui ont au moins une entrée gardée, après alias (ADR-0008, règle 1)."""
        kept = self.with_normal_presence - self.birth_collisions
        # Collisions « deux numéros » résolues (2b) : pas de présence normale, mais une entrée gardée.
        resolved = {
            pid
            for fid, pid in self.resolved_candidates
            if pid not in self.birth_collisions and (pid, fid) not in self.same_day
            and self.collision_exceptions.get((fid, pid)) != "exclude"
        }  # fmt: skip
        self.counts["collision_entries_resolved_2b"] = len(resolved)
        kept |= resolved
        kept |= {pid for (_, pid), action in self.collision_exceptions.items() if action == "keep"}
        kept = {self.aliases.get(pid, pid) for pid in kept}
        for internal, pid in enumerate(sorted(kept), start=1):
            self.player_ids[pid] = internal
            birth = self.births.retained(pid) if pid not in self.birth_collisions else None
            name = self.profile_names.get(pid) or (
                self.names[pid].most_common(1)[0][0] if self.names.get(pid) else str(pid)
            )
            self.rows.add("player", (internal, name, birth, self.nationalities.get(pid), pid))
        for internal, cid in enumerate(sorted(self.coach_names), start=1):
            self.coach_ids[cid] = internal
            self.rows.add("coach", (internal, cid, self.coach_names[cid]))
        self.counts["players"] = len(self.player_ids)
        self.counts["coaches"] = len(self.coach_ids)

    # --- passe 2 : émission --------------------------------------------------------------

    def emit(self) -> None:
        lineup_id = stats_id = tms_id = 0
        team_match: dict[tuple[int, int], dict] = {}  # (fixture, team API) -> champs de team_match
        for fid, item in self.details():
            if fid not in self.match_ids:
                continue
            match_id = self.match_ids[fid]
            home, away = self.match_teams[fid]
            lineups = [x for x in item.get("lineups") or [] if isinstance(x, dict)]
            stats = [x for x in item.get("players") or [] if isinstance(x, dict)]
            classified = col.classify_match(lineups, stats)
            per_team = {team: {"unknown": 0, "excluded": 0, "coach": None, "formation": None} for team in (home, away)}

            seen_lineup: set[int] = set()
            for lineup in lineups:
                team = (lineup.get("team") or {}).get("id")
                if team not in per_team:
                    self.counts["lineups_other_team"] += 1
                    continue
                coach = (lineup.get("coach") or {}).get("id")
                per_team[team]["coach"] = self.coach_ids.get(int(coach)) if coach else None
                per_team[team]["formation"] = lineup.get("formation")
                for started, key in ((True, "startXI"), (False, "substitutes")):
                    for entry in lineup.get(key) or []:
                        player = (entry or {}).get("player") or {}
                        pid = player.get("id")
                        if not pid:  # absent ou 0 : joueur inconnu (ADR-0008, règle 1)
                            if started:
                                per_team[team]["unknown"] += 1
                            self.counts["lineup_unknown_entries"] += 1
                            continue
                        pid = int(pid)
                        if self.excluded(fid, pid, classified):
                            per_team[team]["excluded"] += 1
                            self.counts["lineup_entries_excluded"] += 1
                            self._track_top5(fid, pid, started, kept=False)
                            continue
                        self._track_top5(fid, pid, started, kept=True)
                        internal = self.player_ids.get(self.aliases.get(pid, pid))
                        if internal is None:  # ne devrait pas arriver : même règle que build_players
                            self.counts["lineup_entries_player_missing"] += 1
                            continue
                        if internal in seen_lineup:  # même entrée répétée (faux positif de collision)
                            self.counts["lineup_entries_repeated"] += 1
                            continue
                        seen_lineup.add(internal)
                        lineup_id += 1
                        pos = player.get("pos")
                        self.rows.add(
                            "lineup",
                            (lineup_id, match_id, self.team_ids[team], internal, started, pos, integer(player.get("number")),
                             player.get("grid"), POSITION_BUCKETS.get(pos)),
                        )  # fmt: skip

            seen_stats: set[int] = set()
            for block in stats:
                block_team = (block.get("team") or {}).get("id")
                for entry in block.get("players") or []:
                    entry = entry or {}
                    pid = (entry.get("player") or {}).get("id")
                    if not pid:
                        self.counts["stats_unknown_entries"] += 1
                        continue
                    pid = int(pid)
                    s = ((entry.get("statistics") or [{}])[0]) or {}
                    games = s.get("games") or {}
                    team = classified.team.get(pid, block_team)  # la composition fait foi
                    resolved = classified.resolved_number(pid)
                    if self.excluded(fid, pid, classified) or (
                        resolved is not None and games.get("number") != resolved
                    ):
                        if team in per_team:
                            per_team[team]["excluded"] += 1
                        self.counts["stats_entries_excluded"] += 1
                        continue
                    internal = self.player_ids.get(self.aliases.get(pid, pid))
                    if internal is None:
                        self.counts["stats_entries_player_missing"] += 1
                        continue
                    if team not in per_team:  # équipe ni à domicile ni à l'extérieur dans la liste
                        self.counts["stats_entries_other_team"] += 1
                        continue
                    if internal in seen_stats:
                        self.counts["stats_entries_repeated"] += 1
                        continue
                    seen_stats.add(internal)
                    stats_id += 1
                    self.rows.add("player_match_stats", self._stats_row(stats_id, match_id, internal, team, s))

            for block in item.get("statistics") or []:
                team = (block.get("team") or {}).get("id")
                if team not in per_team:
                    continue
                values = {}
                for stat in block.get("statistics") or []:
                    column = TEAM_STATS.get(stat.get("type"))
                    if column is not None:
                        parse = number if column in TEAM_STATS_DECIMAL else integer
                        values[column] = parse(stat.get("value"))
                per_team[team]["stats"] = values
            for team, fields in per_team.items():
                team_match[(fid, team)] = fields

        self._emit_team_match(team_match, tms_id)
        self._revision_criteria()
        for table in ("lineup", "player_match_stats"):
            self.counts[table] = self.rows.counts[table]

    def _track_top5(self, fid: int, pid: int, started: bool, kept: bool) -> None:
        """Titularisations gardées ou exclues, par (joueur, championnat du top 5, saison) : ADR-0020.

        Une entrée exclue n'a plus d'identifiant en base : ce décompte ne peut se faire
        qu'ici, pendant le chargement. Il ne sort que sous forme de nombres.
        """
        info = self.match_info.get(fid)
        if info is None or info["league"] not in TOP5_LEAGUES:
            return
        if not hasattr(self, "_top5_starts"):
            self._top5_starts: Counter = Counter()
            self._top5_excluded: Counter = Counter()
            self._top5_matches_hit: set[int] = set()
        if not kept:
            self._top5_matches_hit.add(fid)
        if started:
            key = (pid, info["league"], info["season"])
            self._top5_starts[key] += 1
            if not kept:
                self._top5_excluded[key] += 1

    def _revision_criteria(self) -> None:
        """Critères de révision de l'ADR-0020, en nombres (repris par check-referentiel)."""
        starts = getattr(self, "_top5_starts", Counter())
        excluded = getattr(self, "_top5_excluded", Counter())
        top5_league_matches = sum(
            1 for fid, info in self.match_info.items() if info["league"] in TOP5_LEAGUES and fid in self._detailed
        )
        shares = [excluded[key] / n for key, n in starts.items() if n >= REVISION_MIN_STARTS and excluded[key]]
        self.counts["top5_matches_detailed"] = top5_league_matches
        self.counts["top5_matches_with_excluded_entry"] = len(getattr(self, "_top5_matches_hit", set()))
        self.counts["top5_player_seasons_with_excluded_starts"] = len(shares)
        self.counts["top5_player_seasons_over_10pct"] = sum(1 for share in shares if share > REVISION_SHARE)
        self.counts["top5_max_share_excluded_pct"] = round(100 * max(shares), 1) if shares else 0

    def _stats_row(self, row_id: int, match_id: int, player: int, team: int, s: dict) -> tuple:
        games, goals, shots = s.get("games") or {}, s.get("goals") or {}, s.get("shots") or {}
        passes, tackles, duels = s.get("passes") or {}, s.get("tackles") or {}, s.get("duels") or {}
        dribbles, fouls, cards = s.get("dribbles") or {}, s.get("fouls") or {}, s.get("cards") or {}
        rating = number(games.get("rating"))
        return (
            row_id, match_id, player, self.team_ids[team], integer(games.get("minutes")),
            round(rating, 1) if rating is not None else None, POSITION_BUCKETS.get(games.get("position")),
            integer(goals.get("total")), integer(goals.get("assists")), integer(shots.get("total")),
            integer(shots.get("on")), integer(passes.get("key")),
            None,  # passes.accuracy : tantôt un nombre, tantôt un pourcentage selon les matchs ; non converti
            integer(tackles.get("total")), integer(tackles.get("interceptions")), integer(duels.get("total")),
            integer(duels.get("won")), integer(dribbles.get("attempts")), integer(dribbles.get("success")),
            integer(dribbles.get("past")), integer(fouls.get("drawn")), integer(fouls.get("committed")),
            integer(cards.get("yellow")), integer(cards.get("red")), integer(games.get("number")),
            games.get("substitute"), games.get("captain"),
        )  # fmt: skip

    def _emit_team_match(self, team_match: dict[tuple[int, int], dict], tms_id: int) -> None:
        """Deux lignes par match (domicile, extérieur), dans l'ordre des matchs ; identifiant = 2 × match - côté."""
        for fid, match_id in sorted(self.match_ids.items(), key=lambda pair: pair[1]):
            home_goals, away_goals = self.match_goals[match_id]
            for is_home, team in ((True, self.match_teams[fid][0]), (False, self.match_teams[fid][1])):
                fields = team_match.get((fid, team), {})
                row_id = 2 * match_id - (1 if is_home else 0)
                goals_for, goals_against = (home_goals, away_goals) if is_home else (away_goals, home_goals)
                xg = (fields.get("stats") or {}).get("expected_goals")
                opponent = team_match.get((fid, self.match_teams[fid][1 if is_home else 0]), {})
                xg_against = (opponent.get("stats") or {}).get("expected_goals")
                self.rows.add(
                    "team_match",
                    (row_id, match_id, self.team_ids[team], is_home, goals_for, goals_against, xg, xg_against,
                     fields.get("coach"), fields.get("formation"),
                     fields.get("unknown") if fields else None, fields.get("excluded") if fields else None),
                )  # fmt: skip
                if fields.get("stats"):
                    tms_id += 1
                    self.rows.add(
                        "team_match_stats",
                        (tms_id, row_id, *(fields["stats"].get(c) for c in TEAM_STATS_COLUMNS)),
                    )
        self.counts["team_match"] = self.rows.counts["team_match"]
        self.counts["team_match_stats"] = self.rows.counts["team_match_stats"]

    def run(self) -> Rows:
        listed = self.read_lists()
        self.progress(f"listes : {len(listed)} matchs")
        self.build_reference(listed)
        self.catalog()
        self.build_players()
        self.emit()
        return self.rows
