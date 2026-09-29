"""Journal T-60 : compositions annoncées avant le coup d'envoi (ADR-0010).

But unique : vérifier l'hypothèse de l'évaluation H2 en rejeu, à savoir que
le onze du détail de match (collecté après coup) est celui annoncé avant le
coup d'envoi. Jamais utilisé pour évaluer un modèle : l'échantillon est trop
petit.

Commande `t60 --date AAAA-MM-JJ` (tâche planifiée les jours de match) :

1. `/fixtures?date=<jour>&timezone=UTC` : tous les matchs du jour, avec leur
   heure réelle (1 requête). Seuls ceux du top 5 non commencés sont suivis ;
2. pour chaque match, à partir de `lead` minutes avant le coup d'envoi (40 par
   défaut), `/fixtures?ids=` par lots de 20, toutes les `interval` minutes
   (5 par défaut), jusqu'à obtenir les deux compositions (11 titulaires
   chacune) ou jusqu'au coup d'envoi. La documentation v3 annonce les
   compositions « between 20 and 40 minutes before the fixture » ;
3. chaque réponse est stockée sous `api_football/daily/<jour>/...` avec le
   journal habituel. Le plafond `--max-requests` s'applique à l'exécution.

Coût : 1 requête, plus un lot de 20 matchs par passage (toutes les 5 minutes)
tant qu'au moins un match attend ses compositions. Les matchs dont les
fenêtres se chevauchent partagent les mêmes lots. Pire cas d'un samedi du top
5 (aucune composition publiée) : environ 70 requêtes ; en pratique, les
compositions arrivent vers T-30 et le coût est de l'ordre de 40.

Ces réponses d'avant-match ne comptent jamais comme « détail reçu » : le
planificateur ignore `daily/` (voir `plan.fixture_ids_in_manifest`), sinon
le détail d'après-match ne serait jamais demandé.

Commande `t60-report` (lecture seule, session de gel) : pour chaque match
annoncé dont le détail d'après-match est dans le brut, part des titulaires
identiques. Elle ne lit que les compositions : ni score, ni buts (scellé,
ADR-0012).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect.api_football import SOURCE
from foot_predictor.collect.api_football.client import ApiFootballClient, CollectStop, HttpError, TransientError
from foot_predictor.collect.api_football.runner import store_response
from foot_predictor.collect.api_football.tasks import DETAIL_BATCH_MAX
from foot_predictor.rawstore.store import SUFFIX, VERSION_SEPARATOR, read_envelope

logger = logging.getLogger(__name__)

DAILY_DIR = f"{SOURCE}/daily"
DEFAULT_LEAD = dt.timedelta(minutes=40)  # « between 20 and 40 minutes before »
DEFAULT_INTERVAL = dt.timedelta(minutes=5)
NOT_STARTED = frozenset({"NS", "TBD"})
STARTERS = 11


@dataclass
class Match:
    fixture_id: int
    league: int
    kickoff: dt.datetime


def kickoff_of(item: dict) -> dt.datetime | None:
    fixture = item.get("fixture") or {}
    if fixture.get("timestamp") is not None:
        return dt.datetime.fromtimestamp(int(fixture["timestamp"]), dt.timezone.utc)
    try:
        return dt.datetime.fromisoformat(str(fixture.get("date"))).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def starting_elevens(item: dict) -> dict[int, list[int | None]]:
    """Titulaires annoncés par équipe : {team.id: [player.id, ...]}."""
    elevens: dict[int, list[int | None]] = {}
    for lineup in item.get("lineups") or []:
        team = ((lineup or {}).get("team") or {}).get("id")
        if team is not None:
            elevens[int(team)] = [((entry or {}).get("player") or {}).get("id") for entry in lineup.get("startXI") or []]
    return elevens


def has_lineups(item: dict) -> bool:
    elevens = starting_elevens(item)
    return len(elevens) == 2 and all(len(players) == STARTERS for players in elevens.values())


def day_matches(body: dict, leagues: Iterable[int]) -> list[Match]:
    """Matchs non commencés des compétitions suivies, triés par heure."""
    wanted = set(leagues)
    matches = []
    for item in body.get("response") or []:
        league = ((item or {}).get("league") or {}).get("id")
        fixture_id = ((item or {}).get("fixture") or {}).get("id")
        status = (((item or {}).get("fixture") or {}).get("status") or {}).get("short")
        kickoff = kickoff_of(item or {})
        if league in wanted and fixture_id is not None and status in NOT_STARTED and kickoff is not None:
            matches.append(Match(int(fixture_id), int(league), kickoff))
    return sorted(matches, key=lambda m: (m.kickoff, m.fixture_id))


def batch_stem(fixture_ids: Iterable[int]) -> str:
    ids = "-".join(str(i) for i in sorted(fixture_ids))
    return hashlib.sha256(ids.encode("ascii")).hexdigest()[:12]


@dataclass
class T60Report:
    day: dt.date
    matches: int = 0  # matchs du top 5 à suivre
    announced: dict[int, dt.datetime] = field(default_factory=dict)  # match -> première réponse avec compositions
    missed: list[int] = field(default_factory=list)  # coup d'envoi atteint sans compositions
    dropped: list[int] = field(default_factory=list)  # reportés, annulés... en cours de journée
    requests: int = 0
    stop_reason: str | None = None


class T60Collector:
    def __init__(
        self,
        client: ApiFootballClient,
        raw_dir: Path,
        day: dt.date,
        leagues: Iterable[int],
        *,
        lead: dt.timedelta = DEFAULT_LEAD,
        interval: dt.timedelta = DEFAULT_INTERVAL,
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.raw_dir = Path(raw_dir)
        self.day = day
        self.leagues = tuple(leagues)
        self.lead = lead
        self.interval = interval
        self._now = now
        self._sleep = sleep
        self.report = T60Report(day)
        self.folder = f"{DAILY_DIR}/{day.isoformat()}"

    def run(self) -> T60Report:
        try:
            response = self.client.get("/fixtures", {"date": self.day.isoformat(), "timezone": "UTC"})
            store_response(self.raw_dir, f"{self.folder}/fixtures", "day", response)
            if response.errors:
                self.report.stop_reason = f"liste du jour en erreur : {response.errors}"
                return self.report
            pending = {m.fixture_id: m for m in day_matches(response.body, self.leagues)}
            self.report.matches = len(pending)
            logger.info("T-60 %s : %s match(s) du top 5 à suivre", self.day, len(pending))
            self._follow(pending)
        except CollectStop as exc:
            self.report.stop_reason = str(exc)
            logger.warning("Arrêt propre : %s", exc)
        finally:
            self.report.requests = self.client.requests_made
        return self.report

    def _follow(self, pending: dict[int, Match]) -> None:
        while pending:
            now = self._now()
            for fixture_id in [f for f, m in pending.items() if now >= m.kickoff]:
                self.report.missed.append(fixture_id)
                del pending[fixture_id]
            if not pending:
                return
            open_ids = sorted(f for f, m in pending.items() if m.kickoff - self.lead <= now)
            if not open_ids:
                wake = min(m.kickoff - self.lead for m in pending.values())
                self._sleep(max((wake - now).total_seconds(), 1.0))
                continue
            for start in range(0, len(open_ids), DETAIL_BATCH_MAX):
                self._poll(open_ids[start:start + DETAIL_BATCH_MAX], pending)
            if pending:
                self._sleep(self.interval.total_seconds())

    def _poll(self, fixture_ids: list[int], pending: dict[int, Match]) -> None:
        params = {"ids": "-".join(str(i) for i in fixture_ids)}
        try:
            response = self.client.get("/fixtures", params)
        except (TransientError, HttpError) as exc:
            logger.warning("T-60 lot %s : %s ; nouvel essai au prochain passage", params["ids"], exc)
            return
        store_response(self.raw_dir, f"{self.folder}/lineups", batch_stem(fixture_ids), response)
        if response.errors:
            logger.warning("T-60 lot %s : errors %s", params["ids"], response.errors)
            return
        for item in response.body.get("response") or []:
            fixture_id = ((item or {}).get("fixture") or {}).get("id")
            if fixture_id not in pending:
                continue
            status = (((item.get("fixture") or {}).get("status")) or {}).get("short")
            if has_lineups(item):
                self.report.announced[fixture_id] = self._now()
                del pending[fixture_id]
            elif status not in NOT_STARTED:
                self.report.dropped.append(fixture_id)  # reporté, annulé, déjà commencé...
                del pending[fixture_id]
            else:
                kickoff = kickoff_of(item)
                if kickoff is not None:
                    pending[fixture_id].kickoff = kickoff  # heure mise à jour par l'API


class KeepAwake:
    """Empêche la mise en veille automatique de Windows pendant `t60`.

    La commande dort des heures entre deux fenêtres de coup d'envoi : sans
    cela, le portable se mettrait en veille et raterait les compositions.
    `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` garde le
    système éveillé (pas l'écran) tant que le processus tourne ; l'état est
    rétabli à la sortie. Sans effet hors de Windows. La fermeture du capot
    reste une mise en veille forcée : laisser le portable ouvert et branché.
    """

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __enter__(self) -> KeepAwake:
        self._set(self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED)
        return self

    def __exit__(self, *exc) -> None:
        self._set(self.ES_CONTINUOUS)

    @staticmethod
    def _set(flags: int) -> None:
        import sys

        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.SetThreadExecutionState(flags)


def report_lines(report: T60Report) -> list[str]:
    lines = [f"Journal T-60 du {report.day} : {report.matches} match(s) du top 5 suivis.",
             f"  compositions obtenues avant le coup d'envoi : {len(report.announced)}",
             f"  coup d'envoi atteint sans compositions : {len(report.missed)}",
             f"  sortis du suivi (reportés, annulés, commencés) : {len(report.dropped)}",
             f"Requêtes envoyées : {report.requests}"]
    if report.stop_reason:
        lines.append(f"Arrêt : {report.stop_reason}")
    return lines


def expected_requests(matches: list[Match], lead: dt.timedelta, interval: dt.timedelta) -> int:
    """Pire cas d'une journée (aucune composition publiée avant le coup
    d'envoi) : même boucle que `T60Collector._follow`, sans requête."""
    requests, pending = 1, list(matches)  # 1 : liste du jour
    if not pending:
        return requests
    now = min(m.kickoff for m in pending) - lead
    while pending:
        pending = [m for m in pending if now < m.kickoff]
        open_count = sum(1 for m in pending if m.kickoff - lead <= now)
        if pending and not open_count:
            now = min(m.kickoff for m in pending) - lead
            continue
        requests += -(-open_count // DETAIL_BATCH_MAX)
        now += interval
    return requests


# --- bilan (lecture seule) ------------------------------------------------------------------


@dataclass
class Comparison:
    fixture_id: int
    league: int
    compared: int = 0  # titulaires annoncés comparés (identifiant connu)
    identical: int = 0
    differences: list[tuple[int, int | None, int | None]] = field(default_factory=list)  # (équipe, annoncé, final)


def _bodies(directory: Path) -> Iterable[tuple[Path, dict]]:
    """Corps lisibles, du plus ancien au plus récent (horodatage de version) :
    un même match passe d'un lot à l'autre au fil de la journée."""
    if not directory.is_dir():
        return
    paths = directory.rglob(f"*{SUFFIX}")
    for path in sorted(paths, key=lambda p: (p.name.removesuffix(SUFFIX).rpartition(VERSION_SEPARATOR)[2], p.name)):
        try:
            body = read_envelope(path).get("body")
        except (OSError, EOFError, ValueError):
            continue
        if isinstance(body, dict) and not body.get("errors"):
            yield path, body


def announced_lineups(raw_dir: Path) -> dict[int, tuple[int, int, dict[int, list[int | None]]]]:
    """Compositions annoncées : {match: (compétition, saison, {équipe: titulaires})}.

    Pour chaque match, la dernière réponse d'avant-match qui contient les deux
    compositions.
    """
    found: dict[int, tuple[int, int, dict]] = {}
    for _, body in _bodies(Path(raw_dir) / DAILY_DIR):
        for item in body.get("response") or []:
            fixture = (item or {}).get("fixture") or {}
            status = (fixture.get("status") or {}).get("short")
            league = (item.get("league") or {})
            if fixture.get("id") is None or status not in NOT_STARTED or not has_lineups(item):
                continue
            found[int(fixture["id"])] = (int(league.get("id") or 0), int(league.get("season") or 0),
                                         starting_elevens(item))
    return found


def final_lineups(raw_dir: Path, wanted: dict[int, tuple[int, int, dict]]) -> dict[int, dict[int, list[int | None]]]:
    """Titulaires du détail d'après-match (dernière version), pour les matchs voulus.

    Seuls les dossiers `fixtures_detail/league=L/season=S` des matchs annoncés
    sont lus, et seules les compositions sont extraites.
    """
    folders = {(league, season) for league, season, _ in wanted.values()}
    final: dict[int, dict[int, list[int | None]]] = {}
    for league, season in sorted(folders):
        for _, body in _bodies(Path(raw_dir) / SOURCE / "fixtures_detail" / f"league={league}" / f"season={season}"):
            for item in body.get("response") or []:
                fixture_id = ((item or {}).get("fixture") or {}).get("id")
                if fixture_id in wanted and has_lineups(item):
                    final[int(fixture_id)] = starting_elevens(item)
    return final


def compare_lineups(raw_dir: Path) -> tuple[list[Comparison], int]:
    """(comparaisons, nombre de matchs annoncés sans détail d'après-match)."""
    announced = announced_lineups(raw_dir)
    final = final_lineups(raw_dir, announced)
    comparisons = []
    for fixture_id, (league, _, before) in sorted(announced.items()):
        after = final.get(fixture_id)
        if after is None:
            continue
        comparison = Comparison(fixture_id, league)
        for team, players in sorted(before.items()):
            kept = set(after.get(team, []))
            for player in players:
                if player is None:
                    continue
                comparison.compared += 1
                if player in kept:
                    comparison.identical += 1
            for missing, extra in zip(sorted(p for p in players if p is not None and p not in kept),
                                      sorted(p for p in after.get(team, []) if p is not None and p not in set(players))):
                comparison.differences.append((team, missing, extra))
        comparisons.append(comparison)
    return comparisons, len(announced) - len(comparisons)


def comparison_lines(comparisons: list[Comparison], without_detail: int) -> list[str]:
    """Bilan chiffré, sans identifiant de joueur (versionnable)."""
    compared = sum(c.compared for c in comparisons)
    identical = sum(c.identical for c in comparisons)
    changed = [c for c in comparisons if c.identical < c.compared]
    share = f"{100 * identical / compared:.2f} %" if compared else "—"
    lines = [
        f"Matchs annoncés et détaillés après coup : {len(comparisons)} (annoncés sans détail : {without_detail})",
        f"Titulaires comparés : {compared} ; identiques : {identical} ({share})",
        f"Matchs avec au moins un titulaire différent : {len(changed)}",
        "Critère de révision de l'ADR-0010 : plus de 2 % de titulaires différents.",
    ]
    per_league: dict[int, list[Comparison]] = {}
    for c in comparisons:
        per_league.setdefault(c.league, []).append(c)
    for league, items in sorted(per_league.items()):
        n, same = sum(c.compared for c in items), sum(c.identical for c in items)
        lines.append(f"  compétition {league} : {len(items)} match(s), {same}/{n} titulaires identiques")
    return lines
