"""> **Remplacé (partie 4, ADR-0037) — retrait en partie 5.** Ancien module (modèles A et B, schéma `features.team_match_features`) ; le protocole et les modèles du MVP sont dans `modeling/protocol.py`, `experiment.py` et `modeling/models/`.

Entraîne le Modèle A (Poisson indépendant, retenu comme référence --
`docs/RESULTATS_MODELE.md`) sur TOUT l'historique disponible (pas seulement
le train set du split chronologique de `run_comparison.py`, qui existe pour
comparer A et B équitablement) et persiste le résultat via joblib
(`persistence.py`), pour que `predict_service.py` n'ait pas à ré-entraîner à
chaque appel.

Lancement : APP_ENV=<env> uv run python -m foot_predictor.modeling.legacy.train_and_persist
"""

from __future__ import annotations

import datetime as dt

from foot_predictor.db.session import get_session
from foot_predictor.modeling.legacy.dataset import build_dataset
from foot_predictor.modeling.legacy.features_config import DEFAULT_FEATURE_COLUMNS
from foot_predictor.modeling.legacy.persistence import DEFAULT_MODEL_PATH, PersistedPoissonModel, save_model
from foot_predictor.modeling.legacy.poisson_model import fit_poisson_model


def main() -> None:
    with get_session() as session:
        print("Construction du dataset (X, y) depuis features.team_match_features...")
        dataset = build_dataset(session, feature_columns=DEFAULT_FEATURE_COLUMNS)
        print(f"  {len(dataset.X)} lignes ({len(dataset.X) // 2} matchs environ)")
        print(f"  matchs écartés (features manquantes d'un côté) : {dataset.n_matches_dropped_missing_features}")
        print(f"  lignes écartées (valeur de feature manquante) : {dataset.n_rows_dropped_missing_values}")

        print("\nAjustement du Modèle A (Poisson indépendant) sur l'historique complet...")
        model = fit_poisson_model(dataset.X, dataset.y)

        persisted = PersistedPoissonModel(
            model=model,
            z_feature_columns=list(DEFAULT_FEATURE_COLUMNS),
            trained_at=dt.datetime.now(dt.UTC),
            n_rows_train=len(dataset.X),
        )
        path = save_model(persisted, DEFAULT_MODEL_PATH)
        print(f"\nModèle persisté dans {path} ({persisted.n_rows_train} lignes d'entraînement).")


if __name__ == "__main__":
    main()
