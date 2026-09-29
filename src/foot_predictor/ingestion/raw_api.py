"""Lecture du brut API-FOOTBALL, en lecture seule (ADR-0003, ADR-0008).

Utilisé par le chargeur (`ingestion/load_api.py`) et les brouillons de YAML
(`mapping_builder/`). N'écrit jamais rien : aucune fonction de ce module
n'ouvre un fichier en écriture ni ne crée de dossier.

Règles de lecture :

- pour chaque fichier, **la version la plus récente** fait foi (une recollecte
  s'ajoute à côté, avec un horodatage plus récent) ;
- pour les détails de match, un match présent dans plusieurs lots est pris dans
  le lot le plus récent ;
- `api_football/daily/` (journal T-60 : compositions d'avant-match) n'est
  jamais lu : ce ne sont pas des détails de match (E-025).
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from foot_predictor.rawstore.store import SUFFIX, VERSION_SEPARATOR, read_envelope

SOURCE = "api_football"
_LEAGUE_DIR = re.compile(r"^league=(\d+)$")
_SEASON_STEM = re.compile(r"^season=(\d+)$")


def _latest_by_stem(directory: Path) -> dict[str, Path]:
    """{stem: dernière version} pour les fichiers d'un dossier (tri des noms = ordre chronologique)."""
    latest: dict[str, Path] = {}
    if not directory.is_dir():
        return latest
    for path in sorted(directory.glob(f"*{SUFFIX}")):
        latest[path.name.split(VERSION_SEPARATOR)[0]] = path  # le dernier vu est le plus récent
    return latest


def body(path: Path) -> dict:
    envelope = read_envelope(path)
    return envelope.get("body") or {}


def response(path: Path) -> list[dict]:
    return [item for item in body(path).get("response") or [] if isinstance(item, dict)]


def league_seasons(raw_dir: Path) -> list[tuple[int, int]]:
    """(compétition, saison) qui ont une liste de matchs dans le brut, triées."""
    found = []
    root = Path(raw_dir) / SOURCE / "fixtures_list"
    if not root.is_dir():
        return found
    for league_dir in root.iterdir():
        match = _LEAGUE_DIR.match(league_dir.name)
        if not match:
            continue
        for stem in _latest_by_stem(league_dir):
            season = _SEASON_STEM.match(stem)
            if season:
                found.append((int(match.group(1)), int(season.group(1))))
    return sorted(found)


def fixtures_list(raw_dir: Path, league: int, season: int) -> list[dict]:
    """Dernière liste de matchs d'une compétition-saison (vide si absente)."""
    path = _latest_by_stem(Path(raw_dir) / SOURCE / "fixtures_list" / f"league={league}").get(f"season={season}")
    return response(path) if path else []


def fixture_details(raw_dir: Path, league: int, season: int) -> Iterator[dict]:
    """Détails des matchs d'une compétition-saison, un seul par match (lot le plus récent)."""
    directory = Path(raw_dir) / SOURCE / "fixtures_detail" / f"league={league}" / f"season={season}"
    if not directory.is_dir():
        return
    seen: set[int] = set()
    # Plus récent d'abord : l'horodatage est après le séparateur, le tri se fait sur lui.
    paths = sorted(directory.glob(f"*{SUFFIX}"), key=lambda p: p.name.split(VERSION_SEPARATOR)[-1], reverse=True)
    for path in paths:
        for item in response(path):
            fid = fixture_id(item)
            if fid is None or fid in seen:
                continue
            seen.add(fid)
            yield item


def fixture_id(item: dict) -> int | None:
    value = (item.get("fixture") or {}).get("id")
    return int(value) if value is not None else None


def kickoff(item: dict) -> dt.datetime | None:
    """Coup d'envoi en UTC (`fixture.date`, ISO 8601 avec décalage)."""
    value = (item.get("fixture") or {}).get("date")
    if not value:
        return None
    return dt.datetime.fromisoformat(value).astimezone(dt.UTC)


@dataclass(frozen=True)
class ListedFixture:
    """Un match d'une liste, réduit à ce qui sert à l'appariement (aucun score)."""

    fixture_id: int
    league: int
    season: int
    kickoff: dt.datetime | None
    home_id: int
    away_id: int
    home_name: str
    away_name: str
    status: str | None


def listed_fixtures(raw_dir: Path, league: int, season: int) -> list[ListedFixture]:
    fixtures = []
    for item in fixtures_list(raw_dir, league, season):
        teams = item.get("teams") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        fid = fixture_id(item)
        if fid is None or home.get("id") is None or away.get("id") is None:
            continue
        fixtures.append(
            ListedFixture(
                fixture_id=fid,
                league=league,
                season=season,
                kickoff=kickoff(item),
                home_id=int(home["id"]),
                away_id=int(away["id"]),
                home_name=home.get("name") or "",
                away_name=away.get("name") or "",
                status=((item.get("fixture") or {}).get("status") or {}).get("short"),
            )
        )
    return fixtures
