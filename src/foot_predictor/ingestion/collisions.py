"""Collisions d'identifiants de joueurs : détection partagée par le chargeur et le contrôle (ADR-0020).

Une collision est un identifiant API qui désigne deux personnes (ADR-0008,
règle 3). Ce module reprend **exactement** la règle de `quality/raw_check.py`
(partie 1), sans modifier ce dernier (règles du gel) : `raw_check` l'appellera
après le gel (partie 2, phase B). Un test vérifie que les deux donnent les
mêmes collisions.

Trois types :

- **même match** : l'identifiant chez les deux équipes (`TWO_TEAMS`), ou avec
  deux numéros de maillot dans la même équipe (`SAME_TEAM`) ;
- **même jour** : l'identifiant chez deux équipes le même jour (UTC) ;
- **deux naissances** : deux dates de naissance qui ne sont pas une simple
  correction d'une saison à l'autre.

Faux positifs écartés : l'identifiant 0 (joueur inconnu de l'API), les
statistiques rattachées à l'équipe adverse dans tout un match (au moins
`SWAP_MIN_PLAYERS` joueurs), la même entrée répétée.

Traitement au chargement (ADR-0020, option 2b) : une entrée en collision est
chargée comme joueur inconnu, sauf « deux numéros dans la même équipe » quand la
composition porte un seul numéro, que l'on retrouve dans une seule entrée de
statistiques : cette entrée est gardée, les autres sont exclues.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

UNKNOWN_PLAYER_ID = 0
SWAP_MIN_PLAYERS = 5
TWO_TEAMS, SAME_TEAM = "two_teams", "same_team"
SWAPPED_STATS, REPEATED_ENTRY = "swapped_stats", "repeated_entry"
LINEUP, STATS = "L", "S"

# Une présence : (source, équipe, numéro de maillot).
Place = tuple[str, int | None, object]


@dataclass
class MatchPlayers:
    """Classement des joueurs d'un match (règle « même match » et faux positifs)."""

    places: dict[int, list[Place]] = field(default_factory=dict)
    team: dict[int, int] = field(default_factory=dict)  # joueur -> équipe retenue (présence normale)
    collisions: dict[int, str] = field(default_factory=dict)  # joueur -> TWO_TEAMS ou SAME_TEAM
    false_positives: dict[int, str] = field(default_factory=dict)  # joueur -> cause
    unknown_entries: int = 0  # entrées à l'identifiant 0

    def resolved_number(self, player: int) -> object | None:
        """ADR-0020, option 2b : numéro à garder pour une collision SAME_TEAM résolue, sinon None.

        Résolue si la composition porte l'identifiant avec un seul numéro (non nul)
        et qu'une seule entrée distincte de statistiques a ce numéro, les autres
        entrées de statistiques ayant un autre numéro.
        """
        if self.collisions.get(player) != SAME_TEAM:
            return None
        found = self.places[player]
        lineup = {(team, number) for source, team, number in found if source == LINEUP}
        stats = [(team, number) for source, team, number in found if source == STATS]
        if len(lineup) != 1:
            return None
        ((team, number),) = lineup
        if number is None:
            return None
        matching = {entry for entry in stats if entry == (team, number)}
        if len(matching) == 1 and any(entry != (team, number) for entry in stats):
            return number
        return None


def _add(places: dict[int, list[Place]], result: MatchPlayers, player_id: object, place: Place) -> None:
    if player_id is None:
        return
    if player_id == UNKNOWN_PLAYER_ID:
        result.unknown_entries += 1
        return
    places.setdefault(int(player_id), []).append(place)


