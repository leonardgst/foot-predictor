"""Appariement des équipes par le calendrier (sans comparer les noms)."""

import datetime as dt
from itertools import permutations

from foot_predictor.mapping_builder.schedule_match import Fixture, match_schedule

START = dt.date(2023, 8, 5)
NAMES = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]
IDS = [101, 102, 103, 104, 105, 106]


def season(teams, start=START):
    """Aller-retour complet, une journée par semaine (tous les matchs le même jour)."""
    rounds = []
    pairs = list(permutations(range(len(teams)), 2))
    # Journées : chaque équipe joue une fois par journée (algorithme du cercle, aller puis retour).
    n = len(teams)
    order = list(range(n))
    for leg in range(2):
        rotation = order[:]
        for day in range(n - 1):
            matches = []
            for i in range(n // 2):
                a, b = rotation[i], rotation[n - 1 - i]
                matches.append((a, b) if (day + i + leg) % 2 == 0 else (b, a))
            rounds.append(matches)
            rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    assert len({m for r in rounds for m in r}) == len(pairs)
    return [
        Fixture(start + dt.timedelta(weeks=week), teams[h], teams[a])
        for week, matches in enumerate(rounds)
        for h, a in matches
    ]


def test_all_teams_matched_when_every_match_is_on_the_same_day():
    fd, api = season(NAMES), season(IDS)
    result = match_schedule(fd, api)
    assert result.mapping == dict(zip(NAMES, IDS, strict=True))
    assert not result.unmatched


def test_tolerates_one_day_shift_and_a_missing_match():
    fd, api = season(NAMES), season(IDS)
    fd[0] = Fixture(fd[0].date + dt.timedelta(days=1), fd[0].home, fd[0].away)  # date locale / UTC
    api = api[1:]  # un match absent de l'API
    result = match_schedule(fd, api)
    assert result.mapping == dict(zip(NAMES, IDS, strict=True))


def test_future_api_fixtures_are_ignored():
    """Saison en cours : la liste API contient des matchs pas encore dans le CSV."""
    fd, api = season(NAMES), season(IDS)
    result = match_schedule(fd[:9], api)  # 3 journées jouées sur 10
    assert result.mapping == dict(zip(NAMES, IDS, strict=True))


def test_ambiguous_team_is_left_unmatched():
    """Une équipe football-data qui ne correspond à aucune équipe API n'est pas devinée."""
    fd, api = season(NAMES), season(IDS)
    # Foxtrot est remplacée dans l'API par une autre équipe dont le calendrier est différent.
    api = [f for f in api if 106 not in (f.home, f.away)]
    result = match_schedule(fd, api)
    assert "Foxtrot" in result.unmatched
    assert 106 not in result.mapping.values()


def test_two_names_never_share_an_identifier():
    fd, api = season(NAMES), season(IDS)
    result = match_schedule(fd, api)
    assert len(set(result.mapping.values())) == len(result.mapping)
