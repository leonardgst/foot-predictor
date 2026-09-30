"""Carte d'identité d'un modèle entraîné (rapport F.4, ADR-0010 : horizon déclaré).

Tout ce qu'il faut pour savoir **ce qu'est** un modèle et **d'où il vient**, sans le relancer :
version, horizon, classe et hyperparamètres retenus (avec les scores de la validation interne),
variables requises, période et population d'apprentissage, empreinte du jeu de données, commit et
révision Alembic, métriques de validation (rapport d'expérience de référence), limites connues.

La carte est écrite dans `models/<version>/model_card.json` (dossier ignoré par Git, avec le
modèle) et copiée dans `reports/model_cards/<version>.json` (versionné).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

KNOWN_LIMITS_H1 = [
    "Horizon H1 : aucune information de composition (ADR-0010).",
    "Indépendance conditionnelle des deux équipes (Dixon-Coles sans gain, ADR-0038) ; légère sous-dispersion "
    "des buts par équipe (φ ≈ 0,98) non modélisée.",
    "En live, les tirs de G2 viennent de football-data seulement : écart d'xg_proxy de +0,02 en moyenne, "
    "+0,08 en Serie A (ADR-0035), à contrôler en partie 5.",
    "Les coupes ne sont pas des matchs d'évaluation ; le modèle est appris et validé sur les championnats du top 5.",
    "Calibration de P(T > 2,5) : un décile sur dix à 3,8 points en validation glissante (ADR-0039).",
]


def training_period(rows: pd.DataFrame) -> dict:
    dates = pd.to_datetime(rows["match_date"], utc=True)
    return {
        "first_season": int(rows["season_year"].min()),
        "last_season": int(rows["season_year"].max()),
        "first_match": dates.min().isoformat(),
        "last_match": dates.max().isoformat(),
        "rows": int(len(rows)),
        "matches": int(rows["match_id"].nunique()),
    }


def validation_metrics(report: dict | None, model_id: str | None) -> dict | None:
    """Métriques poolées d'un rapport d'expérience pour le modèle `model_id`, et ses comparaisons."""
    if not report or not model_id:
        return None
    pooled = report["pooled"][model_id]
    calibration = {k: pooled["calibration_over_2_5"][k] for k in ("mean_abs_gap", "slope", "intercept")}
    comparisons = [
        {"a": c["a"], "b": c["b"], "log_loss": c["log_loss"]["pooled"]}
        for c in report["comparisons"]
        if model_id in (c["a"], c["b"]) and "log_loss" in c
    ]
    return {
        "report": report["id"],
        "model_id": model_id,
        "folds": [f["name"] for f in report["folds"]],
        "log_loss": pooled["log_loss"],
        "rps": pooled["rps"],
        "brier_over_2_5": pooled["brier_over_2_5"],
        "matches": pooled["matches"],
        "calibration_over_2_5": calibration,
        "comparisons": comparisons,
    }


def build_card(
    *,
    version: str,
    horizon: str,
    model_spec: dict,
    fit,
    train_rows: pd.DataFrame,
    population: str,
    manifest: dict,
    git: dict,
    experiment_file: str,
    includes_sealed: bool,
    validation: dict | None,
    created_at: dt.datetime | None = None,
    limits: list[str] | None = None,
) -> dict:
    """Carte d'identité (dictionnaire sérialisable en JSON)."""
    described = fit.model.describe()
    return {
        "version": version,
        "created_at": (created_at or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds"),
        "horizon": horizon,
        "model": {
            "id": model_spec["id"],
            "class": fit.model.name,
            "params": fit.params,
            "grid": model_spec.get("grid"),
            "features": list(fit.model.features),
            "design": described.get("diagnostics", {}).get("design") or described.get("design"),
        },
        "hyperparameters": {"chosen": fit.params, "inner_validation": fit.inner_scores},
        "training": {
            **training_period(train_rows),
            "population": population,
            "excluded_rows": fit.excluded_train_rows,
            "includes_sealed_matches": includes_sealed,
        },
        "dataset": {
            "version": manifest.get("version"),
            "manifest_sha256": manifest.get("manifest_sha256"),
            "registry_sha256": manifest.get("registry_sha256"),
            "load_run_id": manifest.get("load_run_id"),
        },
        "alembic_revision": manifest.get("alembic_revision"),
        "code": git,
        "experiment_file": experiment_file,
        "coefficients": described.get("diagnostics", {}).get("coefficients"),
        "validation": validation,
        "limits": limits if limits is not None else KNOWN_LIMITS_H1,
    }
