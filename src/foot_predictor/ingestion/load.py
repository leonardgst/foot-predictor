"""Écriture du référentiel en base : `staging` vidé puis rechargé en une transaction (ADR-0008).

`load` est une **reconstruction complète** : `staging` (et, par cascade, les
tables `features` qui en dépendent) est vidé, puis rechargé par `COPY` depuis
les lignes préparées par `load_api` et `load_external`. Les identifiants
internes sont écrits tels quels : deux chargements du même brut donnent les
mêmes tables, ce que vérifient les empreintes (`fingerprints`).

Garde-fous, vérifiés avant toute écriture :

- `confirm_db` doit être le nom de la base connectée (on sait ce qu'on vide) ;
- la base ne doit contenir **aucune ligne** dans le schéma `raw` : c'est la
  marque de l'ancienne base dev (brut en JSONB, 19 fusions manuelles), qui ne
  doit jamais être vidée (décision M14 : ancienne base intacte) ;
- la base doit être à la dernière migration.

Chaque exécution laisse une ligne dans `ops.load_run` : date, commit, sha256 des
journaux lus, décomptes, empreintes, durée, statut.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from foot_predictor.ingestion.load_api import COLUMNS, Rows, csv_value
from foot_predictor.rawstore.manifest import MANIFEST_DIR

# Ordre des COPY : une table ne référence que des tables déjà chargées.
TABLES = [
    "competition", "season", "team", "coach", "player", "match", "team_match", "team_match_stats",
    "lineup", "player_match_stats", "competition_source_mapping", "team_source_mapping", "match_source_mapping",
    "team_match_stats_external", "match_odds",
]  # fmt: skip
# Vidées avant chargement (CASCADE : features.* qui référencent staging).
TRUNCATED = [
    "staging.player_injury", "staging.coach_source_mapping", "staging.player_source_mapping",
    *(f"staging.{table}" for table in TABLES),
]  # fmt: skip
FINGERPRINT_EXCLUDED = {"created_at"}
ALEMBIC_HEAD = "0007_cotes_football_data"


class LoadRefused(RuntimeError):
    """La base visée n'est pas une base de travail reconstructible."""


def check_target(connection, confirm_db: str) -> None:
    current = connection.execute(text("SELECT current_database()")).scalar_one()
    if current != confirm_db:
        raise LoadRefused(f"Base connectée « {current} », confirmée « {confirm_db} » : chargement refusé.")
    version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if version != ALEMBIC_HEAD:
        raise LoadRefused(f"Base en révision {version}, {ALEMBIC_HEAD} attendue : lancer alembic upgrade head.")
    for (table,) in connection.execute(
        text("SELECT format('%I.%I', schemaname, relname) FROM pg_stat_user_tables WHERE schemaname = 'raw'")
    ):
        if connection.execute(text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar_one():
            raise LoadRefused(
                f"{table} contient des lignes : c'est l'ancienne base (brut JSONB). Elle ne se vide pas (M14)."
            )


def manifest_hashes(*raw_dirs: Path | None) -> dict[str, str]:
    """sha256 de chaque journal `_manifest/*.jsonl` lu, pour `ops.load_run`."""
    hashes = {}
    for raw_dir in raw_dirs:
        if raw_dir is None:
            continue
        for path in sorted((Path(raw_dir) / MANIFEST_DIR).glob("*.jsonl")):
            if ".rebuilt-" not in path.name:
                hashes[path.resolve().as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def git_commit() -> str | None:
    try:
        done = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def _copy(cursor, table: str, rows: Rows) -> None:
    columns = ", ".join(COLUMNS[table])
    with cursor.copy(f"COPY staging.{table} ({columns}) FROM STDIN WITH (FORMAT csv)") as copy:
        path = rows.path(table)
        if path is not None:
            with open(path, "rb") as handle:
                while chunk := handle.read(1 << 20):
                    copy.write(chunk)
        else:
            import csv
            import io

            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            for row in rows.tables.get(table, []):
                writer.writerow([csv_value(v) for v in row])
            copy.write(buffer.getvalue().encode("utf-8"))


def fingerprints(connection) -> dict[str, dict]:
    """Nombre de lignes et md5 de chaque table chargée (colonnes hors `created_at`, triées par id)."""
    result = {}
    for table in TABLES:
        columns = [
            name
            for (name,) in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'staging' "
                    "AND table_name = :t ORDER BY ordinal_position"
                ),
                {"t": table},
            )
            if name not in FINGERPRINT_EXCLUDED
        ]
        cols = ", ".join(f'"{c}"' for c in columns)
        count, digest = connection.execute(
            text(
                f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t.id), '')) FROM (SELECT {cols} FROM staging.{table}) t"
            )
        ).one()
        result[table] = {"rows": count, "md5": digest}
    return result


def write(engine: Engine, rows: Rows, confirm_db: str, progress=lambda _message: None) -> dict[str, dict]:
    """Vide `staging`, copie les lignes, recale les séquences ; renvoie les empreintes."""
    with engine.begin() as connection:
        check_target(connection, confirm_db)
        connection.execute(text(f"TRUNCATE {', '.join(TRUNCATED)} CASCADE"))
        progress("staging vidé")
        cursor = connection.connection.driver_connection.cursor()
        for table in TABLES:
            if rows.counts.get(table) or rows.tables.get(table):
                _copy(cursor, table, rows)
                progress(f"COPY {table} : {rows.counts.get(table) or len(rows.tables.get(table, []))} lignes")
        for table in TABLES:
            connection.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('staging.{table}', 'id'), "
                    f"coalesce(max(id), 1), max(id) IS NOT NULL) FROM staging.{table}"
                )
            )
        return fingerprints(connection)


def record_run(engine: Engine, **values) -> int:
    with engine.begin() as connection:
        return connection.execute(
            text(
                "INSERT INTO ops.load_run (started_at, finished_at, status, git_commit, raw_dir, external_raw_dir, "
                "manifests, counts, fingerprints, duration_seconds) VALUES (:started_at, :finished_at, :status, "
                ":git_commit, :raw_dir, :external_raw_dir, CAST(:manifests AS jsonb), CAST(:counts AS jsonb), "
                "CAST(:fingerprints AS jsonb), :duration_seconds) RETURNING id"
            ),
            {**values, **{k: json.dumps(values.get(k)) for k in ("manifests", "counts", "fingerprints")}},
        ).scalar_one()


class Timer:
    def __init__(self) -> None:
        self.started_at = dt.datetime.now(dt.UTC)
        self._start = time.monotonic()

    @property
    def seconds(self) -> float:
        return round(time.monotonic() - self._start, 1)
