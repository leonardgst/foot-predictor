"""
Vérification à lancer AVANT tout scraping réel :
    APP_ENV=dev uv run python check_env.py

Ne fait aucun appel réseau vers les sources externes (football-data,
API-Football, Understat) — vérifie juste que le terrain est prêt.
"""
from __future__ import annotations

import importlib
import os
import sys

CHECKS_OK = []
CHECKS_FAIL = []


def check(label: str, fn):
    try:
        fn()
        CHECKS_OK.append(label)
    except Exception as exc:  # noqa: BLE001
        CHECKS_FAIL.append(f"{label} -> {exc}")


def check_imports():
    for module in ("requests", "understatapi", "sqlalchemy", "alembic", "yaml"):
        importlib.import_module(module)


def check_env_vars():
    missing = [v for v in ("APP_ENV",) if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"variables manquantes: {missing}")


def check_api_football_key():
    if not os.environ.get("API_FOOTBALL_KEY"):
        raise RuntimeError(
            "API_FOOTBALL_KEY absente de l'environnement "
            "(hors .env.*, à exporter manuellement dans le shell)"
        )


def check_db_connection():
    from foot_predictor.db.session import get_engine
    from sqlalchemy import text

    with get_engine().connect() as conn:
        schemas = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name IN ('raw', 'staging', 'features')"
                )
            )
        }
        missing = {"raw", "staging", "features"} - schemas
        if missing:
            raise RuntimeError(f"schémas manquants: {missing}")


def check_alembic_head():
    import subprocess

    result = subprocess.run(
        ["uv", "run", "alembic", "current"], capture_output=True, text=True, check=True
    )
    if "(head)" not in result.stdout:
        raise RuntimeError(f"pas à jour (head) : {result.stdout.strip()}")


def check_mapping_files():
    from pathlib import Path

    mappings_dir = Path("src/foot_predictor/ingestion/mappings")
    expected = ["football_data_competitions.yaml", "football_data_teams.yaml", "understat_teams.yaml"]
    missing = [f for f in expected if not (mappings_dir / f).exists()]
    if missing:
        raise RuntimeError(f"mappings absents (pas bloquant, mapping vide utilisé) : {missing}")


if __name__ == "__main__":
    check("Dépendances Python importables (requests, understatapi, sqlalchemy...)", check_imports)
    check("Variable APP_ENV définie", check_env_vars)
    check("API_FOOTBALL_KEY définie (nécessaire avant l'étape 3-4)", check_api_football_key)
    check("Connexion DB + schémas raw/staging/features présents", check_db_connection)
    check("Migrations Alembic à jour (head)", check_alembic_head)
    check("Fichiers de mapping présents", check_mapping_files)

    print("=== OK ===")
    for c in CHECKS_OK:
        print(f"  ✅ {c}")
    print("=== ÉCHECS ===")
    for c in CHECKS_FAIL:
        print(f"  ❌ {c}")

    sys.exit(1 if CHECKS_FAIL else 0)