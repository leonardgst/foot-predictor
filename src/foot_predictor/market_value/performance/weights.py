"""
Pondérations manuelles par cluster (à dire d'expert, pas apprises) -- cf.
recap clustering, section 6 étape 6. À compléter une fois les clusters
réels observés et nommés (étape 4 : nommage manuel après coup).

Vide pour l'instant : le fallback (pondération uniforme) permet de calculer
un score dès maintenant sans bloquer le pipeline, mais ce score n'a de sens
métier qu'une fois les vrais poids renseignés ici.
"""
from __future__ import annotations

CLUSTER_WEIGHTS: dict[str, dict[str, float]] = {
    # À compléter après observation des clusters réels, par ex. :
    # "attacker_0_finisseur": {
    #     "goals_per90_pctl": 0.30,
    #     "xg_per90_pctl": 0.25,
    #     "shots_on_target_per90_pctl": 0.15,
    #     ...
    # },
}


def get_weights_for_cluster(cluster_label: str, feature_columns: list[str]) -> dict[str, float]:
    """Renvoie les poids définis pour ce cluster, ou une pondération uniforme
    par défaut si le cluster n'a pas encore été nommé/pondéré (fallback
    explicite plutôt que silencieux -- le score reste calculable mais n'est
    pas encore le score métier final tant que weights.py n'est pas complété)."""
    if cluster_label in CLUSTER_WEIGHTS:
        return CLUSTER_WEIGHTS[cluster_label]
    uniform_weight = 1.0 / len(feature_columns) if feature_columns else 0.0
    return {col: uniform_weight for col in feature_columns}
