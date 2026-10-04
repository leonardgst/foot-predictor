"""Sources du live : football-data superposé **en mémoire** à la table des matchs (ADR-0042 ; ADR-0011, règle 3).

Après le gel, `staging` ne reçoit plus rien d'API-FOOTBALL : le calendrier de la saison courante y
est figé (identifiants justes, dates souvent fausses), sans résultats. Le live le complète avec
football-data, sans toucher à `load` ni au référentiel :

| Source | Apporte | Fichier (bruts externes, ADR-0024) |
|---|---|---|
| calendrier API figé (`staging`) | identifiants des matchs et des équipes | — |
| prochains matchs de football-data | dates et heures réelles, cotes avant clôture | `football_data/fixtures/fixtures__*.csv` (toutes les versions) |
| saison courante de football-data | résultats (buts), tirs et tirs cadrés | `football_data/csv/season=S/<div>__*.csv` (dernière version) |

**Appariement** (ADR-0011, règle 3) : par (championnat, saison, équipe à domicile, équipe à
l'extérieur), **sans la date**, clé unique dans une saison de championnat. Les noms d'équipes
passent par `ingestion/mappings/football_data_team_ids.yaml` (nom → identifiant API → équipe de
`staging`). Un nom absent de ce YAML n'est **jamais deviné** : le match concerné est indisponible,
avec la raison.

**Superposition** : un match déjà joué dans `staging` garde les valeurs de l'API ; un match non
joué reçoit, s'il figure dans les résultats, le statut « joué », les buts et les tirs de
football-data (tirs pris tels quels, ADR-0041) ; s'il figure dans les prochains matchs, sa date et
son heure réelles. Heure de football-data : heure de Londres (GMT l'hiver, BST l'été ; vérifié sur
1 749 matchs de 2024-25 sur 1 752), convertie en UTC.

**Fraîcheur par championnat** (ADR-0011, règle 5) : football-data est complet pour un championnat
jusqu'à la veille du **premier match encore sans résultat** (date réelle si connue, sinon date
figée de l'API), ou jusqu'à la veille d'une ligne de résultat inutilisable (équipe inconnue, match
introuvable). Un match du jour J est donc « périmé » dès qu'un match antérieur de son championnat
manque : la prédiction est refusée, jamais faite sur un historique incomplet. Règle prudente : un
match reporté sans nouvelle date bloque son championnat jusqu'à son résultat (compté dans le
rapport ; critère de révision de l'ADR-0011 : plus d'un match sur cinq indisponible).

Aucune cote ni aucun résultat inventé : une valeur absente ou illisible reste vide.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data.check import decode
from foot_predictor.collect.football_data.download import SUFFIX, season_dir
from foot_predictor.collect.football_data.live import FIXTURES_DIR, FIXTURES_STEM, LIVE_DIVISIONS, version_time
from foot_predictor.inference.availability import Freshness
from foot_predictor.ingestion.football_data_csv import parse_date
from foot_predictor.ingestion.football_data_odds import AVANT_CLOTURE, implied_probability_over, select_odds

UK_TIMEZONE = "Europe/London"
SOURCE_NAME = "football-data (live)"
MAPPING_FILE = "ingestion/mappings/football_data_team_ids.yaml"


def season_of(day: dt.date) -> int:
    """Année de début de saison : août 2026 à juin 2027 → 2026."""
    return day.year if day.month >= 7 else day.year - 1


def kickoff_utc(date: dt.date, time_text: str | None) -> pd.Timestamp | None:
    """Coup d'envoi UTC depuis la date et l'heure de Londres ; None si l'heure manque ou est illisible."""
    if not time_text or not time_text.strip():
        return None
    try:
        local = dt.datetime.combine(date, dt.time.fromisoformat(time_text.strip()))
    except ValueError:
        return None
    stamp = pd.Timestamp(local).tz_localize(UK_TIMEZONE, ambiguous="NaT", nonexistent="NaT")
    return None if pd.isna(stamp) else stamp.tz_convert("UTC")


