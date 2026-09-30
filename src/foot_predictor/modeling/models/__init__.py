"""Modèles du MVP, tous derrière la même interface (`base.Model` : `fit`, puis `predict`).

`MODELS` associe le nom utilisé dans les fichiers d'expérience (`model: b1`) à la classe.
Le marché (`model: market`) n'est pas un modèle ajustable : l'exécuteur le traite à part
(`modeling/models/market.py`, référence sur l'événement plus/moins 2,5 seulement).
"""

from __future__ import annotations

from foot_predictor.modeling.models.base import Model
from foot_predictor.modeling.models.references import B0, B1
from foot_predictor.modeling.models.team import M3, M4
from foot_predictor.modeling.models.total import M1, M2

MODELS: dict[str, type[Model]] = {"b0": B0, "b1": B1, "m1": M1, "m2": M2, "m3": M3, "m4": M4}
