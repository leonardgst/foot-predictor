"""Diagnostic (lecture seule) : liste les valeurs brutes home_team/away_team
réellement stockées dans raw.football_data_match pour une division donnée, et
les compare caractère par caractère aux clés de football_data_teams.yaml.

Usage :
    APP_ENV=dev uv run python scripts/one_off/check_raw.py [DIV]    # ex. SP1

Sans argument, parcourt toutes les divisions présentes en base.
"""
import sys
from pathlib import Path

import yaml
from sqlalchemy import select

from foot_predictor.db.models import FootballDataMatch
from foot_predictor.db.session import get_session

MAPPING_PATH = Path("src/foot_predictor/ingestion/mappings/football_data_teams.yaml")
mapping = yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8"))

div_filter = sys.argv[1] if len(sys.argv) > 1 else None

raw_names_by_div: dict[str, set[str]] = {}
with get_session() as session:
    for row in session.scalars(select(FootballDataMatch)):
        payload = row.raw_payload
        div = payload["div"]
        if div_filter and div != div_filter:
            continue
        names = raw_names_by_div.setdefault(div, set())
        names.add(payload["home_team"])
        names.add(payload["away_team"])

for div, names in sorted(raw_names_by_div.items()):
    print(f"\n=== {div} : {len(names)} valeurs brutes distinctes ===")
    for name in sorted(names):
        # Absent du YAML n'est pas une anomalie : get_or_create_team retombe alors
        # sur le nom brut comme nom canonique (cas normal quand brut == canonique).
        status = "mappé   " if name in mapping else "identité"
        print(f"  {name!r:35} len={len(name):2}  {status}  -> {mapping.get(name, name)!r}")

if not raw_names_by_div:
    print("Aucune ligne trouvée" + (f" pour la division {div_filter!r}." if div_filter else "."))
