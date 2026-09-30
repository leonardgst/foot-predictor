"""Chargeur football-data : appariement aux matchs API et matchs hors couverture (ADR-0008, règle 2).

S'exécute après `load_api`, sur le même objet de lignes, en continuant la
numérotation interne. Règles :

- football-data ne crée **jamais** de joueur (il n'en a pas) ;
- ses équipes passent par `football_data_team_ids.yaml` : un nom apparié devient
  l'équipe API correspondante, un nom `hors_api` une équipe « hors_api » ;
- dans une compétition-saison **couverte par l'API** (liste de matchs présente),
  chaque ligne est appariée à un match API par (domicile, extérieur, date à
  ± 1 jour). Aucune création : une ligne non appariée est comptée et listée ;
- **hors de la couverture API**, football-data crée le match (origine
  « hors_api »), et la saison si besoin ;
- `*_source_mapping` garde le lien : division, nom d'équipe, ligne de fichier ;
- pour chaque match apparié **ou** créé, une ligne par équipe dans
  `team_match_stats_external` : tirs et tirs cadrés (`HS`, `HST` à domicile, `AS`,
  `AST` à l'extérieur ; ADR-0029). Une valeur absente ou illisible reste vide,
  jamais 0 ; une colonne absente d'un ancien fichier aussi ;
- pour ces mêmes matchs, au plus une ligne par version dans `match_odds` : cotes
  plus/moins 2,5 « avant clôture » et « clôture », colonne choisie par l'ordre de
  priorité de `football_data_odds` (ADR-0036). Sans cote lisible, aucune ligne.

Scellé (ADR-0012) : la cohérence des scores entre les deux sources n'est
contrôlée que pour les matchs antérieurs au 1er juillet 2025. Au-delà, seuls
les taux d'appariement et les décomptes sont produits. Les tirs et les cotes
des matchs scellés sont chargés (permis), jamais comparés ni résumés ici.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect.football_data.download import FIRST_SEASON, LAST_SEASON
from foot_predictor.ingestion import raw_api
from foot_predictor.ingestion.football_data_csv import CsvMatch, read_matches
from foot_predictor.ingestion.football_data_odds import VERSIONS, select_odds
from foot_predictor.ingestion.load_api import ApiLoad
from foot_predictor.seal import SEAL_DATE

SOURCE = "football_data"
SEALED_FROM = SEAL_DATE  # date unique du scellé (ADR-0028)
TOLERANCE = dt.timedelta(days=1)


def integer(value: str | None) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except ValueError:
        return None


@dataclass
class Unmatched:
    division: str
    season: int
    date: dt.date
    home: str
    away: str
    reason: str


@dataclass
class ExternalLoad:
    api: ApiLoad
    external_raw_dir: Path
    division_to_league: dict[str, int]
    teams: dict[str, int]  # nom -> team.id API
    hors_api: set[str]
    seasons: range = range(FIRST_SEASON, LAST_SEASON + 1)

    counts: Counter = field(default_factory=Counter)
    rates: dict[tuple[str, int], tuple[int, int]] = field(default_factory=dict)  # (div, saison) -> (appariés, lignes)
    unmatched: list[Unmatched] = field(default_factory=list)
    score_mismatches: dict[tuple[str, int], int] = field(default_factory=dict)  # avant le scellé seulement
    _shots_id: int = 0
    _shots_team_matches: set[int] = field(default_factory=set)
    _odds_id: int = 0
    _odds_matches: set[int] = field(default_factory=set)

    def run(self) -> None:
        api = self.api
        covered = set(raw_api.league_seasons(api.raw_dir))
        # Matchs API par (compétition, saison, domicile, extérieur) -> [(date, fixture, score 90 min)].
        by_pair: dict[tuple, list] = defaultdict(list)
        for fid, (home, away) in api.match_teams.items():
            info = api.match_info[fid]
            by_pair[(info["league"], info["season"], home, away)].append((info["date"], fid, info["goals_90"]))

        next_team = max(api.team_ids.values(), default=0) + 1
        hors_api_ids: dict[str, int] = {}
        for name in sorted(self.hors_api):
            hors_api_ids[name] = next_team
            api.rows.add("team", (next_team, name, None, None, "hors_api"))
            next_team += 1
        self.counts["teams_hors_api"] = len(hors_api_ids)

        next_competition_mapping = 1
        for division, league in sorted(self.division_to_league.items()):
            if league in api.competition_ids:
                api.rows.add(
                    "competition_source_mapping",
                    (next_competition_mapping, api.competition_ids[league], SOURCE, division),
                )
                next_competition_mapping += 1

        team_mapping_id = 1
        for name in sorted(set(self.teams) | set(hors_api_ids)):
            internal = api.team_ids.get(self.teams[name]) if name in self.teams else hors_api_ids[name]
            if internal is not None:
                api.rows.add("team_source_mapping", (team_mapping_id, internal, SOURCE, name))
                team_mapping_id += 1

        next_season = max(api.season_ids.values(), default=0) + 1
        next_match = max(api.match_ids.values(), default=0) + 1
        match_mapping_id = 1
        for division, league in sorted(self.division_to_league.items()):
            for season in self.seasons:
                rows = read_matches(self.external_raw_dir, division, season)
                if not rows:
                    continue
                if (league, season) in covered:
                    matched = 0
                    for row in rows:
                        fid = self._pair(by_pair, league, season, row)
                        if fid is None:
                            continue
                        matched += 1
                        api.rows.add(
                            "match_source_mapping",
                            (match_mapping_id, api.match_ids[fid], SOURCE, f"{division}:{season}:{row.line}"),
                        )
                        match_mapping_id += 1
                        self._compare_scores(division, season, row, fid)
                        self._emit_shots(api.match_ids[fid], row)
                        self._emit_odds(api.match_ids[fid], row)
                    self.rates[(division, season)] = (matched, len(rows))
                    self.counts["fd_rows_covered"] += len(rows)
                    self.counts["fd_rows_matched"] += matched
                    continue
                # Hors couverture API : football-data crée la saison et les matchs.
                if league not in api.competition_ids:
                    self.counts["fd_rows_without_competition"] += len(rows)
                    continue
                season_id = api.season_ids.get((league, season))
                if season_id is None:
                    first, last = min(r.date for r in rows), max(r.date for r in rows)
                    season_id = next_season
                    api.season_ids[(league, season)] = season_id
                    api.rows.add(
                        "season",
                        (season_id, api.competition_ids[league], f"{season}-{season + 1}", first, last, season),
                    )
                    next_season += 1
                for row in rows:
                    home = self._team(row.home, hors_api_ids)
                    away = self._team(row.away, hors_api_ids)
                    if home is None or away is None:
                        self.counts["fd_rows_unknown_team"] += 1
                        continue
                    self._create_match(next_match, api.competition_ids[league], season_id, home, away, row)
                    api.rows.add(
                        "match_source_mapping",
                        (match_mapping_id, next_match, SOURCE, f"{division}:{season}:{row.line}"),
                    )
                    match_mapping_id += 1
                    self._emit_shots(next_match, row)
                    self._emit_odds(next_match, row)
                    next_match += 1
                    self.counts["matches_hors_api"] += 1

    def _emit_shots(self, match_id: int, row: CsvMatch) -> None:
        """Tirs et tirs cadrés des deux équipes, dans `team_match_stats_external`.

        L'identifiant de `team_match` suit la règle des chargeurs : 2 × match − 1 pour
        l'équipe à domicile, 2 × match pour l'extérieur. Le domicile du CSV est celui du
        match API (l'appariement se fait sur le couple ordonné domicile, extérieur).
        Deux lignes du CSV appariées au même match : seule la première est gardée.
        """
        for is_home, (shots_col, target_col) in ((True, ("HS", "HST")), (False, ("AS", "AST"))):
            team_match_id = 2 * match_id - (1 if is_home else 0)
            if team_match_id in self._shots_team_matches:
                self.counts["fd_shots_duplicate_pairing"] += 1
                continue
            self._shots_team_matches.add(team_match_id)
            shots, on_target = integer(row.row.get(shots_col)), integer(row.row.get(target_col))
            self._shots_id += 1
            self.api.rows.add("team_match_stats_external", (self._shots_id, SOURCE, team_match_id, shots, on_target))
            self.counts["fd_shots_rows"] += 1
            if shots is None or on_target is None:
                self.counts["fd_shots_rows_incomplete"] += 1

    def _emit_odds(self, match_id: int, row: CsvMatch) -> None:
        """Cotes plus/moins 2,5 du match, une ligne par version disponible, dans `match_odds` (ADR-0036).

        Deux lignes du CSV appariées au même match : seule la première est gardée, comme
        pour les tirs. Une version sans cote lisible ne donne aucune ligne (jamais inventée).
        """
        if match_id in self._odds_matches:
            self.counts["fd_odds_duplicate_pairing"] += 1
            return
        self._odds_matches.add(match_id)
        for version in VERSIONS:
            odds = select_odds(row.row, version)
            if odds is None:
                self.counts[f"fd_odds_missing_{version}"] += 1
                continue
            self._odds_id += 1
            self.api.rows.add(
                "match_odds",
                (self._odds_id, match_id, SOURCE, version, odds.over, odds.under, odds.column, odds.n_odds),
            )
            self.counts[f"fd_odds_rows_{version}"] += 1
            self.counts[f"fd_odds_{version}_{odds.column}"] += 1

    def _team(self, name: str, hors_api_ids: dict[str, int]) -> int | None:
        if name in self.teams:
            return self.api.team_ids.get(self.teams[name])
        return hors_api_ids.get(name)

    def _pair(self, by_pair, league: int, season: int, row: CsvMatch) -> int | None:
        home_api, away_api = self.teams.get(row.home), self.teams.get(row.away)
        if home_api is None or away_api is None:
            self.unmatched.append(
                Unmatched(row.division, season, row.date, row.home, row.away, "équipe sans identifiant API")
            )
            return None
        candidates = [
            (abs(date - row.date), fid)
            for date, fid, _ in by_pair.get((league, season, home_api, away_api), [])
            if date is not None and abs(date - row.date) <= TOLERANCE
        ]
        if not candidates:
            self.unmatched.append(
                Unmatched(row.division, season, row.date, row.home, row.away, "aucun match API à ± 1 jour")
            )
            return None
        return min(candidates)[1]

    def _compare_scores(self, division: str, season: int, row: CsvMatch, fid: int) -> None:
        """Cohérence des scores : seulement avant le scellé (ADR-0012)."""
        if row.date >= SEALED_FROM:
            return
        fd_score = (integer(row.row.get("FTHG")), integer(row.row.get("FTAG")))
        api_score = self.api.match_info[fid]["goals_90"]
        if None in fd_score or None in api_score:
            self.counts["scores_not_comparable"] += 1
            return
        self.counts["scores_compared"] += 1
        if fd_score != api_score:
            self.score_mismatches[(division, season)] = self.score_mismatches.get((division, season), 0) + 1
            self.counts["scores_different"] += 1

    def _create_match(self, match_id: int, competition: int, season: int, home: int, away: int, row: CsvMatch) -> None:
        goals = (integer(row.row.get("FTHG")), integer(row.row.get("FTAG")))
        kickoff = dt.datetime.combine(row.date, dt.time(0, 0), tzinfo=dt.UTC)  # heure locale inconnue ou non convertie
        played = None not in goals
        self.api.rows.add(
            "match",
            (match_id, competition, season, kickoff, home, away, goals[0], goals[1], "played" if played else "scheduled",
             None, None, None, None, goals[0], goals[1], None, None, False, None, "hors_api"),
        )  # fmt: skip
        for is_home, team in ((True, home), (False, away)):
            goals_for, goals_against = (goals[0], goals[1]) if is_home else (goals[1], goals[0])
            self.api.rows.add(
                "team_match",
                (2 * match_id - (1 if is_home else 0), match_id, team, is_home, goals_for, goals_against,
                 None, None, None, None, None, None),
            )  # fmt: skip
