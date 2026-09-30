"""Entraînement final (`python -m foot_predictor.modeling train --final`) : un modèle, sa carte d'identité.

Procédure, identique à celle du fichier d'expérience (validation interne puis réajustement) :

- `include_sealed=False` (défaut) : apprentissage sur les saisons de développement du fichier
  (`train_seasons`, 2015-16 à 2024-25 pour `experiments/scelle_h1.yaml`) ; validation interne sur la
  dernière. C'est l'entraînement du test scellé (4.16), exécutable sur les données de développement.
- `include_sealed=True` : après le test scellé seulement (le journal doit contenir l'évaluation
  terminée) ; jeu construit avec `--sealed-test`, apprentissage sur **toutes** les saisons présentes,
  matchs scellés compris (4.17). Lecture journalisée.

**Jamais d'écrasement** : chaque version a son dossier `models/<version>/` (ignoré par Git : le
modèle sérialisé et sa carte) ; la carte est copiée dans `reports/model_cards/<version>.json`.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import joblib
import pandas as pd

from foot_predictor.modeling import protocol
from foot_predictor.modeling.experiment import _json_default, expand_grid, git_state, load_spec
from foot_predictor.modeling.model_card import build_card, validation_metrics
from foot_predictor.modeling.models import MODELS

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_ROOT = REPO_ROOT / "models"
CARDS_DIR = REPO_ROOT / "reports" / "model_cards"


class FinalTrainingError(RuntimeError):
    """Entraînement final refusé (modèle inconnu, version existante, scellé non levé)."""


def train_final(
    experiment_path: Path,
    model_id: str,
    *,
    data: pd.DataFrame | None = None,
    manifest: dict | None = None,
    dataset: str | None = None,
    include_sealed: bool = False,
    validation_report: Path | None = None,
    validation_model: str | None = None,
    models_root: Path = MODELS_ROOT,
    cards_dir: Path = CARDS_DIR,
    sealed_log: Path | None = None,
    today: dt.date | None = None,
) -> dict:
    """Entraîne `model_id` de l'expérience selon sa procédure ; écrit modèle et carte ; renvoie la carte."""
    experiment_path = Path(experiment_path)
    spec = load_spec(experiment_path)
    model_spec = next((m for m in spec["models"] if m["id"] == model_id), None)
    if model_spec is None or model_spec["model"] not in MODELS:
        raise FinalTrainingError(f"{model_id} : absent de {experiment_path} ou non entraînable.")
    if include_sealed:
        from foot_predictor.modeling.sealed import already_evaluated

        if not already_evaluated(experiment_path.as_posix(), sealed_log):
            raise FinalTrainingError("Apprentissage avec les matchs scellés refusé : le test scellé n'est pas fait.")
    if data is None:
        from foot_predictor.features.sources import load_dataset

        data, manifest = load_dataset(
            dataset or spec.get("dataset"),
            sealed_test=include_sealed,
            experiment=experiment_path.as_posix() if include_sealed else None,
            sealed_log=sealed_log,
        )
    first, last = spec.get("train_seasons", [protocol.FIRST_TRAINING_SEASON, protocol.SEAL_DATE.year - 1])
    if include_sealed:
        last = int(data["season_year"].max())
    fold = protocol.Fold(int(last) + 1, first_season=int(first), train_on_sealed=include_sealed)
    make = MODELS[model_spec["model"]]
    grid = [(model_spec.get("params") or {}) | g for g in expand_grid(model_spec.get("grid"))]
    features = make(**grid[0]).features
    population = model_spec.get("population", spec.get("population", "top5"))
    fit = protocol.select_and_fit(make, grid, data, fold, population, features)
    train_rows, _ = protocol.usable(protocol.training_rows(data, fold.train_seasons, population), features)

    git = git_state()
    today = today or dt.datetime.now(dt.UTC).date()
    version = f"{spec['name']}-{model_id}-{today:%Y%m%d}-{(git.get('commit') or 'inconnu')[:8]}".lower()
    if include_sealed:
        version += "-avec-scelle"
    folder = models_root / version
    if folder.exists():
        raise FinalTrainingError(f"{folder} existe déjà : un modèle n'est jamais écrasé.")
    report = json.loads(Path(validation_report).read_text(encoding="utf-8")) if validation_report else None
    card = build_card(
        version=version,
        horizon="H1",
        model_spec=model_spec,
        fit=fit,
        train_rows=train_rows,
        population=population,
        manifest=manifest or {},
        git=git,
        experiment_file=experiment_path.as_posix(),
        includes_sealed=include_sealed,
        validation=validation_metrics(report, validation_model or model_id),
    )
    folder.mkdir(parents=True)
    joblib.dump(fit.model, folder / "model.joblib")
    text = json.dumps(card, indent=2, ensure_ascii=False, default=_json_default) + "\n"
    (folder / "model_card.json").write_text(text, encoding="utf-8", newline="\n")
    cards_dir.mkdir(parents=True, exist_ok=True)
    (cards_dir / f"{version}.json").write_text(text, encoding="utf-8", newline="\n")
    return card