def classify_match(lineups: list[dict], teams_stats: list[dict]) -> MatchPlayers:
    """Règle « même match » de `raw_check._record_appearances`, sur un détail de match.

    Sources : compositions (titulaires et remplaçants) puis statistiques joueurs,
    chacune rattachée à son équipe et à un numéro. Les événements sont écartés
    (un but contre son camp y est rattaché à l'équipe adverse).
    """
    result = MatchPlayers()
    places = result.places
    for lineup in lineups:
        team = (lineup.get("team") or {}).get("id")
        for entry in [*(lineup.get("startXI") or []), *(lineup.get("substitutes") or [])]:
            player = (entry or {}).get("player") or {}
            _add(places, result, player.get("id"), (LINEUP, team, player.get("number")))
    for block in teams_stats:
        team = (block.get("team") or {}).get("id")
        for entry in block.get("players") or []:
            entry = entry or {}
            games = (((entry.get("statistics") or [{}])[0]) or {}).get("games") or {}
            _add(places, result, (entry.get("player") or {}).get("id"), (STATS, team, games.get("number")))

    mismatched: list[int] = []
    for player_id, found in places.items():
        first = found[0]
        if len(found) == 1 or (len(found) == 2 and found[1][0] != first[0] and found[1][1] == first[1]):
            if first[1] is not None:
                result.team[player_id] = first[1]
            continue
        lineup = {(team, number) for source, team, number in found if source == LINEUP}
        stats = {(team, number) for source, team, number in found if source == STATS}
        lineup_teams, stats_teams = {team for team, _ in lineup}, {team for team, _ in stats}
        if len(lineup) > 1 or len(stats) > 1:
            result.collisions[player_id] = TWO_TEAMS if len(lineup_teams | stats_teams) > 1 else SAME_TEAM
        elif lineup_teams and stats_teams and lineup_teams != stats_teams:
            mismatched.append(player_id)
        else:
            result.false_positives[player_id] = REPEATED_ENTRY
            team = next(iter(lineup_teams or stats_teams))
            if team is not None:
                result.team[player_id] = team

    swapped = len(mismatched) >= SWAP_MIN_PLAYERS
    for player_id in mismatched:
        if swapped:
            result.false_positives[player_id] = SWAPPED_STATS
            team = next(team for source, team, _ in places[player_id] if source == LINEUP)  # la composition fait foi
            if team is not None:
                result.team[player_id] = team
        else:
            result.collisions[player_id] = TWO_TEAMS
    return result


def same_day_collisions(players, days, teams, fixtures) -> set[tuple[int, int]]:
    """(joueur, match) des présences d'un joueur vu chez deux équipes le même jour.

    Les quatre arguments sont des tableaux de même longueur : une présence
    normale (hors collision « même match ») par joueur et par match.
    """
    players, days, teams, fixtures = (np.asarray(a, dtype=np.int64) for a in (players, days, teams, fixtures))
    if not len(players):
        return set()
    order = np.lexsort((teams, days, players))
    player, day, team, fixture = players[order], days[order], teams[order], fixtures[order]
    new_key = np.ones(len(order), dtype=bool)
    new_key[1:] = (player[1:] != player[:-1]) | (day[1:] != day[:-1])
    group = np.cumsum(new_key) - 1
    other_team = np.zeros(len(order), dtype=bool)
    other_team[1:] = (team[1:] != team[:-1]) & ~new_key[1:]
    flagged = np.isin(group, np.unique(group[other_team]))
    return set(zip(player[flagged].tolist(), fixture[flagged].tolist(), strict=True))


BIRTH, CORRECTION = "birth", "correction"


def classify_births(seasons_by_birth: dict[str, set[int]]) -> str | None:
    """Plusieurs dates de naissance : collision (`BIRTH`) ou correction de l'API (`CORRECTION`) ?

    Deux dates qui se succèdent dans le temps (la première dans des saisons toutes
    antérieures à celles de la seconde) : correction. Sinon (dates qui alternent,
    même saison, plus de deux dates) : collision. Une seule date : None.
    """
    if len(seasons_by_birth) < 2:
        return None
    if len(seasons_by_birth) > 2:
        return BIRTH
    first, second = sorted(seasons_by_birth.values(), key=lambda seasons: (min(seasons), max(seasons)))
    return CORRECTION if max(first) < min(second) else BIRTH


def retained_birth(seasons_by_birth: dict[str, set[int]]) -> str | None:
    """Date de naissance retenue (ADR-0016, ADR-0020) : la seule, la plus récente
    en cas de correction, aucune en cas de collision."""
    kind = classify_births(seasons_by_birth)
    if not seasons_by_birth or kind == BIRTH:
        return None
    return max(seasons_by_birth, key=lambda birth: (max(seasons_by_birth[birth]), birth))


@dataclass
class BirthIndex:
    """Dates de naissance vues dans les profils : joueur -> date -> saisons."""

    births: dict[int, dict[str, set[int]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(set)))

    def add(self, player: int, birth: str | None, season: int) -> None:
        if birth:
            self.births[player][birth].add(season)

    def collisions(self) -> set[int]:
        return {player for player, by_birth in self.births.items() if classify_births(by_birth) == BIRTH}

    def retained(self, player: int) -> str | None:
        return retained_birth(self.births[player]) if player in self.births else None
