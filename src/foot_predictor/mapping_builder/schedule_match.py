"""Appariement des équipes football-data aux équipes API-FOOTBALL par le calendrier.

Pourquoi le calendrier plutôt que les noms : « Man United » et « Manchester
United », ou deux clubs homonymes de pays différents, trompent un rapprochement
de noms. Dans un même championnat-saison, deux équipes qui jouent les mêmes
jours, à domicile et à l'extérieur, contre les mêmes adversaires, sont la même
équipe. Aucun nom n'est comparé ici.

Méthode, pour un championnat-saison :

0. **Amorce.** Empreinte de calendrier de chaque équipe : l'ensemble des
   (date, domicile ou extérieur). Une équipe est amorcée si son empreinte
   recouvre nettement celle d'une seule équipe API (Jaccard).
1. **Votes.** Pour chaque match football-data (date, domicile, extérieur), on
   regarde les matchs API du même jour (tolérance : 0 jour, puis 1 jour). Chacun
   donne une voix « domicile football-data -> domicile API » et une voix
   « extérieur -> extérieur ».
2. **Ancrage.** Une équipe est appariée si son meilleur candidat recueille au
   moins la moitié de ses matchs et au moins deux fois plus de voix que le
   second, et si aucune autre équipe ne vise le même identifiant.
3. **Propagation.** Les votes sont recalculés en ne gardant que les matchs API
   compatibles avec les équipes déjà appariées (l'adversaire doit correspondre).
   On recommence tant que de nouvelles équipes s'apparient.
4. **Validation.** Une correspondance n'est retenue que si au moins
   `MIN_CONFIRMED` de ses matchs football-data ont un match API le même jour
   (± 1), avec **les deux** équipes appariées de façon cohérente.

Tout le reste est rendu « non apparié », avec la raison : jamais deviné.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass

MIN_SHARE = 0.5  # part des matchs de l'équipe que doit recueillir le meilleur candidat
MIN_RATIO = 2.0  # voix du meilleur / voix du second
MIN_CONFIRMED = 0.9  # part des matchs confirmés par un match API cohérent


@dataclass(frozen=True)
class Fixture:
    """Un match réduit à son calendrier : date, domicile, extérieur (noms ou identifiants)."""

    date: dt.date
    home: object
    away: object


@dataclass
class ScheduleMatch:
    mapping: dict[str, int]  # nom football-data -> identifiant API
    unmatched: dict[str, str]  # nom football-data -> raison
    confirmed: dict[str, float]  # part des matchs confirmés, pour les appariés


def _by_date(fixtures: list[Fixture]) -> dict[dt.date, list[Fixture]]:
    index: dict[dt.date, list[Fixture]] = defaultdict(list)
    for fixture in fixtures:
        index[fixture.date].append(fixture)
    return index


def _near(index: dict[dt.date, list[Fixture]], date: dt.date, tolerance: int) -> list[Fixture]:
    return [f for delta in range(-tolerance, tolerance + 1) for f in index.get(date + dt.timedelta(days=delta), [])]


def _votes(fd: list[Fixture], index, mapping: dict[str, int], tolerance: int) -> dict[str, Counter]:
    claimed = set(mapping.values())
    votes: dict[str, Counter] = defaultdict(Counter)
    for match in fd:
        for api in _near(index, match.date, tolerance):
            home_ok = mapping.get(match.home, api.home) == api.home
            away_ok = mapping.get(match.away, api.away) == api.away
            if not (home_ok and away_ok):
                continue
            if match.home not in mapping and api.home not in claimed:
                votes[match.home][api.home] += 1
            if match.away not in mapping and api.away not in claimed:
                votes[match.away][api.away] += 1
    return votes


def _anchor(votes: dict[str, Counter], played: Counter) -> dict[str, int]:
    chosen: dict[str, int] = {}
    for name, counter in votes.items():
        ranked = counter.most_common(2)
        best, best_votes = ranked[0]
        second_votes = ranked[1][1] if len(ranked) > 1 else 0
        if best_votes >= MIN_SHARE * played[name] and best_votes >= MIN_RATIO * second_votes:
            chosen[name] = best
    # Deux équipes football-data qui visent le même identifiant : aucune n'est retenue.
    targets = Counter(chosen.values())
    return {name: api for name, api in chosen.items() if targets[api] == 1}


def _fingerprints(fixtures: list[Fixture]) -> dict[object, set[tuple[dt.date, str]]]:
    prints: dict[object, set[tuple[dt.date, str]]] = defaultdict(set)
    for fixture in fixtures:
        prints[fixture.home].add((fixture.date, "H"))
        prints[fixture.away].add((fixture.date, "A"))
    return prints


def _seed(fd: list[Fixture], api: list[Fixture]) -> dict[str, int]:
    """Amorce : empreinte de calendrier (dates et côté domicile ou extérieur), comparée par Jaccard.

    Dans un championnat où toutes les équipes jouent le même samedi, les votes du
    premier passage sont trop partagés. L'empreinte, elle, distingue nettement :
    une équipe et elle-même se recouvrent presque entièrement, deux équipes
    différentes environ au tiers (même jour, même côté une fois sur deux).
    """
    fd_prints, api_prints = _fingerprints(fd), _fingerprints(api)
    chosen: dict[str, int] = {}
    for name, mine in fd_prints.items():
        scores = sorted(
            ((len(mine & theirs) / len(mine | theirs), team) for team, theirs in api_prints.items()),
            key=lambda pair: (-pair[0], str(pair[1])),
        )
        if not scores:
            continue
        (best, team), second = scores[0], (scores[1][0] if len(scores) > 1 else 0.0)
        if best >= SEED_MIN_JACCARD and best >= SEED_MIN_RATIO * second:
            chosen[name] = team
    targets = Counter(chosen.values())
    return {name: team for name, team in chosen.items() if targets[team] == 1}


SEED_MIN_JACCARD = 0.6
SEED_MIN_RATIO = 1.5


def match_schedule(fd: list[Fixture], api: list[Fixture]) -> ScheduleMatch:
    """Apparie les équipes d'un championnat-saison (voir la docstring du module)."""
    if fd:
        # Saison en cours : la liste API contient aussi les matchs à venir, absents du
        # fichier football-data. On ne garde que la période couverte par ce fichier.
        first = min(m.date for m in fd) - dt.timedelta(days=1)
        last = max(m.date for m in fd) + dt.timedelta(days=1)
        api = [f for f in api if first <= f.date <= last]
    index = _by_date(api)
    played: Counter = Counter()
    for match in fd:
        played[match.home] += 1
        played[match.away] += 1

    mapping: dict[str, int] = _seed(fd, api)
    for tolerance in (0, 1):
        while True:
            new = _anchor(_votes(fd, index, mapping, tolerance), played)
            if not new:
                break
            mapping.update(new)

    confirmed: dict[str, float] = {}
    ok_count: Counter = Counter()
    for match in fd:
        home, away = mapping.get(match.home), mapping.get(match.away)
        if home is None or away is None:
            continue
        if any(f.home == home and f.away == away for f in _near(index, match.date, 1)):
            ok_count[match.home] += 1
            ok_count[match.away] += 1

    unmatched: dict[str, str] = {}
    final: dict[str, int] = {}
    for name in sorted(played):
        if name not in mapping:
            unmatched[name] = "aucun candidat net (voix insuffisantes ou partagées)"
            continue
        share = ok_count[name] / played[name]
        if share >= MIN_CONFIRMED:
            final[name], confirmed[name] = mapping[name], share
        else:
            unmatched[name] = f"candidat {mapping[name]} confirmé sur {share:.0%} des matchs seulement"
    return ScheduleMatch(final, unmatched, confirmed)