def integer(value: str | None) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except ValueError:
        return None


@dataclass(frozen=True)
class TeamMaps:
    """Correspondances : division → championnat API, nom football-data → équipe API → équipe de `staging`."""

    division_to_league: dict[str, int]
    fd_to_api: dict[str, int]
    api_to_internal: dict[int, int]

    @classmethod
    def from_yaml(cls, api_to_internal: dict[int, int]) -> TeamMaps:
        from foot_predictor.ingestion.yaml_mappings import division_to_league, football_data_teams

        teams, _, _ = football_data_teams()
        return cls(division_to_league(), teams, dict(api_to_internal))

    def team(self, name: str) -> int | None:
        api = self.fd_to_api.get(name.strip())
        return None if api is None else self.api_to_internal.get(api)


@dataclass(frozen=True)
class SourceFile:
    """Une version d'un fichier de football-data : ses lignes et sa date de téléchargement."""

    rows: list[dict]
    fetched_at: dt.datetime
    name: str


def read_csv_file(path: Path) -> SourceFile:
    rows = list(csv.DictReader(io.StringIO(decode(path.read_bytes()))))
    return SourceFile(rows, version_time(path), path.name)


def fixtures_files(raw_dir: Path) -> list[SourceFile]:
    """Toutes les versions du fichier des prochains matchs, de la plus ancienne à la plus récente."""
    return [read_csv_file(p) for p in raw_bytes.versions(raw_dir, FIXTURES_DIR, FIXTURES_STEM, SUFFIX)]


def season_files(raw_dir: Path, season: int, divisions=LIVE_DIVISIONS) -> dict[str, SourceFile]:
    """Dernière version du CSV de chaque division pour la saison `season` (résultats)."""
    found = {}
    for division in divisions:
        path = raw_bytes.latest(raw_dir, season_dir(season), division, SUFFIX)
        if path is not None:
            found[division] = read_csv_file(path)
    return found


@dataclass
class LiveIssue:
    """Ligne de football-data inutilisable : jamais devinée, toujours comptée."""

    division: str
    date: dt.date | None
    home: str
    away: str
    reason: str


@dataclass
class LiveOverlay:
    """Résultat de la superposition : nouvelle table des matchs (copie), fraîcheur par championnat, rapport."""

    matches: pd.DataFrame
    freshness: dict[int, Freshness]
    blocked: dict[int, list[str]] = field(default_factory=dict)  # match_id -> raisons d'indisponibilité
    odds: pd.DataFrame = field(default_factory=pd.DataFrame)
    issues: list[LiveIssue] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    data_version: str = ""


def _key_index(matches: pd.DataFrame, season: int, leagues: set[int]) -> tuple[dict[tuple, int], set[tuple]]:
    """(clé → position, clés ambiguës). Une clé portée par deux matchs n'est jamais résolue au hasard."""
    scope = matches[(matches["season_year"] == season) & matches["api_league_id"].isin(list(leagues))]
    index: dict[tuple, int] = {}
    ambiguous: set[tuple] = set()
    for position, row in zip(scope.index, scope.itertuples(), strict=True):
        key = (int(row.api_league_id), int(row.home_team_id), int(row.away_team_id))
        if key in index:
            ambiguous.add(key)
        index[key] = position
    for key in ambiguous:
        del index[key]
    return index, ambiguous


def _unknown_team_reason(name: str) -> str:
    return f"équipe « {name} » de football-data absente des YAML de rapprochement ({MAPPING_FILE})"


