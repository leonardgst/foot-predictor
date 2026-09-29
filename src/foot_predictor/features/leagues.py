"""Championnats du MVP et échelles nationales (identifiants de ligue API-FOOTBALL).

Une **échelle** est la pyramide d'un pays : sa D1 et sa D2, liées par la montée et la
descente. L'Elo (G1) a une échelle par pays, sans échelle commune entre pays (ADR-0031).
"""

from __future__ import annotations

# league.id API -> (pays, niveau) ; niveau 1 = D1, 2 = D2.
LADDERS: dict[int, tuple[str, int]] = {
    39: ("England", 1),  # Premier League
    40: ("England", 2),  # Championship
    140: ("Spain", 1),  # La Liga
    141: ("Spain", 2),  # Segunda División
    78: ("Germany", 1),  # Bundesliga
    79: ("Germany", 2),  # 2. Bundesliga
    135: ("Italy", 1),  # Serie A
    136: ("Italy", 2),  # Serie B
    61: ("France", 1),  # Ligue 1
    62: ("France", 2),  # Ligue 2
}

TOP5: frozenset[int] = frozenset({39, 140, 78, 135, 61})
"""Population d'évaluation (ADR-0012, règle 3) : championnats du top 5."""

EUROPEAN_CUPS: frozenset[int] = frozenset({2, 3, 848})
"""Ligue des champions, Ligue Europa, Ligue Europa Conférence."""

# Première saison (année de début) où toutes les coupes jouées par les équipes d'un pays
# sont dans staging : coupes nationales et coupes d'Europe (mesure 4 de la partie 3).
# Avant 2015-16, aucune coupe n'est chargée ; Coppa Italia depuis 2016-17 ; Copa del Rey
# depuis 2018-19. Supercoupes et Coupe du monde des clubs : jamais (limite écrite).
REST_RELIABLE_FROM: dict[str, int] = {
    "England": 2015,
    "Germany": 2015,
    "France": 2015,
    "Italy": 2016,
    "Spain": 2018,
}
