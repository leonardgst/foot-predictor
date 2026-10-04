"""Collecteur live de football-data : prochains matchs et saison courante (ADR-0042 ; ADR-0011, règle 3).

    python -m foot_predictor.collect.football_data.live fixtures --max-requests 1
    python -m foot_predictor.collect.football_data.live season --season 2026 --max-requests 10   # phase B

Option commune : `--raw-dir` (dossier des bruts externes, `data/raw` par défaut, ADR-0024).

Arborescence (à côté de celle du téléchargeur historique, `download.py`, inchangé) :

    <raw_dir>/football_data/fixtures/fixtures__<horodatage>.csv    prochains matchs (toutes divisions)
    <raw_dir>/football_data/csv/season=2026/E0__<horodatage>.csv   saison courante, nouvelle version à côté
    <raw_dir>/_manifest/football_data.jsonl                        une ligne par fichier stocké

Règles, reprises du téléchargeur historique : fichier stocké **octet pour octet**, jamais
d'écrasement (une nouvelle version s'ajoute à côté), une requête par seconde au plus,
`User-Agent` du projet, plafond `--max-requests` obligatoire, verrou du dossier brut, journal.
Propres au live :

- un fichier dont la dernière version a moins de `--min-age-hours` heures (6 par défaut) n'est pas
  redemandé : football-data ne met ses fichiers à jour que deux fois par semaine environ ;
- **scellé** : `season` refuse toute saison à partir de 2025-26 tant que le test scellé n'est pas
  terminé (`reports/sealed_tests.md`) ; ces fichiers contiennent des résultats sous scellés ;
- domaine `football-data.co.uk` sans `www` : le site redirige désormais `www` vers lui (relevé le
  2026-10-04), ce qui ferait une seconde requête par fichier.

Conditions d'utilisation relues le 2026-10-04 (ADR-0042, citées) : usage réservé aux particuliers,
pour la prédiction de matchs de championnat, sans usage commercial ni produit d'entraînement d'IA.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import requests

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data import SOURCE
from foot_predictor.collect.football_data.download import (
    SUFFIX,
    TIMEOUT_SECONDS,
    USER_AGENT,
    Throttle,
    looks_like_csv,
    season_code,
    season_dir,
)
from foot_predictor.rawstore.lock import CollectLock, LockHeldError
from foot_predictor.rawstore.store import TIMESTAMP_FORMAT, VERSION_SEPARATOR

LIVE_BASE_URL = "https://football-data.co.uk"
FIXTURES_DIR = f"{SOURCE}/fixtures"
FIXTURES_STEM = "fixtures"
LIVE_DIVISIONS = ("E0", "SP1", "D1", "I1", "F1", "E1", "SP2", "D2", "I2", "F2")
"""Top 5 et deuxièmes divisions : les échelles de l'Elo et des glissants (features/leagues.py)."""
MIN_AGE_HOURS = 6.0
SEALED_FIRST_SEASON = 2025  # 2025-26 : saison du test scellé (ADR-0012)
API_MARKERS = ("api_football", "_queue")  # même refus que le téléchargeur historique (ADR-0024)


@dataclass(frozen=True)
class LiveTarget:
    """Un fichier à télécharger : URL, emplacement dans le brut, paramètres du journal."""

    url: str
    relative_dir: str
    stem: str
    endpoint: str
    params: dict = field(hash=False, compare=False)


def fixtures_target() -> LiveTarget:
    return LiveTarget(f"{LIVE_BASE_URL}/{FIXTURES_STEM}{SUFFIX}", FIXTURES_DIR, FIXTURES_STEM, "fixtures", {})


def season_target(division: str, season: int) -> LiveTarget:
    url = f"{LIVE_BASE_URL}/mmz4281/{season_code(season)}/{division}{SUFFIX}"
    return LiveTarget(url, season_dir(season), division, "mmz4281", {"division": division, "season": season})


def looks_like_fixtures(data: bytes) -> bool:
    """Le fichier des prochains matchs : un CSV dont l'en-tête nomme les deux équipes."""
    header = data.lstrip(b"\xef\xbb\xbf").lstrip().split(b"\n", 1)[0]
    return b"HomeTeam" in header and b"AwayTeam" in header


def version_time(path: Path) -> dt.datetime:
    """Horodatage UTC d'une version, lu dans son nom (`<stem>__<AAAAMMJJTHHMMSSffffffZ>.csv`)."""
    stamp = path.name.split(VERSION_SEPARATOR, 1)[1].removesuffix(SUFFIX)
    return dt.datetime.strptime(stamp, TIMESTAMP_FORMAT).replace(tzinfo=dt.UTC)


def is_recent(raw_dir: Path, target: LiveTarget, now: dt.datetime, min_age_hours: float) -> bool:
    """Vrai si la dernière version a moins de `min_age_hours` heures : on ne la redemande pas."""
    last = raw_bytes.latest(raw_dir, target.relative_dir, target.stem, SUFFIX)
    return last is not None and now - version_time(last) < dt.timedelta(hours=min_age_hours)


class SealedSeasonRefused(RuntimeError):
    """Saison sous scellés demandée avant la fin du test scellé."""


