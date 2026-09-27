"""Planification : du fichier de paliers aux tâches de la file (ADR-0002).

Le plan se construit en plusieurs passes, car certaines tâches dépendent de
réponses pas encore collectées :

1. listes : `fixtures_list`, `teams`, `injuries`, `players` (page 1)... ;
2. dérivées, dès que leur liste est dans `data/raw/` :
   - `fixtures_detail` : lots de 20 matchs terminés, à partir de `fixtures_list` ;
   - `coachs` et `transfers` : une tâche par équipe, à partir de `teams`.
   Les pages 2 à N de `players` sont ajoutées par le runner dès que la page 1
   donne `paging.total`.

`plan` est idempotent : le relancer n'ajoute que ce qui manque (clé
canonique). `run` le relance automatiquement quand la file est vide.

Règles des lots de détails :
- seuls les matchs à statut terminal (FT, AET, PEN, AWD, WO) sont mis en lot ;
  les autres sont listés à part (table `deferred_fixtures`) ;
- un match déjà présent dans le journal (champ `fixture_ids`) ou déjà mis en
  lot (quel que soit le statut du lot) n'est jamais redemandé ;
- pour une coupe (`detail_teams_from`), seuls les matchs impliquant une équipe
  d'un championnat du palier de référence, la même saison, sont gardés.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from foot_predictor.collect.api_football import SOURCE, tasks
from foot_predictor.collect.api_football.coverage import LeagueCoverage, load_coverage
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.collect.api_football.tasks import DETAIL_BATCH_MAX, Task
from foot_predictor.rawstore.manifest import read_entries
from foot_predictor.rawstore.store import latest_version, read_envelope

DEFAULT_CONFIG_PATH = Path("config") / "collecte_api_football.yaml"

PLANNABLE_ENDPOINTS = {
    "fixtures_list", "fixtures_detail", "teams", "injuries", "players",
    "coachs", "transfers", "standings", "sidelined",
}
LEAGUE_SEASON_ENDPOINTS = ("fixtures_list", "teams", "injuries", "standings")
TEAM_ENDPOINTS = ("coachs", "transfers")
# Tâche omise quand /leagues déclare la saison non couverte pour ce drapeau.
COVERAGE_GATES = {"injuries": "injuries", "players": "players", "standings": "standings"}


# --- configuration --------------------------------------------------------------


@dataclass(frozen=True)
class SeasonSpec:
    first: int | None
    last: int
    requires_coverage: str | None = None


@dataclass(frozen=True)
class Block:
    name: str
    kind: str
    leagues: tuple[int, ...]
    seasons: SeasonSpec
    endpoints: tuple[str, ...]
    detail_teams_from: str | None = None


@dataclass(frozen=True)
class CollectConfig:
    reserve: int
    terminal_statuses: frozenset[str]
    tiers: dict[str, list[Block]]


class ConfigError(ValueError):
    pass


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> CollectConfig:
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return parse_config(raw)


def parse_config(raw: dict) -> CollectConfig:
    tiers: dict[str, list[Block]] = {}
    for tier, tier_raw in (raw.get("tiers") or {}).items():
        blocks = []
        for block_raw in (tier_raw or {}).get("blocks") or []:
            blocks.append(_parse_block(tier, block_raw))
        tiers[tier] = blocks
    for tier, blocks in tiers.items():
        for block in blocks:
            if block.detail_teams_from and block.detail_teams_from not in tiers:
                raise ConfigError(f"{tier}/{block.name} : palier de référence inconnu {block.detail_teams_from}")
    return CollectConfig(
        reserve=int(raw.get("reserve", 500)),
        terminal_statuses=frozenset(raw.get("terminal_statuses") or ["FT", "AET", "PEN", "AWD", "WO"]),
        tiers=tiers,
    )


def _parse_block(tier: str, raw: dict) -> Block:
    name = raw.get("name", "?")
    where = f"{tier}/{name}"
    endpoints = tuple(raw.get("endpoints") or ())
    unknown = set(endpoints) - PLANNABLE_ENDPOINTS
    if unknown:
        raise ConfigError(f"{where} : endpoints inconnus {sorted(unknown)}")
    if set(endpoints) & set(TEAM_ENDPOINTS) and "teams" not in endpoints:
        raise ConfigError(f"{where} : coachs et transfers exigent teams dans endpoints")
    kind = raw.get("kind")
    if kind not in ("league", "cup"):
        raise ConfigError(f"{where} : kind doit valoir league ou cup")
    seasons_raw = raw.get("seasons") or {}
    if "last" not in seasons_raw:
        raise ConfigError(f"{where} : seasons.last est obligatoire")
    return Block(
        name=name,
        kind=kind,
        leagues=tuple(int(x) for x in raw.get("leagues") or ()),
        seasons=SeasonSpec(
            first=seasons_raw.get("first"),
            last=int(seasons_raw["last"]),
            requires_coverage=seasons_raw.get("requires_coverage"),
        ),
        endpoints=endpoints,
        detail_teams_from=raw.get("detail_teams_from"),
    )


# --- lecture du brut ---------------------------------------------------------------


def fixture_ids_in_manifest(raw_dir: Path) -> set[int]:
    """Matchs dont le détail est déjà stocké (réponse 200 sans `errors`)."""
    ids: set[int] = set()
    for entry in read_entries(raw_dir, SOURCE):
        if entry.get("http_status") == 200 and not entry.get("errors") and entry.get("fixture_ids"):
            ids.update(entry["fixture_ids"])
    return ids


def _latest_body(raw_dir: Path, task: Task) -> dict | None:
    """Corps de la dernière réponse stockée pour cette tâche, si elle est exploitable."""
    path = latest_version(raw_dir, task.rel_dir, task.stem)
    if path is None:
        return None
    body = read_envelope(path)["body"]
    if not isinstance(body, dict) or body.get("errors"):
        return None
    return body


# --- planification ---------------------------------------------------------------


@dataclass
class PlanReport:
    tier: str
    added: Counter = field(default_factory=Counter)
    skipped: Counter = field(default_factory=Counter)  # raison -> nombre
    waiting: Counter = field(default_factory=Counter)  # type -> listes attendues
    deferred: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total_added(self) -> int:
        return sum(self.added.values())


_WAITING = object()


class Planner:
    def __init__(
        self,
        config: CollectConfig,
        raw_dir: Path,
        queue: WorkQueue,
        coverage: dict[int, LeagueCoverage] | None = None,
    ) -> None:
        self.config = config
        self.raw_dir = Path(raw_dir)
        self.queue = queue
        self.coverage = coverage if coverage is not None else load_coverage(self.raw_dir)
        self._known_detail_ids = fixture_ids_in_manifest(self.raw_dir) | queue.detail_fixture_ids()
        self._new: dict[str, Task] = {}

    def plan(self, tier: str) -> PlanReport:
        if tier not in self.config.tiers:
            raise ConfigError(f"Palier inconnu : {tier} (connus : {', '.join(self.config.tiers)})")
        report = PlanReport(tier)
        self._new = {}
        blocks = self.config.tiers[tier]
        if not blocks:
            report.warnings.append(f"{tier} : aucun bloc défini dans la configuration (à préciser).")
        if self.coverage is None:
            report.warnings.append(
                "Couverture inconnue (aucune réponse /leagues stockée) : lancer d'abord la commande coverage. "
                "Aucune saison n'est filtrée."
            )
        self._warn_if_earlier_tiers_pending(tier, report)

        for block in blocks:
            block_seasons: list[tuple[int, int]] = []
            for league in block.leagues:
                for season in self._seasons(block, league, report):
                    block_seasons.append((league, season))
                    self._plan_league_season(tier, block, league, season, report)
            self._plan_team_tasks(tier, block, block_seasons, report)
            if "sidelined" in block.endpoints:
                report.warnings.append(f"{block.name} : sidelined n'est pas encore planifiable (liste de joueurs à définir).")

        fresh = [task for task in self._new.values() if not self.queue.contains(task)]
        self.queue.add(fresh)
        report.added.update(task.task_type for task in fresh)
        self.queue.mark_tier_planned(tier)
        return report

    # --- saisons ---------------------------------------------------------------

    def _seasons(self, block: Block, league: int, report: PlanReport) -> list[int]:
        spec = block.seasons
        cov = self.coverage.get(league) if self.coverage is not None else None
        if self.coverage is not None and cov is None:
            report.warnings.append(f"{block.name} : identifiant {league} absent de /leagues, ignoré.")
            return []

        if spec.first is None:
            if cov is None:
                report.warnings.append(
                    f"{block.name} : saisons de {league} inconnues sans la commande coverage, ignoré."
                )
                return []
            candidates = sorted(year for year in cov.seasons if year <= spec.last)
        else:
            candidates = list(range(int(spec.first), spec.last + 1))
            if cov is not None:
                missing = [year for year in candidates if not cov.has_season(year)]
                report.skipped["saison absente de /leagues"] += len(missing)
                candidates = [year for year in candidates if cov.has_season(year)]

        if spec.requires_coverage and cov is not None:
            kept = [year for year in candidates if cov.flag(year, spec.requires_coverage)]
            report.skipped[f"saison sans {spec.requires_coverage}"] += len(candidates) - len(kept)
            candidates = kept
        return candidates

    def _covered(self, league: int, season: int, endpoint: str) -> bool:
        gate = COVERAGE_GATES.get(endpoint)
        if gate is None or self.coverage is None or league not in self.coverage:
            return True
        return self.coverage[league].flag(season, gate) is not False

    # --- tâches par (compétition, saison) -------------------------------------------

    def _plan_league_season(self, tier: str, block: Block, league: int, season: int, report: PlanReport) -> None:
        for endpoint in block.endpoints:
            if endpoint in TEAM_ENDPOINTS or endpoint == "sidelined":
                continue
            if not self._covered(league, season, endpoint):
                report.skipped[f"{endpoint} non couvert"] += 1
                continue
            if endpoint in LEAGUE_SEASON_ENDPOINTS:
                task = (tasks.fixtures_list_task(tier, league, season) if endpoint == "fixtures_list"
                        else tasks.league_season_task(tier, endpoint, league, season))
                self._propose(task)
            elif endpoint == "players":
                self._propose(tasks.players_task(tier, league, season, 1))
            elif endpoint == "fixtures_detail":
                self._plan_details(tier, block, league, season, report)

    def _plan_details(self, tier: str, block: Block, league: int, season: int, report: PlanReport) -> None:
        listing = tasks.fixtures_list_task(tier, league, season)
        body = _latest_body(self.raw_dir, listing)
        if body is None:
            if self._is_waiting(listing):
                report.waiting["fixtures_detail"] += 1
            return

        team_filter = None
        if block.detail_teams_from:
            team_filter = self._reference_teams(block.detail_teams_from, season)
            if team_filter is _WAITING:
                report.waiting["fixtures_detail"] += 1
                return

        terminal, deferred = [], []
        for item in body.get("response") or []:
            fixture = item.get("fixture") or {}
            status = (fixture.get("status") or {}).get("short")
            if status in self.config.terminal_statuses:
                terminal.append(item)
            else:
                deferred.append((fixture["id"], league, season, status, fixture.get("date")))
        self.queue.add_deferred(deferred)
        # Un match mis de côté lors d'une liste précédente peut être terminé depuis.
        self.queue.remove_deferred(item["fixture"]["id"] for item in terminal)
        report.deferred += len(deferred)

        if team_filter is not None:
            kept = [item for item in terminal if _team_ids(item) & team_filter]
            report.skipped["coupe : aucune équipe suivie"] += len(terminal) - len(kept)
            terminal = kept
        terminal_ids = [item["fixture"]["id"] for item in terminal]

        to_fetch = sorted(i for i in set(terminal_ids) if i not in self._known_detail_ids)
        report.skipped["match déjà présent ou déjà en lot"] += len(set(terminal_ids)) - len(to_fetch)
        for batch in chunks(to_fetch, DETAIL_BATCH_MAX):
            self._propose(tasks.fixtures_detail_task(tier, league, season, batch))
            self._known_detail_ids.update(batch)

    def _reference_teams(self, reference_tier: str, season: int) -> set[int] | object:
        """Équipes des championnats du palier de référence pour cette saison,
        ou `_WAITING` si une de leurs listes est encore attendue."""
        teams: set[int] = set()
        for block in self.config.tiers[reference_tier]:
            if block.kind != "league":
                continue
            for league in block.leagues:
                listing = tasks.fixtures_list_task(reference_tier, league, season)
                body = _latest_body(self.raw_dir, listing)
                if body is not None:
                    for item in body.get("response") or []:
                        teams |= _team_ids(item)
                elif self._is_waiting(listing):
                    return _WAITING
        return teams

    # --- tâches par équipe ---------------------------------------------------------

    def _plan_team_tasks(self, tier: str, block: Block, block_seasons: list[tuple[int, int]], report: PlanReport) -> None:
        endpoints = [e for e in block.endpoints if e in TEAM_ENDPOINTS]
        if not endpoints:
            return
        team_ids: set[int] = set()
        for league, season in block_seasons:
            listing = tasks.league_season_task(tier, "teams", league, season)
            body = _latest_body(self.raw_dir, listing)
            if body is None:
                if self._is_waiting(listing):
                    report.waiting["coachs/transfers"] += 1
                continue
            for item in body.get("response") or []:
                team_id = (item.get("team") or {}).get("id")
                if team_id is not None:
                    team_ids.add(team_id)
        for endpoint in endpoints:
            for team_id in sorted(team_ids):
                self._propose(tasks.team_task(tier, endpoint, team_id))

    # --- utilitaires ---------------------------------------------------------------

    def _propose(self, task: Task) -> None:
        self._new.setdefault(task.key, task)

    def _is_waiting(self, task: Task) -> bool:
        """Vrai si la réponse de cette tâche est encore attendue (en file ou
        proposée dans cette passe) ; faux si elle a échoué ou n'est pas prévue."""
        return task.key in self._new or self.queue.status_of(task) == "pending"

    def _warn_if_earlier_tiers_pending(self, tier: str, report: PlanReport) -> None:
        pending: Counter = Counter()
        for other_tier, _, status, count in self.queue.counts():
            if status == "pending" and other_tier < tier:
                pending[other_tier] += count
        for earlier, count in sorted(pending.items()):
            report.warnings.append(
                f"{earlier} a encore {count} tâches pending : ADR-0002 demande de finir et contrôler "
                f"un palier avant de commencer le suivant."
            )


def _team_ids(item: dict) -> set[int]:
    teams = item.get("teams") or {}
    return {side["id"] for side in (teams.get("home"), teams.get("away")) if side and side.get("id") is not None}


def chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]
