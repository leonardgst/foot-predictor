"""Modèles de l'inférence : modèle actif (live) et modèles de rejeu par saison (décisions 3 et 4, ADR-0040).

**Modèle actif** : un dossier `models/<version>/` écrit par `train --final` (modèle `joblib` et
carte d'identité). Au chargement, le résultat `statsmodels` est **allégé** (`remove_data` : il
garde ses coefficients et sa covariance, pas ses données d'apprentissage) : 25 Mo → moins de
1 Mo, prédictions identiques au bit près (testé).

**Modèle de rejeu de la saison S** (ADR-0011, règle 1 : « telles que connues à l'époque ») : le
modèle du **pli S**, appris sur 2015-16 à S − 1 selon la procédure du fichier du test scellé
(`experiments/scelle_h1.yaml`, modèle `M3_G0G2`) avec `modeling.protocol.select_and_fit`,
exactement comme l'évaluation l'a fait. Jamais le modèle appris jusqu'en 2024-25. Entraîné à la
demande (quelques secondes), mis en cache dans `models/rejeu/<S>/` avec sa carte.

**Saisons ouvertes au rejeu** : 2021-22 à 2024-25 ; à partir de 2025-26, seulement quand le test
scellé est terminé (journal `reports/sealed_tests.md`, `modeling.sealed.already_evaluated`).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd

from foot_predictor.modeling import protocol
from foot_predictor.modeling.experiment import _json_default, expand_grid, git_state, load_spec
from foot_predictor.modeling.model_card import build_card
from foot_predictor.modeling.models import MODELS
from foot_predictor.seal import SEAL_DATE

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_ROOT = REPO_ROOT / "models"
REPLAY_ROOT = MODELS_ROOT / "rejeu"
EXPERIMENT_FILE = REPO_ROOT / "experiments" / "scelle_h1.yaml"
MODEL_ID = "M3_G0G2"
DEFAULT_ACTIVE_VERSION = "scelle-h1-m3_g0g2-20260930-3c92fc80"
"""Modèle actif tant que `ops.model_registry` (sous-étape 5.4) n'en désigne pas un autre."""
FIRST_REPLAY_SEASON = 2021
SEALED_FIRST_SEASON = SEAL_DATE.year  # 2025-26


class ModelUnavailable(RuntimeError):
    """Modèle absent, ou saison de rejeu non ouverte."""


@dataclass
class LoadedModel:
    version: str
    model: object
    card: dict
    path: Path

    @property
    def features(self) -> tuple[str, ...]:
        return tuple(self.model.features)


def slim(model) -> object:
    """Retire du résultat `statsmodels` ses données d'apprentissage (prédictions inchangées)."""
    result = getattr(model, "result_", None)
    if result is not None and hasattr(result, "remove_data"):
        result.remove_data()
    return model


def load_model(folder: Path) -> LoadedModel:
    folder = Path(folder)
    if not (folder / "model.joblib").exists():
        raise ModelUnavailable(f"Modèle absent : {folder.name} (entraînement final à faire).")
    card = json.loads((folder / "model_card.json").read_text(encoding="utf-8"))
    return LoadedModel(card["version"], slim(joblib.load(folder / "model.joblib")), card, folder)


def load_active(version: str | None = None, models_root: Path = MODELS_ROOT) -> LoadedModel:
    """Modèle actif (live) : la version donnée, sinon celle du registre, sinon la version par défaut."""
    return load_model(models_root / (version or DEFAULT_ACTIVE_VERSION))


def sealed_test_done(experiment: str = "experiments/scelle_h1.yaml", log_path: Path | None = None) -> bool:
    from foot_predictor.modeling.sealed import already_evaluated

    return already_evaluated(experiment, log_path)


def check_replay_season(season: int, log_path: Path | None = None) -> None:
    """Refuse une saison de rejeu non ouverte (avant 2021-22, ou scellée tant que le test n'est pas fait)."""
    if season < FIRST_REPLAY_SEASON:
        raise ModelUnavailable(f"Saison {season}-{(season + 1) % 100:02d} : rejeu ouvert à partir de 2021-22.")
    if season >= SEALED_FIRST_SEASON and not sealed_test_done(log_path=log_path):
        raise ModelUnavailable(
            f"Saison {season}-{(season + 1) % 100:02d} : sous scellés tant que le test scellé n'est pas fait (ADR-0012)."
        )


def season_of(day: dt.date) -> int:
    """Saison (année de début) d'un jour : une saison commence le 1er juillet."""
    return day.year if day.month >= 7 else day.year - 1


def train_replay_model(
    season: int, data: pd.DataFrame, manifest: dict | None = None, spec_path: Path = EXPERIMENT_FILE
):
    """(modèle, carte) du pli `season` : même procédure que l'évaluation, apprentissage 2015-16 à S − 1."""
    spec = load_spec(spec_path)
    model_spec = next(m for m in spec["models"] if m["id"] == MODEL_ID)
    make = MODELS[model_spec["model"]]
    grid = [(model_spec.get("params") or {}) | g for g in expand_grid(model_spec.get("grid"))]
    features = make(**grid[0]).features
    population = model_spec.get("population", spec.get("population", "top5"))
    fold = protocol.Fold(season)
    fit = protocol.select_and_fit(make, grid, data, fold, population, features)
    train_rows, _ = protocol.usable(protocol.training_rows(data, fold.train_seasons, population), features)
    version = f"rejeu-{season}-{MODEL_ID.lower()}"
    card = build_card(
        version=version, horizon="H1", model_spec=model_spec, fit=fit, train_rows=train_rows,
        population=population, manifest=manifest or {}, git=git_state(),
        experiment_file=Path(spec_path).relative_to(REPO_ROOT).as_posix() if Path(spec_path).is_relative_to(REPO_ROOT)
        else Path(spec_path).as_posix(),
        includes_sealed=False, validation=None,
    )  # fmt: skip
    card["replay_season"] = season
    return fit.model, card


def replay_model(
    season: int,
    data: pd.DataFrame | None = None,
    manifest: dict | None = None,
    replay_root: Path = REPLAY_ROOT,
    log_path: Path | None = None,
) -> LoadedModel:
    """Modèle de rejeu de la saison : lu dans le cache, sinon entraîné puis mis en cache."""
    check_replay_season(season, log_path)
    folder = replay_root / str(season)
    if (folder / "model.joblib").exists():
        return load_model(folder)
    if data is None:
        from foot_predictor.features.sources import load_dataset

        data, manifest = load_dataset("ds-2026-09-30-ba2b91f7")
    model, card = train_replay_model(season, data, manifest)
    slim(model)
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, folder / "model.joblib")
    text = json.dumps(card, indent=2, ensure_ascii=False, default=_json_default) + "\n"
    (folder / "model_card.json").write_text(text, encoding="utf-8", newline="\n")
    return LoadedModel(card["version"], model, card, folder)


def model_for_day(day: dt.date, mode: str, data=None, **kwargs) -> LoadedModel:
    """Modèle à employer : celui du pli de la saison en rejeu, le modèle actif en live."""
    if mode == "replay":
        return replay_model(season_of(day), data, **kwargs)
    if mode == "live":
        return load_active(kwargs.get("version"))
    raise ValueError(f"Mode inconnu : {mode} (replay ou live)")
