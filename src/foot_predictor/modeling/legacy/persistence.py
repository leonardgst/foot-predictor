"""> **Remplacé (partie 4, ADR-0037) — retrait en partie 5.** Ancien module (modèles A et B, schéma `features.team_match_features`) ; le protocole et les modèles du MVP sont dans `modeling/protocol.py`, `experiment.py` et `modeling/models/`.

Persistence du Modèle A entraîné (joblib), pour éviter de ré-entraîner à
chaque appel du service d'inférence (`predict_service.py`).

Ce qui est persisté n'est pas seulement le `PoissonModel` (coefficients
statsmodels) mais aussi `z_feature_columns` : la liste exacte des colonnes de
`features.team_match_features` utilisées au moment de l'entraînement (cf.
`features_config.py`). C'est cette liste qui pilote quelles features
`live_features.py` doit recalculer en direct pour un match à venir -- la
coder en dur côté inférence risquerait de diverger silencieusement du modèle
réellement chargé si `DEFAULT_FEATURE_COLUMNS` change plus tard (ex. ajout de
z9-z11).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import joblib

from foot_predictor.modeling.legacy.poisson_model import PoissonModel

DEFAULT_MODEL_PATH = Path("models/poisson_model_a.joblib")


@dataclass(frozen=True)
class PersistedPoissonModel:
    model: PoissonModel
    z_feature_columns: list[str]
    trained_at: dt.datetime
    n_rows_train: int


def save_model(persisted: PersistedPoissonModel, path: Path = DEFAULT_MODEL_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(persisted, path)
    return path


def load_model(path: Path = DEFAULT_MODEL_PATH) -> PersistedPoissonModel:
    if not path.exists():
        raise FileNotFoundError(
            f"Aucun modèle persisté à {path}. Lancer d'abord : "
            "APP_ENV=<env> uv run python -m foot_predictor.modeling.legacy.train_and_persist"
        )
    return joblib.load(path)
