"""Enchaînement de `load` : API, puis football-data, puis écriture et trace dans `ops.load_run`."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy.engine import Engine

from foot_predictor.collect.api_football.plan import CollectConfig
from foot_predictor.ingestion import yaml_mappings as ym
from foot_predictor.ingestion.load import LoadRefused, Timer, git_commit, manifest_hashes, record_run, write
from foot_predictor.ingestion.load_api import ApiLoad, Rows
from foot_predictor.ingestion.load_external import SEALED_FROM, ExternalLoad

__all__ = ["LoadRefused", "run_load"]


def run_load(
    engine: Engine,
    raw_dir: Path,
    external_raw_dir: Path | None,
    confirm_db: str,
    config: CollectConfig,
    work_dir: Path,
    progress=lambda _message: None,
) -> dict:
    """Reconstruit `staging` et renvoie le résumé écrit dans `ops.load_run`."""
    timer = Timer()
    base = {
        "started_at": timer.started_at,
        "git_commit": git_commit(),
        "raw_dir": str(raw_dir),
        "external_raw_dir": str(external_raw_dir) if external_raw_dir else None,
        "manifests": manifest_hashes(raw_dir, external_raw_dir),
    }
    try:
        rows = Rows(work_dir)
        api = ApiLoad(
            raw_dir, config, aliases=ym.player_aliases(), collision_exceptions=ym.player_collision_exceptions(),
            progress=progress, rows=rows,
        )  # fmt: skip
        api.run()
        counts = dict(api.counts)
        if external_raw_dir is not None:
            teams, hors_api, _ = ym.football_data_teams()
            external = ExternalLoad(api, external_raw_dir, ym.division_to_league(), teams, hors_api)
            external.run()
            counts.update({f"fd_{k}" if not k.startswith("fd_") else k: v for k, v in external.counts.items()})
            counts["fd_rates"] = {f"{d}:{s}": list(v) for (d, s), v in sorted(external.rates.items())}
            counts["fd_score_mismatches_before_seal"] = {
                f"{d}:{s}": n for (d, s), n in external.score_mismatches.items()
            }
            # Non appariés : libellés d'équipes et dates, avant le scellé ; décompte seul ensuite (ADR-0012).
            counts["fd_unmatched_before_seal"] = [
                [u.division, u.season, u.date.isoformat(), u.home, u.away, u.reason]
                for u in external.unmatched
                if u.date < SEALED_FROM
            ]
            counts["fd_unmatched_after_seal"] = sum(1 for u in external.unmatched if u.date >= SEALED_FROM)
        rows.close()
        progress("préparation terminée")
        fingerprints = write(engine, rows, confirm_db, progress=progress)
    except LoadRefused:
        raise  # base refusée : on n'y écrit rien, pas même la trace de l'essai
    except Exception:
        record_run(engine, **base, finished_at=dt.datetime.now(dt.UTC), status="failed", counts=None,
                   fingerprints=None, duration_seconds=timer.seconds)  # fmt: skip
        raise
    run_id = record_run(
        engine, **base, finished_at=dt.datetime.now(dt.UTC), status="ok", counts=counts, fingerprints=fingerprints,
        duration_seconds=timer.seconds,
    )  # fmt: skip
    return {"run_id": run_id, "duration_seconds": timer.seconds, "counts": counts, "fingerprints": fingerprints}
