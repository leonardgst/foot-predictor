"""M7 : boosting d'arbres à perte de Poisson, par équipe (rapport I.4 ; ADR-0049).

Question : **une structure non linéaire et à interactions fait-elle mieux que log λ = xᵀβ ?** M3 et M6
supposent que les variables agissent linéairement dans log λ. Le boosting ajoute des arbres peu profonds,
chacun corrigeant l'erreur des précédents sous la déviance de Poisson ; il peut donc capter une courbure
(l'effet de l'Elo qui s'aplatit aux extrêmes) ou une interaction (domicile × force) que M3 ignore.

`sklearn.ensemble.HistGradientBoostingRegressor(loss="poisson")` : la prédiction est directement λ
(le lien log est appliqué par la perte). Aucune dépendance de plus (scikit-learn sert déjà à M6).

**Mêmes variables que M3 et M6** : la matrice vient de `Design` (même rodage D3, mêmes lignes exclues, mêmes
colonnes constantes retirées). La standardisation de `Design` ne change rien à un arbre, qui ne dépend que de
l'ordre des valeurs ; la constante en est retirée. Une comparaison M3 / M6 / M7 ne change donc que la structure.

**Déterminisme et pas d'arrêt précoce** : `early_stopping=False`, car l'arrêt précoce de scikit-learn tire
au hasard un échantillon de validation parmi les lignes d'apprentissage, sans respecter l'ordre du temps ;
le nombre d'itérations est un hyperparamètre choisi par la validation interne du protocole (ADR-0037),
jamais sur la saison de test. Sans sous-échantillonnage, l'ajustement ne dépend d'aucun hasard
(`random_state` est fixé pour le rendre explicite).
"""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from foot_predictor.modeling.design import Design
from foot_predictor.modeling.models.base import MatchPredictions, Model
from foot_predictor.modeling.models.team import _pair

RANDOM_STATE = 20260930


class M7(Model):
    """Boosting d'arbres à perte de Poisson par équipe, mêmes variables que M3 (matrice de `Design`)."""

    name = "M7"

    def __init__(
        self,
        groups=("G0", "G1", "G2", "G5"),
        half_life: int | None = 120,
        max_depth: int = 3,
        max_iter: int = 200,
        learning_rate: float = 0.05,
        min_samples_leaf: int = 200,
        l2_regularization: float = 1.0,
        train_from: int | None = None,
    ) -> None:
        if max_depth < 1 or max_iter < 1 or min_samples_leaf < 1:
            raise ValueError("max_depth, max_iter et min_samples_leaf doivent être au moins 1")
        if not 0 < learning_rate <= 1:
            raise ValueError("learning_rate doit être dans ]0 ; 1]")
        if l2_regularization < 0:
            raise ValueError("l2_regularization doit être positif ou nul")
        half_life = half_life if "G2" in groups else None
        # `train_from` : début d'apprentissage imposé en plus de celui des groupes (témoin de fenêtre, ADR-0049).
        extra = {} if train_from is None else {"train_from": train_from}
        super().__init__(
            groups=list(groups),
            half_life=half_life,
            max_depth=max_depth,
            max_iter=max_iter,
            learning_rate=learning_rate,
            min_samples_leaf=min_samples_leaf,
            l2_regularization=l2_regularization,
            **extra,
        )
        self.design = Design(tuple(groups), half_life, level="team")
        self.features = tuple(self.design.required())
        starts = [s for s in (self.design.first_training_season, train_from) if s is not None]
        self.first_training_season = max(starts) if starts else None

    def _matrix(self, rows: pd.DataFrame, fit: bool) -> pd.DataFrame:
        frame = self.design.fit_transform(rows) if fit else self.design.transform(rows)
        return frame.drop(columns=["const"])

    def fit(self, rows: pd.DataFrame) -> M7:
        X = self._matrix(rows, fit=True)
        y = rows["goals_for"].to_numpy(dtype=float)
        self.columns_ = list(X.columns)
        self.model_ = HistGradientBoostingRegressor(
            loss="poisson",
            learning_rate=self.params["learning_rate"],
            max_iter=self.params["max_iter"],
            max_depth=self.params["max_depth"],
            min_samples_leaf=self.params["min_samples_leaf"],
            l2_regularization=self.params["l2_regularization"],
            early_stopping=False,
            random_state=RANDOM_STATE,
        ).fit(X.to_numpy(), y)
        self.n_rows_ = int(len(y))
        return self

    def team_lambda(self, rows: pd.DataFrame):
        return self.model_.predict(self._matrix(rows, fit=False).to_numpy())

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:
        ids, lambda_home, lambda_away = _pair(rows, self.team_lambda(rows))
        return MatchPredictions.independent_poisson(ids, lambda_home, lambda_away)

    def describe(self) -> dict:
        return super().describe() | {
            "n_rows": getattr(self, "n_rows_", None),
            "n_iterations": int(self.model_.n_iter_) if hasattr(self, "model_") else None,
            "columns": getattr(self, "columns_", []),
            "design": self.design.describe(),
        }
