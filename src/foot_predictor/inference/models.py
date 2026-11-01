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

**Modèle de rejeu H2** (6.10, ADR-0050) : même mécanique, avec la procédure de `M3_H2` du fichier du
test scellé H2 (`experiments/scelle_h2.yaml` : G0 + G1 + G2 + G5, apprentissage de G5 dès 2016-17) sur le
jeu H2. Il n'existe qu'en rejeu : sans abonnement, aucune composition n'arrive en live (ADR-0010), et
aucun modèle H2 n'est appris avec les matchs scellés (ADR-0047, D6).

**Saisons ouvertes au rejeu** : 2021-22 à 2024-25. Les saisons scellées (2025-26 et suivantes)
restent fermées au rejeu **jusqu'au test scellé de H2**, même après celui de H1 : ce second test
réutilisera les mêmes matchs (ADR-0012, règle 5 ; ADR-0045, qui précise la règle 2 de
l'ADR-0011). Le live, lui, les lit comme historique une fois le test H1 terminé.
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
from foot_predictor.seal import SEAL_DATE, SealViolation, check_opened_for_h2_inference

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_ROOT = REPO_ROOT / "models"
REPLAY_ROOT = MODELS_ROOT / "rejeu"
EXPERIMENT_FILE = REPO_ROOT / "experiments" / "scelle_h1.yaml"
MODEL_ID = "M3_G0G2"
EXPERIMENT_FILE_H2 = REPO_ROOT / "experiments" / "scelle_h2.yaml"
MODEL_ID_H2 = "M3_H2"
HORIZONS = ("H1", "H2")
REPLAY_DATASET_VERSION = {"H1": "ds-2026-09-30-ba2b91f7", "H2": "ds-2026-11-01-e0defb32"}
"""Jeu qui entraîne le modèle de rejeu de chaque horizon : celui de l'évaluation qui l'a retenu (ADR-0039, ADR-0050)."""
DEFAULT_ACTIVE_VERSION = "scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle"
"""Modèle actif tant que `ops.model_registry` n'en désigne pas un autre : le modèle final H1, appris
avec les matchs scellés (ADR-0044 ; rendu actif en 5.13, ADR-0045)."""
LIMITS_H2 = [
    "Horizon H2 : la composition annoncée (onze et entraîneur de la feuille de match) n'existe qu'en rejeu ; "
    "aucune prédiction H2 en live après la fin de l'abonnement (ADR-0010, ADR-0047).",
    "Gain mesuré sur la base H1 : +0,00078 de log-loss du total [+0,00003 ; +0,00151] (ADR-0048) ; à fenêtre "
    "d'apprentissage égale, l'intervalle contient 0. Le test scellé H2 ne pourra presque sûrement pas le distinguer de zéro.",
    "Notes de joueurs calculées après le match par le fournisseur, selon une formule inconnue ; seuls les matchs "
    "antérieurs servent (ADR-0013).",
    "Même structure et mêmes limites que H1 pour le reste : indépendance conditionnelle des deux équipes, "
    "championnats du top 5 seulement.",
]
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


def check_replay_season(season: int, sealed_log: Path | None = None) -> None:
    """Refuse une saison de rejeu non ouverte : avant 2021-22, ou scellée tant que le test scellé H2 n'est pas terminé.

    Les saisons scellées (2025-26 et après) s'ouvrent quand le journal porte « évaluation terminée »
    pour `experiments/scelle_h2.yaml` (ADR-0052) ; sans cette ligne, le refus de l'ADR-0045 demeure.
    """
    if season < FIRST_REPLAY_SEASON:
        raise ModelUnavailable(f"Saison {season}-{(season + 1) % 100:02d} : rejeu ouvert à partir de 2021-22.")
    if season >= SEALED_FIRST_SEASON:
        try:
            check_opened_for_h2_inference(sealed_log)
        except SealViolation as error:
            raise ModelUnavailable(
                f"Saison {season}-{(season + 1) % 100:02d} : sous scellés pour le rejeu jusqu'au test scellé de H2, "
                f"qui réutilise ses matchs (ADR-0045, ADR-0052). {error}"
            ) from error


def training_season(season: int) -> int:
    """Pli qui apprend le modèle de rejeu de `season` : 2025-26 et 2026-27 emploient le modèle du test (ADR-0052).

    Le jeu de développement s'arrête avant le 1er juillet 2025 : le pli de 2025 apprend sur 2015-16 à
    2024-25, exactement comme le test scellé. Un modèle de 2026-27 appris sur 2025-26 supposerait de lire
    des matchs scellés pour l'apprentissage ; il n'existe pas.
    """
    return min(season, SEALED_FIRST_SEASON)


def season_of(day: dt.date) -> int:
    """Saison (année de début) d'un jour : une saison commence le 1er juillet."""
    return day.year if day.month >= 7 else day.year - 1


def check_horizon(horizon: str) -> None:
    if horizon not in HORIZONS:
        raise ValueError(f"Horizon inconnu : {horizon} (attendu : {HORIZONS})")


def train_replay_model(
    season: int,
    data: pd.DataFrame,
    manifest: dict | None = None,
    spec_path: Path | None = None,
    horizon: str = "H1",
):
    """(modèle, carte) du pli `season` : même procédure que l'évaluation, apprentissage 2015-16 à S − 1.

    H2 : le début d'apprentissage des groupes à historique court (G5 : 2016-17, rodage D3) est passé à
    `select_and_fit`, comme le fait l'évaluation ; les lignes de rodage ne servent ni au choix ni à
    l'ajustement. Pour H1, `first_training_season` est vide : comportement inchangé.
    """
    check_horizon(horizon)
    spec_path = spec_path or (EXPERIMENT_FILE if horizon == "H1" else EXPERIMENT_FILE_H2)
    model_id = MODEL_ID if horizon == "H1" else MODEL_ID_H2
    spec = load_spec(spec_path)
    model_spec = next(m for m in spec["models"] if m["id"] == model_id)
    make = MODELS[model_spec["model"]]
    grid = [(model_spec.get("params") or {}) | g for g in expand_grid(model_spec.get("grid"))]
    first = make(**grid[0])
    features, first_season = first.features, first.first_training_season
    population = model_spec.get("population", spec.get("population", "top5"))
    fold = protocol.Fold(season)
    fit = protocol.select_and_fit(make, grid, data, fold, population, features, first_season)
    seasons = [s for s in fold.train_seasons if first_season is None or s >= first_season]
    train_rows, _ = protocol.usable(protocol.training_rows(data, seasons, population), features)
    version = f"rejeu-{season}-{model_id.lower()}"
    card = build_card(
        version=version, horizon=horizon, model_spec=model_spec, fit=fit, train_rows=train_rows,
        population=population, manifest=manifest or {}, git=git_state(),
        experiment_file=Path(spec_path).relative_to(REPO_ROOT).as_posix() if Path(spec_path).is_relative_to(REPO_ROOT)
        else Path(spec_path).as_posix(),
        includes_sealed=False, validation=None, limits=LIMITS_H2 if horizon == "H2" else None,
    )  # fmt: skip
    card["replay_season"] = season
    return fit.model, card


def replay_model(
    season: int,
    data: pd.DataFrame | None = None,
    manifest: dict | None = None,
    replay_root: Path = REPLAY_ROOT,
    horizon: str = "H1",
    sealed_log: Path | None = None,
) -> LoadedModel:
    """Modèle de rejeu de la saison : lu dans le cache, sinon entraîné puis mis en cache.

    Le cache de H2 est le sous-dossier `h2/` de celui de H1 : les deux horizons ne se mélangent pas.
    """
    check_horizon(horizon)
    check_replay_season(season, sealed_log)
    season = training_season(season)
    folder = replay_root / str(season) if horizon == "H1" else replay_root / "h2" / str(season)
    if (folder / "model.joblib").exists():
        return load_model(folder)
    if data is None:
        from foot_predictor.features.sources import load_dataset

        data, manifest = load_dataset(REPLAY_DATASET_VERSION[horizon])
    model, card = train_replay_model(season, data, manifest, horizon=horizon)
    slim(model)
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, folder / "model.joblib")
    text = json.dumps(card, indent=2, ensure_ascii=False, default=_json_default) + "\n"
    (folder / "model_card.json").write_text(text, encoding="utf-8", newline="\n")
    return LoadedModel(card["version"], model, card, folder)


def model_for_day(day: dt.date, mode: str, data=None, horizon: str = "H1", **kwargs) -> LoadedModel:
    """Modèle à employer : celui du pli de la saison en rejeu, le modèle actif en live (H1 seulement)."""
    if mode == "replay":
        return replay_model(season_of(day), data, horizon=horizon, **kwargs)
    if mode == "live":
        return load_active(kwargs.get("version"))
    raise ValueError(f"Mode inconnu : {mode} (replay ou live)")
