"""
Téléchargement football-data.co.uk -> raw.football_data_match.

Contrairement à Transfermarkt/Understat, football-data.co.uk n'est PAS du
scraping HTML : c'est un téléchargement direct de CSV publiés gratuitement
par le site pour cet usage (voir https://www.football-data.co.uk/data.php,
qui indique explicitement que les données sont fournies "for the purposes
of league match prediction"). Fichiers mis à jour au moins 2x/semaine par
le site -> une exécution quotidienne (ou moins) suffit largement, pas besoin
de polling agressif.

URL pattern confirmé : https://www.football-data.co.uk/mmz4281/{season}/{div}.csv
  - season : 4 chiffres, ex. "2425" pour 2024-2025
  - div    : code championnat, ex. "E0" (Premier League), "P1" (Liga Portugal)

Idempotent au niveau raw : upsert sur la clé naturelle (div, date, home_team,
away_team) plutôt qu'un simple append, pour éviter une croissance illimitée
de la table à chaque exécution (le fichier redonne l'intégralité de la saison
à chaque téléchargement, y compris les matchs déjà connus).
"""
from __future__ import annotations

import csv
import datetime as dt
import io

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import FootballDataMatch, SourceIngestionLog

BASE_URL = "https://www.football-data.co.uk/mmz4281"
USER_AGENT = "foot-predictor-research-bot/1.0 (personal educational project)"

# Championnats couverts en V1 (cf. mappings/football_data_competitions.yaml)
DIVISIONS = ["E0", "SP1", "D1", "I1", "F1"]


def season_code(start_year: int) -> str:
    """2024 -> '2425' (format attendu par l'URL football-data.co.uk)."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _parse_match_date(raw_date: str) -> str:
    """football-data.co.uk change de format de date selon l'ancienneté de la
    saison : 'DD/MM/YYYY' pour les saisons récentes, 'DD/MM/YY' (année sur 2
    chiffres) pour les plus anciennes -- on essaie les deux, dans cet ordre."""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(raw_date, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Format de date non reconnu par football-data : {raw_date!r}")


def parse_csv_content(csv_text: str, season_label: str) -> list[dict]:
    """Parse le contenu CSV brut en une liste de payloads jsonb prêts pour raw."""
    reader = csv.DictReader(io.StringIO(csv_text))
    payloads = []
    for row in reader:
        if not row.get("Date") or not row.get("HomeTeam"):
            continue  # ligne vide en fin de fichier, fréquent chez football-data
        match_date = _parse_match_date(row["Date"])
        payloads.append(
            {
                "div": row["Div"],
                "season_label": season_label,
                "date": match_date,
                "home_team": row["HomeTeam"],
                "away_team": row["AwayTeam"],
                "fthg": _parse_int(row.get("FTHG")),
                "ftag": _parse_int(row.get("FTAG")),
            }
        )
    return payloads


def _upsert_raw_row(session: Session, ingestion_id: int, payload: dict) -> str:
    """Renvoie 'created', 'updated' ou 'unchanged'."""
    existing = session.scalar(
        select(FootballDataMatch).where(
            FootballDataMatch.raw_payload["div"].astext == payload["div"],
            FootballDataMatch.raw_payload["date"].astext == payload["date"],
            FootballDataMatch.raw_payload["home_team"].astext == payload["home_team"],
            FootballDataMatch.raw_payload["away_team"].astext == payload["away_team"],
        )
    )
    if existing is None:
        session.add(FootballDataMatch(ingestion_id=ingestion_id, raw_payload=payload))
        return "created"
    if existing.raw_payload != payload:
        existing.raw_payload = payload
        existing.ingestion_id = ingestion_id
        return "updated"
    return "unchanged"


def fetch_division(div: str, season_label: str) -> str:
    """Télécharge le CSV d'un championnat/saison. Lève une exception si échec."""
    start_year = int(season_label.split("-")[0])
    url = f"{BASE_URL}/{season_code(start_year)}/{div}.csv"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.content.decode("utf-8-sig")  # utf-8-sig : gère le BOM automatiquement


def ingest_football_data_source(session: Session, season_label: str) -> dict:
    """
    Télécharge et ingère tous les championnats de DIVISIONS pour une saison donnée.
    Une source_ingestion_log par championnat, pour tracer précisément les échecs
    (un championnat en échec ne bloque pas les autres).
    """
    summary = {}
    for div in DIVISIONS:
        log = SourceIngestionLog(
            source_name="football-data",
            payload_ref=f"{BASE_URL}/{season_code(int(season_label.split('-')[0]))}/{div}.csv",
            status="pending",
        )
        session.add(log)
        session.flush()

        try:
            csv_text = fetch_division(div, season_label)
            payloads = parse_csv_content(csv_text, season_label)

            counts = {"created": 0, "updated": 0, "unchanged": 0}
            for payload in payloads:
                result = _upsert_raw_row(session, log.id, payload)
                counts[result] += 1

            log.status = "success"
            summary[div] = counts
        except requests.RequestException as exc:
            log.status = "failed"
            summary[div] = {"error": str(exc)}

        session.commit()

    return summary


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    # Backfill des 10 dernières saisons (cf. mapping_builder, même logique que
    # api_football_scraper.py -- gratuit et instantané ici, pas de contrainte
    # de quota contrairement à API-Football).
    SEASON_START_YEARS = range(2015, 2025)

    with get_session() as session:
        for start_year in SEASON_START_YEARS:
            season_label = f"{start_year}-{start_year + 1}"
            summary = ingest_football_data_source(session, season_label)
            for div, counts in summary.items():
                print(f"{season_label} / {div}: {counts}")