def check_season_allowed(season: int, sealed_test_done: Callable[[], bool]) -> None:
    if season >= SEALED_FIRST_SEASON and not sealed_test_done():
        raise SealedSeasonRefused(
            f"Saison {season}-{(season + 1) % 100:02d} : ses CSV contiennent des résultats sous scellés ; "
            "téléchargement refusé tant que le test scellé n'est pas terminé (ADR-0012, phase B)."
        )


def default_sealed_test_done() -> bool:
    from foot_predictor.modeling.sealed import already_evaluated

    return already_evaluated("experiments/scelle_h1.yaml")


@dataclass
class LiveReport:
    stored: list[LiveTarget] = field(default_factory=list)
    recent: list[LiveTarget] = field(default_factory=list)  # dernière version trop récente : non redemandé
    failed: list[tuple[LiveTarget, str]] = field(default_factory=list)
    skipped_cap: list[LiveTarget] = field(default_factory=list)


def fetch(
    raw_dir: Path,
    targets: list[LiveTarget],
    *,
    max_requests: int,
    min_age_hours: float = MIN_AGE_HOURS,
    get: Callable[..., requests.Response] = requests.get,
    throttle: Throttle | None = None,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    command: str = "football_data live",
) -> LiveReport:
    """Télécharge `targets` (au plus `max_requests` requêtes), sous le verrou du dossier brut."""
    from foot_predictor.rawstore.manifest import append_entry

    throttle = throttle or Throttle()
    report = LiveReport()
    sent = 0
    with CollectLock(raw_dir, command):
        for index, target in enumerate(targets):
            if is_recent(raw_dir, target, now(), min_age_hours):
                report.recent.append(target)
                continue
            if sent >= max_requests:
                report.skipped_cap = [t for t in targets[index:] if not is_recent(raw_dir, t, now(), min_age_hours)]
                break
            throttle.wait()
            sent += 1
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
            valid = looks_like_fixtures(data) if target.endpoint == "fixtures" else looks_like_csv(data)
            if not valid:
                report.failed.append((target, "réponse qui n'est pas un CSV football-data"))
                continue
            stored = raw_bytes.write_bytes(raw_dir, target.relative_dir, target.stem, SUFFIX, data, fetched_at)
            append_entry(
                raw_dir,
                SOURCE,
                {
                    "timestamp": fetched_at.isoformat(),
                    "source": SOURCE,
                    "endpoint": target.endpoint,
                    "params": target.params,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.collect.football_data.live")
    parser.add_argument("--raw-dir", type=Path, default=Path("data") / "raw", help="dossier des bruts externes")
    parser.add_argument("--min-age-hours", type=float, default=MIN_AGE_HOURS, help="âge minimal avant de redemander")
    sub = parser.add_subparsers(dest="command", required=True)
    fixtures = sub.add_parser("fixtures", help="fichier des prochains matchs (fixtures.csv)")
    fixtures.add_argument("--max-requests", type=int, required=True, help="plafond de requêtes")
    season = sub.add_parser("season", help="CSV de la saison courante (résultats, tirs, cotes)")
    season.add_argument("--season", type=int, required=True, help="année de début (2026 = 2026-27)")
    season.add_argument("--division", action="append", dest="divisions", help=f"défaut : {' '.join(LIVE_DIVISIONS)}")
    season.add_argument("--max-requests", type=int, required=True, help="plafond de requêtes")
    for command in (fixtures, season):
        command.add_argument("--dry-run", action="store_true", help="affiche le plan ; n'écrit rien, n'envoie rien")
    return parser


def main(argv: list[str] | None = None, sealed_test_done: Callable[[], bool] = default_sealed_test_done) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    if any((args.raw_dir / marker).exists() for marker in API_MARKERS):
        print(f"Refusé : {args.raw_dir} contient le brut API-FOOTBALL (dossier des bruts externes attendu, "
              "ADR-0024).", file=sys.stderr)  # fmt: skip
        return 2
    if args.command == "fixtures":
        targets = [fixtures_target()]
    else:
        try:
            check_season_allowed(args.season, sealed_test_done)
        except SealedSeasonRefused as exc:
            print(f"Refusé : {exc}", file=sys.stderr)
            return 2
        targets = [season_target(d, args.season) for d in (args.divisions or LIVE_DIVISIONS)]
    if args.dry_run:
        now = dt.datetime.now(dt.UTC)
        for target in targets:
            state = (
                "récent, non redemandé" if is_recent(args.raw_dir, target, now, args.min_age_hours) else "à demander"
            )
            print(f"  {target.url} ({state})")
        print(f"Plafond : {args.max_requests} requête(s).")
        return 0
    try:
        report = fetch(args.raw_dir, targets, max_requests=args.max_requests, min_age_hours=args.min_age_hours,
                       command=f"football_data live {args.command}")  # fmt: skip
    except LockHeldError as exc:
        print(f"Refusé : {exc}", file=sys.stderr)
        return 3
    print(f"Stockés : {len(report.stored)} ; récents (non redemandés) : {len(report.recent)} ; "
          f"en échec : {len(report.failed)} ; au-delà du plafond : {len(report.skipped_cap)}")  # fmt: skip
    for target, reason in report.failed:
        print(f"  échec : {target.url} ({reason})")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