def overlay(
    matches: pd.DataFrame,
    maps: TeamMaps,
    season: int,
    fixtures: list[SourceFile],
    results: dict[str, SourceFile],
    today: dt.date,
) -> LiveOverlay:
    """Superpose football-data à `matches` (non modifiée) pour la saison `season`, au jour `today`."""
    table = matches.copy()
    for column in ("home_shots_fd", "home_sot_fd", "away_shots_fd", "away_sot_fd", "home_goals_90", "away_goals_90"):
        if column in table.columns:
            table[column] = pd.to_numeric(table[column], errors="coerce").astype("Int64")
    leagues = {maps.division_to_league[d] for d in LIVE_DIVISIONS if d in maps.division_to_league}
    index, ambiguous = _key_index(table, season, leagues)
    issues: list[LiveIssue] = []
    caps: dict[int, dt.date] = {}  # championnat -> dernier jour complet imposé par une ligne inutilisable
    blocked: dict[int, list[str]] = defaultdict(list)
    counts = defaultdict(int)

    def locate(division: str, row: dict, date: dt.date | None, *, is_result: bool) -> int | None:
        league = maps.division_to_league.get(division)
        home_name, away_name = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip()
        home, away = maps.team(home_name), maps.team(away_name)
        reason = None
        if home is None or away is None:
            unknown = [n for n, t in ((home_name, home), (away_name, away)) if t is None]
            reason = " ; ".join(_unknown_team_reason(n) for n in unknown)
            _block_known_side(table, index, league, home, away, reason, blocked)
        elif (league, home, away) in ambiguous:
            reason = "appariement ambigu : plusieurs matchs du calendrier API ont cette affiche dans la saison"
        elif (league, home, away) not in index:
            reason = "match introuvable dans le calendrier API figé (championnat, saison, domicile, extérieur)"
        if reason is None:
            return index[(league, home, away)]
        issues.append(LiveIssue(division, date, home_name, away_name, reason))
        counts["lignes_inutilisables"] += 1
        if is_result and date is not None:  # un résultat manquant rend l'historique du championnat incomplet
            caps[league] = min(caps.get(league, date), date - dt.timedelta(days=1))
        return None

    # 1. Prochains matchs : dates réelles et cotes ; la version la plus récente qui cite un match fait foi.
    odds_rows: dict[int, dict] = {}
    for source in fixtures:
        for row in source.rows:
            division, date = (row.get("Div") or "").strip(), parse_date(row.get("Date") or "")
            if division not in maps.division_to_league or date is None or season_of(date) != season:
                continue
            position = locate(division, row, date, is_result=False)
            if position is None or table.at[position, "status"] == "played":
                continue
            kickoff = kickoff_utc(date, row.get("Time"))
            table.at[position, "match_date"] = kickoff if kickoff is not None else pd.Timestamp(date, tz="UTC")
            table.at[position, "match_day"] = date
            counts["dates_reelles"] += 1
            odds = select_odds(row, AVANT_CLOTURE)
            if odds is not None:
                odds_rows[int(table.at[position, "match_id"])] = {
                    "match_id": int(table.at[position, "match_id"]), "version": AVANT_CLOTURE,
                    "p_over": implied_probability_over(odds.over, odds.under), "odds_column": odds.column,
                }  # fmt: skip

    # 2. Résultats de la saison : buts et tirs pour les matchs que staging ne connaît pas encore joués.
    overlaid = set()
    for division, source in sorted(results.items()):
        for row in source.rows:
            date = parse_date(row.get("Date") or "")
            home_goals, away_goals = integer(row.get("FTHG")), integer(row.get("FTAG"))
            if date is None or home_goals is None or away_goals is None:
                continue  # ligne sans résultat (match à venir dans un fichier en cours de saison)
            position = locate(division, row, date, is_result=True)
            if position is None or table.at[position, "status"] == "played":
                continue
            kickoff = kickoff_utc(date, row.get("Time"))
            table.at[position, "match_date"] = kickoff if kickoff is not None else pd.Timestamp(date, tz="UTC")
            table.at[position, "match_day"] = date
            table.at[position, "status"] = "played"
            table.at[position, "home_goals_90"], table.at[position, "away_goals_90"] = home_goals, away_goals
            for column, value in (("home_shots_fd", "HS"), ("away_shots_fd", "AS"), ("home_sot_fd", "HST"),
                                  ("away_sot_fd", "AST")):  # fmt: skip
                table.at[position, column] = integer(row.get(value))
            odds_rows.pop(int(table.at[position, "match_id"]), None)  # joué : plus de référence avant match
            overlaid.add(position)
    counts["resultats_superposes"] = len(overlaid)

    table["match_date"] = pd.to_datetime(table["match_date"], utc=True)
    table = table.sort_values(["match_date", "match_id"], kind="mergesort").reset_index(drop=True)
    freshness = league_freshness(table, season, leagues, results, maps, caps, today)
    odds_frame = pd.DataFrame(list(odds_rows.values()), columns=["match_id", "version", "p_over", "odds_column"])
    return LiveOverlay(table, freshness, dict(blocked), odds_frame, issues, dict(counts),
                       data_version(fixtures, results))  # fmt: skip


