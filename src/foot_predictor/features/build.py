"""Commande `features build` : lit la porte, construit le jeu, écrit l'instantané et sa trace (ADR-0030)."""

from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import text

from foot_predictor.features import huis_clos, registry, xg_proxy
from foot_predictor.features.dataset import (
    DATASETS_ROOT,
    FIRST_SEASON,
    LAST_SEASON,
    LEARNING_FROM,
    SEALED_DATASETS_ROOT,
    VALIDATION_FROM,
    build_frame,
    counts_of,
    git_commit,
    git_dirty,
    load_elo_params,
    sha256_file,
    write_snapshot,
)
from foot_predictor.features.leagues import LADDERS, REST_RELIABLE_FROM, TOP5
from foot_predictor.features.rolling import HALF_LIVES, MAX_AGE_DAYS, PRIOR_WEIGHT
from foot_predictor.seal import SEAL_DATE


def frozen_parameters() -> dict:
    """Tous les paramètres qui déterminent le contenu du jeu (manifeste, traçabilité)."""
    return {
        "elo": load_elo_params().to_dict(),
        "xg_proxy": asdict(xg_proxy.load()),
        "rolling": {"half_lives_days": list(HALF_LIVES), "max_age_days": MAX_AGE_DAYS, "prior_weight": PRIOR_WEIGHT},
        "huis_clos_sha256": sha256_file(huis_clos.PATH),
        "rest_reliable_from": REST_RELIABLE_FROM,
        "seal_date": SEAL_DATE.isoformat(),
    }


def scope() -> dict:
    return {
        "leagues": sorted(LADDERS),
        "eval_population": sorted(TOP5),
        "seasons": [FIRST_SEASON, LAST_SEASON],
        "phases": {
            "rodage": f"< {LEARNING_FROM}",
            "apprentissage": f"{LEARNING_FROM}-{VALIDATION_FROM - 1}",
            "validation": f"{VALIDATION_FROM}-{LAST_SEASON}",
        },  # fmt: skip
        "rows": "saison régulière, terminés, non exclus, score au temps réglementaire connu ; une ligne par équipe",
    }


def database_trace(connection) -> dict:
    revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    load_run = connection.execute(
        text("SELECT id FROM ops.load_run WHERE status = 'ok' ORDER BY id DESC LIMIT 1")
    ).scalar_one_or_none()
    return {"alembic_revision": revision, "load_run_id": load_run}


def run_build(
    output_root: Path | None = None,
    record: bool = True,
    engine=None,
    today: dt.date | None = None,
    sealed_test: bool = False,
    experiment: str | None = None,
) -> dict:
    """Construit une version du jeu de données ; renvoie un résumé (version, chemin, lignes, durée).

    `sealed_test=True` (test scellé, ADR-0012 règle 5, une fois par version) : lit aussi les matchs
    scellés par la porte (usage journalisé dans `reports/sealed_tests.md`, `experiment` obligatoire)
    et écrit dans `data/datasets_scelles/`, jamais lu par défaut.
    """
    from foot_predictor.features.sources import load_matches

    started = time.monotonic()
    if engine is None:
        from foot_predictor.db.session import get_engine

        engine = get_engine()
    with engine.connect() as connection:
        trace = database_trace(connection)
    if sealed_test and not experiment:
        raise ValueError("--sealed-test exige le fichier d'expérience (--experiment), pour le journal du scellé.")
    # Toutes compétitions ; filtre du scellé en SQL, levé seulement avec sealed_test (journalisé).
    matches = load_matches(engine, sealed_test=sealed_test, experiment=experiment)
    frame = build_frame(matches, load_elo_params(), xg_proxy.load(), huis_clos.load_periods(), sealed_test=sealed_test)
    manifest_base = {
        **trace,
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),  # vrai : construit avec du code non committé, à reconstruire
        "registry_sha256": registry.sha256(),
        "parameters": frozen_parameters(),
        "scope": scope() | ({"sealed_test": True, "experiment": experiment} if sealed_test else {}),
        "counts": counts_of(frame),
    }
    today = today or dt.datetime.now(dt.UTC).date()
    root = Path(output_root) if output_root else (SEALED_DATASETS_ROOT if sealed_test else DATASETS_ROOT)
    path, manifest = write_snapshot(frame, manifest_base, root, today)
    if record:
        with engine.begin() as connection:
            exists = connection.execute(
                text("SELECT manifest_sha256 FROM features.dataset_version WHERE version = :v"),
                {"v": manifest["version"]},
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    text(
                        "INSERT INTO features.dataset_version (version, created_at, git_commit, alembic_revision, "
                        "load_run_id, registry_sha256, manifest_sha256, parameters, scope, counts, path) VALUES "
                        "(:version, :created_at, :git_commit, :alembic_revision, :load_run_id, :registry_sha256, "
                        ":manifest_sha256, CAST(:parameters AS jsonb), CAST(:scope AS jsonb), CAST(:counts AS jsonb), "
                        ":path)"
                    ),
                    {
                        "version": manifest["version"],
                        "created_at": dt.datetime.now(dt.UTC),
                        "git_commit": manifest["git_commit"],
                        "alembic_revision": manifest["alembic_revision"],
                        "load_run_id": manifest["load_run_id"],
                        "registry_sha256": manifest["registry_sha256"],
                        "manifest_sha256": manifest["manifest_sha256"],
                        "parameters": json.dumps(manifest["parameters"]),
                        "scope": json.dumps(manifest["scope"]),
                        "counts": json.dumps(manifest["counts"]),
                        "path": path.as_posix(),
                    },
                )
            elif exists != manifest["manifest_sha256"]:  # impossible : la version vient du sha256
                raise RuntimeError(f"Version {manifest['version']} déjà tracée avec un autre manifeste.")
    return {
        "version": manifest["version"],
        "path": path,
        "rows": manifest["counts"]["rows"],
        "seconds": time.monotonic() - started,
        "manifest": manifest,
    }
