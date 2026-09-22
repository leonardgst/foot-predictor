"""
Collecte des noms d'équipe distincts vus dans les réponses Understat, par
championnat, sur une plage de saisons. Réutilise fetch_league_matches déjà
en place dans understat_scraper.py -- aucune requête supplémentaire, les
noms d'équipe sont déjà dans la réponse de league.get_match_data().
"""
from __future__ import annotations

from understatapi import UnderstatClient

from foot_predictor.ingestion.understat_scraper import fetch_league_matches

LEAGUE_CODES = ["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1"]


def collect_understat_team_names(
    client: UnderstatClient, start_years: range, league_codes: list[str] | None = None
) -> dict[str, set[str]]:
    """Renvoie {league_code: {noms d'équipe distincts}} sur toutes les saisons.

    Understat attend une saison sous forme d'année de départ en string, ex. "2024".
    """
    league_codes = league_codes or LEAGUE_CODES
    names_by_league: dict[str, set[str]] = {code: set() for code in league_codes}

    for start_year in start_years:
        season = str(start_year)
        for league_code in league_codes:
            try:
                matches = fetch_league_matches(client, league_code, season)
            except Exception as exc:  # noqa: BLE001
                print(f"  [skip] {league_code} {season}: {exc}")
                continue

            for match_entry in matches:
                names_by_league[league_code].add(match_entry["h"]["title"])
                names_by_league[league_code].add(match_entry["a"]["title"])

    return names_by_league


if __name__ == "__main__":
    with UnderstatClient() as client:
        result = collect_understat_team_names(client, range(2015, 2025))
    for league_code, names in result.items():
        print(f"\n{league_code} : {len(names)} équipes distinctes sur 10 saisons")
        for name in sorted(names):
            print(f"  - {name}")