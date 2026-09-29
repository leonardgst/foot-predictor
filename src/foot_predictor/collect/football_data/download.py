"""Téléchargement des CSV de football-data dans le dossier des bruts externes.

Arborescence (ADR-0003, même logique que l'API) :

    <raw_dir>/football_data/csv/season=2023/E0__<horodatage>.csv
    <raw_dir>/_manifest/football_data.jsonl       une ligne par fichier stocké
    <raw_dir>/_lock/collecte.lock                 verrou pendant un téléchargement

Règles :
- le fichier est stocké **octet pour octet** ; une nouvelle version s'ajoute à
  côté, jamais d'écrasement ;
- au plus une requête par seconde, `User-Agent` qui identifie le projet ;
- plafond de téléchargements obligatoire (`max_requests`) ;
- un fichier déjà présent n'est pas redemandé, sauf `redownload` ;
- une réponse qui n'est pas un CSV de football-data (HTTP ≠ 200, page HTML)
  n'est pas stockée : elle est signalée, et le code de retour vaut 1.

Conditions d'utilisation lues le 2026-09-29 (ADR-0023) : usage réservé aux
particuliers, pour la prédiction de matchs, sans usage commercial.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import requests

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data import SOURCE
from foot_predictor.rawstore.lock import CollectLock
from foot_predictor.rawstore.manifest import append_entry

BASE_URL = "https://www.football-data.co.uk/mmz4281"
USER_AGENT = "foot-predictor-research-bot/1.0 (personal educational project)"
SUFFIX = ".csv"
MIN_INTERVAL_SECONDS = 1.0
TIMEOUT_SECONDS = 30

# Top 5 et deuxièmes divisions (codes vérifiés sur football-data.co.uk/data.php, 2026-09-29).
DIVISIONS = ("E0", "SP1", "D1", "I1", "F1", "E1", "SP2", "D2", "I2", "F2")
FIRST_SEASON, LAST_SEASON = 2000, 2026  # 2000-01 à 2026-27 (année de début, comme l'API)


def season_code(season: int) -> str:
    """2023 -> « 2324 », code de saison des URL de football-data."""
    return f"{season % 100:02d}{(season + 1) % 100:02d}"


def season_dir(season: int) -> str:
    return f"{SOURCE}/csv/season={season}"


def file_url(division: str, season: int) -> str:
    return f"{BASE_URL}/{season_code(season)}/{division}.csv"


def looks_like_csv(data: bytes) -> bool:
    """Un CSV de football-data commence par la colonne « Div » (BOM UTF-8 éventuel)."""
    return data.lstrip(b"\xef\xbb\xbf").lstrip()[:4] == b"Div,"


@dataclass(frozen=True)
class Target:
    division: str
    season: int

    @property
    def url(self) -> str:
        return file_url(self.division, self.season)


def plan(
    raw_dir: Path, divisions: tuple[str, ...], seasons: range, *, redownload: bool = False
) -> tuple[list[Target], list[Target]]:
    """(à télécharger, déjà présents). Lecture seule : ne crée rien."""
    todo, present = [], []
    for season in seasons:
        for division in divisions:
            target = Target(division, season)
            exists = raw_bytes.latest(raw_dir, season_dir(season), division, SUFFIX) is not None
            (present if exists and not redownload else todo).append(target)
    return todo, present


@dataclass
class DownloadReport:
    stored: list[Target] = field(default_factory=list)
    failed: list[tuple[Target, str]] = field(default_factory=list)
    skipped_cap: list[Target] = field(default_factory=list)  # au-delà du plafond


class Throttle:
    """Au plus une requête par `interval` secondes (mesuré de début à début)."""

    def __init__(
        self,
        interval: float = MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval, self._clock, self._sleep = interval, clock, sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self.interval - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()


def download(
    raw_dir: Path,
    targets: list[Target],
    *,
    max_requests: int,
    get: Callable[..., requests.Response] = requests.get,
    throttle: Throttle | None = None,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    command: str = "football_data download",
) -> DownloadReport:
    """Télécharge `targets` (au plus `max_requests`), sous le verrou du dossier brut."""
    throttle = throttle or Throttle()
    report = DownloadReport()
    with CollectLock(raw_dir, command):
        for index, target in enumerate(targets):
            if index >= max_requests:
                report.skipped_cap = targets[index:]
                break
            throttle.wait()
            fetched_at = now()
            started = time.monotonic()
            try:
                response = get(target.url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                report.failed.append((target, f"erreur réseau : {exc.__class__.__name__}"))
                continue
            duration_ms = int((time.monotonic() - started) * 1000)
            data = response.content
            if response.status_code != 200:
                report.failed.append((target, f"HTTP {response.status_code}"))
                continue
            if not looks_like_csv(data):
                report.failed.append((target, "réponse qui n'est pas un CSV football-data"))
                continue
            stored = raw_bytes.write_bytes(
                raw_dir, season_dir(target.season), target.division, SUFFIX, data, fetched_at
            )
            append_entry(
                raw_dir,
                SOURCE,
                {
                    "timestamp": fetched_at.isoformat(),
                    "source": SOURCE,
                    "endpoint": "mmz4281",
                    "params": {"division": target.division, "season": target.season},
                    "url": target.url,
                    "http_status": response.status_code,
                    "errors": None,
                    "results": None,
                    "size_bytes": len(data),
                    "duration_ms": duration_ms,
                    "file": stored.relative_path,
                    "sha256": stored.sha256,
                },
            )
            report.stored.append(target)
    return report