def _block_known_side(table, index, league, home, away, reason, blocked) -> None:
    """Nom inconnu d'un côté : les matchs du côté connu contre une équipe sans nom football-data sont bloqués.

    On ne devine pas **quel** match la ligne désigne : tous les candidats sont indisponibles, avec la raison.
    """
    if league is None or (home is None and away is None):
        return
    for (lg, h, a), position in index.items():
        if lg != league or table.at[position, "status"] == "played":
            continue
        if (home is not None and h == home and away is None) or (away is not None and a == away and home is None):
            blocked[int(table.at[position, "match_id"])].append(reason)


def league_freshness(
    table: pd.DataFrame,
    season: int,
    leagues: set[int],
    results: dict[str, SourceFile],
    maps: TeamMaps,
    caps: dict[int, dt.date],
    today: dt.date,
) -> dict[int, Freshness]:
    """Par championnat : complet jusqu'à la veille du premier match sans résultat (ou d'une ligne inutilisable)."""
    league_to_division = {v: k for k, v in maps.division_to_league.items()}
    freshness = {}
    for league in sorted(leagues):
        scope = table[(table["api_league_id"] == league) & (table["season_year"] == season)]
        pending = scope[(scope["status"] != "played") & ~scope["excluded"].fillna(False).astype(bool)]
        pending = pending[pending["status"] != "cancelled"]
        complete = min(pending["match_day"]) - dt.timedelta(days=1) if len(pending) else today
        if league in caps:
            complete = min(complete, caps[league])
        source = results.get(league_to_division.get(league, ""))
        freshness[league] = Freshness(SOURCE_NAME, complete, source.fetched_at if source else None)
    return freshness


def data_version(fixtures: list[SourceFile], results: dict[str, SourceFile]) -> str:
    """Version des fichiers lus : elle change dès qu'une nouvelle version est téléchargée (clé des caches)."""
    names = [f.name for f in fixtures] + [results[d].name for d in sorted(results)]
    return "fd-" + hashlib.sha256("|".join(names).encode()).hexdigest()[:10] if names else "fd-aucun"


def with_overlay(context, live: LiveOverlay):
    """Nouveau contexte d'inférence avec la table superposée : version combinée, caches des lignes vidés.

    La version des données devient `load_run-<n>+fd-<empreinte>` : une nouvelle version d'un fichier
    de football-data change la clé du cache des lignes (jamais une ligne périmée servie).
    """
    import dataclasses

    odds = live.odds if context.odds is None else pd.concat([context.odds, live.odds], ignore_index=True)
    return dataclasses.replace(
        context,
        matches=live.matches,
        data_version=f"{context.data_version}+{live.data_version}",
        league_freshness=live.freshness,
        live_blocked=live.blocked,
        odds=odds,
        _rows=None,
    )


def load_overlay(matches: pd.DataFrame, raw_dir: Path, maps: TeamMaps, today: dt.date) -> LiveOverlay:
    """Lit les fichiers du dossier des bruts externes et superpose la saison de `today`."""
    season = season_of(today)
    return overlay(matches, maps, season, fixtures_files(raw_dir), season_files(raw_dir, season), today)
