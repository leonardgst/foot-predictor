"""
Collecte des noms d'équipe distincts vus par API-Football, par championnat,
via l'endpoint léger /teams (1 requête par championnat/saison -- PAS
/fixtures?id=, donc pas besoin d'attendre le plan payant : 5 championnats x
10 saisons = 50 requêtes, largement dans le quota gratuit de 100/jour).
"""
from __future__ import annotations

import time

import requests

from foot_predictor.ingestion.api_football_scraper import BASE_URL, _headers

REQUEST_DELAY_SECONDS = 2  # espacement entre requêtes -- le plan gratuit limite aussi par minute, pas juste par jour
MAX_RETRIES_ON_RATE_LIMIT = 3
RETRY_BACKOFF_SECONDS = 20  # attente en cas de 429, avant nouvel essai


def fetch_teams(league_id: int, season: int) -> list[dict]:
    """Renvoie la liste des équipes ayant participé à ce championnat/saison.
    Retente automatiquement en cas de 429 (rate limit), avec un backoff fixe."""
    for attempt in range(MAX_RETRIES_ON_RATE_LIMIT + 1):
        response = requests.get(
            f"{BASE_URL}/teams",
            headers=_headers(),
            params={"league": league_id, "season": season},
            timeout=30,
        )
        if response.status_code == 429:
            if attempt == MAX_RETRIES_ON_RATE_LIMIT:
                response.raise_for_status()
            wait_time = RETRY_BACKOFF_SECONDS * (attempt + 1)
            print(f"    [429] league={league_id} season={season} -> attente {wait_time}s avant retry")
            time.sleep(wait_time)
            continue
        response.raise_for_status()
        return response.json().get("response", [])
    return []  # inatteignable (raise_for_status lève avant), pour satisfaire les type checkers


def collect_api_football_team_names(
    start_years: range, league_ids_by_code: dict[str, int]
) -> dict[str, set[str]]:
    """Renvoie {league_code: {noms d'équipe distincts}} sur toutes les saisons.

    league_ids_by_code : ex. {"E0": 39, "SP1": 140, ...} (cf. leagues_correspondence.yaml).
    """
    names_by_league: dict[str, set[str]] = {code: set() for code in league_ids_by_code}

    for start_year in start_years:
        for league_code, league_id in league_ids_by_code.items():
            time.sleep(REQUEST_DELAY_SECONDS)
            try:
                teams = fetch_teams(league_id, start_year)
            except Exception as exc:  # noqa: BLE001
                print(f"  [skip] {league_code} {start_year}: {exc}")
                continue

            for entry in teams:
                names_by_league[league_code].add(entry["team"]["name"])

    return names_by_league


if __name__ == "__main__":
    import yaml
    from pathlib import Path

    correspondence = yaml.safe_load(
        (Path(__file__).parent / "leagues_correspondence.yaml").read_text(encoding="utf-8")
    )
    league_ids_by_code = {code: info["api_football_league_id"] for code, info in correspondence.items()}

    result = collect_api_football_team_names(range(2015, 2025), league_ids_by_code)
    for league_code, names in result.items():
        print(f"\n{league_code} : {len(names)} équipes distinctes sur 10 saisons")
        for name in sorted(names):
            print(f"  - {name}")