"""Indicateur de huis clos (groupe G0) à partir de `huis_clos.yaml` (ADR-0033).

`behind_closed_doors(league_ids, days)` vaut 1 pour un match joué dans une période
**sûre** de huis clos de son championnat, 0 sinon. Une période `incertain` l'emporte sur
une période sûre qui la recouvre : le match vaut 0 (on ne devine pas). Les périodes à
jauge réduite valent 0 ; elles restent dans le YAML pour la partie 4.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from foot_predictor.features.leagues import LADDERS

PATH = Path(__file__).resolve().parent / "huis_clos.yaml"
STATUSES = ("huis_clos", "jauge_reduite", "incertain")


@dataclass(frozen=True)
class Period:
    league: int
    start: dt.date
    end: dt.date
    status: str
    source: str


def load_periods(path: Path = PATH) -> list[Period]:
    """Lit et valide le YAML : statuts connus, bornes ordonnées, source citée, championnats du MVP."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = data.get("sources") or {}
    periods = []
    for entry in data.get("periods") or []:
        if entry["status"] not in STATUSES:
            raise ValueError(f"Statut inconnu : {entry['status']}")
        if entry["source"] not in sources:
            raise ValueError(f"Source non citée : {entry['source']}")
        start, end = entry["start"], entry["end"]
        if start > end:
            raise ValueError(f"Période inversée : {start} > {end}")
        for league in entry["leagues"]:
            if league not in LADDERS:
                raise ValueError(f"Championnat hors du MVP : {league}")
            periods.append(Period(int(league), start, end, entry["status"], entry["source"]))
    return periods


def behind_closed_doors(league_ids, days, periods: list[Period] | None = None) -> np.ndarray:
    """1 si le match est dans une période sûre de huis clos de son championnat, 0 sinon."""
    periods = load_periods() if periods is None else periods
    leagues = pd.Series(league_ids).astype("int64").to_numpy()
    dates = pd.to_datetime(pd.Series(days)).dt.date.to_numpy()
    sure = np.zeros(len(leagues), dtype=bool)
    doubtful = np.zeros(len(leagues), dtype=bool)
    for period in periods:
        inside = (leagues == period.league) & (dates >= period.start) & (dates <= period.end)
        if period.status == "huis_clos":
            sure |= inside
        elif period.status == "incertain":
            doubtful |= inside
    return (sure & ~doubtful).astype(np.int8)
