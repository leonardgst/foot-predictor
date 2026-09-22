"""
Collecte des noms d'équipe distincts vus dans les CSV football-data.co.uk,
par division, sur une plage de saisons -- ne touche PAS la base, juste pour
construire les mappings d'équipes (pas besoin d'attendre le plan payant
API-Football, c'est gratuit et instantané).

Réutilise les fonctions déjà en place dans football_data_scraper.py
(fetch_division, parse_csv_content) pour ne pas dupliquer la logique de
parsing CSV.
"""
from __future__ import annotations

from foot_predictor.ingestion.football_data_scraper import DIVISIONS, fetch_division, parse_csv_content


def collect_football_data_team_names(
    start_years: range, divisions: list[str] | None = None
) -> dict[str, set[str]]:
    """Renvoie {div: {noms d'équipe distincts}} sur toutes les saisons demandées.

    start_years : ex. range(2015, 2025) -> saisons "2015-2016" ... "2024-2025".
    """
    divisions = divisions or DIVISIONS
    names_by_division: dict[str, set[str]] = {div: set() for div in divisions}

    for start_year in start_years:
        season_label = f"{start_year}-{start_year + 1}"
        for div in divisions:
            try:
                csv_text = fetch_division(div, season_label)
            except Exception as exc:  # noqa: BLE001
                # Saison pas encore jouée / division inexistante cette année -> on
                # continue, ce n'est pas bloquant pour la collecte de noms.
                print(f"  [skip] {div} {season_label}: {exc}")
                continue

            payloads = parse_csv_content(csv_text, season_label)
            for payload in payloads:
                names_by_division[div].add(payload["home_team"])
                names_by_division[div].add(payload["away_team"])

    return names_by_division


if __name__ == "__main__":
    result = collect_football_data_team_names(range(2015, 2025))
    for div, names in result.items():
        print(f"\n{div} : {len(names)} équipes distinctes sur 10 saisons")
        for name in sorted(names):
            print(f"  - {name}")
