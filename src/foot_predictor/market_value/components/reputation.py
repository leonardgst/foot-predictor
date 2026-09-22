"""Composante Réputation du MVS (cf. recap projet, section 4) : à dire
d'expert, comme Potentiel -- pas de dataset de transferts réels pour
calibrer.

Principe retenu : la réputation d'un joueur est approximée par le standing
sportif de son club au moment `as_of_date` (`features.team_match_features
.standing_position`), sur l'hypothèse qu'évoluer dans une équipe qui
performe (haut de tableau) expose davantage le joueur (médias, scouts,
compétitions européennes) qu'évoluer dans une équipe en difficulté, à
niveau de jeu individuel comparable. C'est une approximation grossière
(un joueur peut être individuellement réputé dans une équipe qui souffre
collectivement), mais c'est la seule donnée disponible tant que
`staging.lineup` / `staging.player_match_stats` ne sont pas peuplées.

Formule retenue : mapping linéaire simple de la position au classement vers
un score 0-100, borné par le nombre d'équipes de la compétition (les
compétitions suivies n'ont pas toutes le même nombre d'équipes) :

    reputation_score = 100 * (n_teams - position) / (n_teams - 1)

- position = 1 (1er)         -> 100 (score maximal)
- position = n_teams (dernier) -> 0 (score minimal)
- linéaire entre les deux : pas de raison a priori de sur-pondérer le haut
  ou le bas de tableau sans donnée pour calibrer une courbe plus fine.

Cas limite `n_teams_in_competition <= 1` : le classement n'a aucun sens (il
n'y a rien à classer, ou une seule équipe). On choisit de lever `ValueError`
plutôt que de renvoyer un score neutre arbitraire (50.0) : une compétition à
0 ou 1 équipe est un signe de donnée invalide en amont (`standing.py`
mal alimenté, filtre de compétition erroné, etc.), et masquer ce genre de
problème par un fallback silencieux va à l'encontre du principe du projet
de "fail loud" sur les problèmes de qualité de donnée (cf.
`market_value/preprocessing/per90.py`, `modeling/predict_service
.InsufficientFeatureHistoryError`)."""
from __future__ import annotations


def compute_reputation_score(standing_position: int, n_teams_in_competition: int) -> float:
    """Score 0-100 de réputation, dérivé de la position au classement du
    club du joueur (`features.team_match_features.standing_position`) dans
    une compétition à `n_teams_in_competition` équipes.

    Lève `ValueError` si :
    - `n_teams_in_competition <= 1` (classement sans signification) ;
    - `standing_position` hors de `[1, n_teams_in_competition]` (donnée
      invalide)."""
    if n_teams_in_competition <= 1:
        raise ValueError(
            "n_teams_in_competition doit être > 1 pour calculer une réputation "
            f"(reçu {n_teams_in_competition}) : un classement à 0 ou 1 équipe "
            "n'a pas de sens."
        )
    if not (1 <= standing_position <= n_teams_in_competition):
        raise ValueError(
            f"standing_position ({standing_position}) hors de l'intervalle valide "
            f"[1, {n_teams_in_competition}]."
        )

    return 100.0 * (n_teams_in_competition - standing_position) / (n_teams_in_competition - 1)
