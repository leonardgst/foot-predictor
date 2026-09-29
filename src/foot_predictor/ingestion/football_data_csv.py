"""Lecture des CSV football-data stockés (bruts externes, ADR-0024), en lecture seule.

La dernière version de chaque fichier fait foi. Chaque ligne est gardée entière
(`row`, toutes colonnes) ; les champs utiles à l'appariement sont extraits à part.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data.check import decode
from foot_predictor.collect.football_data.download import SUFFIX, season_dir

# La correspondance division -> compétition API est dans ingestion/mappings/competitions.yaml
# (yaml_mappings.division_to_league).


def parse_date(value: str) -> dt.date | None:
    """« 16/08/2024 » ou « 16/08/24 » (anciens fichiers)."""
    value = value.strip()
    for pattern in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class CsvMatch:
    division: str
    season: int
    line: int  # numéro de ligne dans le fichier (1 = première ligne de données)
    date: dt.date
    home: str
    away: str
    row: dict = field(compare=False, hash=False, repr=False)


def read_matches(raw_dir: Path, division: str, season: int) -> list[CsvMatch]:
    """Matchs de la dernière version du fichier ; lignes vides ou sans date écartées."""
    path = raw_bytes.latest(raw_dir, season_dir(season), division, SUFFIX)
    if path is None:
        return []
    reader = csv.DictReader(io.StringIO(decode(path.read_bytes())))
    matches = []
    for line, row in enumerate(reader, start=1):
        date = parse_date(row.get("Date") or "")
        home, away = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip()
        if date is None or not home or not away:
            continue
        matches.append(CsvMatch(division, season, line, date, home, away, row))
    return matches
