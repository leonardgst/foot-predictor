"""Composante Potentiel du MVS (cf. recap projet, section 4) : à dire
d'expert, PAS de calibration supervisée possible (aucun dataset de
transferts réels exploitable -- même limite que pour le MVS dans son
ensemble).

Principe retenu : le potentiel mesure la marge de progression de VALEUR
restante, pas le niveau de jeu actuel (ça, c'est `performance_score`). Un
jeune joueur a beaucoup de marge devant lui (il peut encore progresser
fortement avant d'atteindre son pic) ; un joueur déjà à son pic n'a plus
grand-chose à gagner en valeur par la seule progression sportive ; un
joueur post-pic est plus susceptible de perdre de la valeur que d'en
gagner, donc son potentiel tend vers 0 (jamais négatif : le score MVS
reste sur l'échelle 0-100, une valeur négative n'aurait pas de sens ici).

Courbe retenue (linéaire par morceaux, cf. constantes ci-dessous) :

    score
    100 |----.
        |     \\
        |      \\
   PEAK |       \\.________.
        |                   \\
        |                    \\
      0 |                     \\________________
        +----+----+---------+---+----+---------+--- âge
             YOUNG          PEAK_START
                             PEAK_END      DECLINE

- âge <= YOUNG_AGE_ANCHOR           : score plafonné à MAX_SCORE (marge de
  progression maximale, joueur encore loin de son pic de carrière).
- YOUNG_AGE_ANCHOR -> PEAK_AGE_START : décroissance linéaire de MAX_SCORE
  vers PEAK_SCORE (la marge se réduit à mesure que le joueur se rapproche
  de son pic).
- PEAK_AGE_START -> PEAK_AGE_END    : plateau à PEAK_SCORE (le joueur est
  dans sa fenêtre de pic sportif habituelle en football pro -- 26-27 ans,
  cf. littérature courbes de valeur marchande -- il lui reste peu de marge
  de progression, mais pas nulle : un pic de forme, un transfert vers un
  plus grand club, etc. peuvent encore faire progresser sa valeur).
- PEAK_AGE_END -> DECLINE_AGE_ANCHOR : décroissance linéaire de PEAK_SCORE
  vers MIN_SCORE (post-pic, la valeur est structurellement plus susceptible
  de baisser que de monter).
- âge >= DECLINE_AGE_ANCHOR         : score plancher à MIN_SCORE (fin de
  carrière proche, potentiel de progression de valeur considéré comme nul).

Les âges d'ancrage sont des constantes nommées (pas de magie dans la
formule) pour pouvoir être ajustés facilement si besoin, sans avoir à
redériver le calcul.
"""
from __future__ import annotations

import datetime as dt

DAYS_PER_YEAR = 365.25  # approximation usuelle, suffisante ici (pas besoin
# d'une précision à la journée près pour un score "à dire d'expert")

# Ancrages d'âge (années), cf. schéma dans le docstring du module.
YOUNG_AGE_ANCHOR = 17.0
PEAK_AGE_START = 26.0
PEAK_AGE_END = 27.0
DECLINE_AGE_ANCHOR = 32.0

# Bornes du score (échelle 0-100, cf. `features.player_market_value_score`).
MAX_SCORE = 100.0
PEAK_SCORE = 20.0
MIN_SCORE = 0.0


def _age_in_years(birth_date: dt.date, as_of_date: dt.date) -> float:
    if as_of_date < birth_date:
        raise ValueError(
            f"as_of_date ({as_of_date}) est antérieure à birth_date ({birth_date}) : "
            "impossible de calculer un âge."
        )
    return (as_of_date - birth_date).days / DAYS_PER_YEAR


def _interpolate(age: float, age_start: float, score_start: float, age_end: float, score_end: float) -> float:
    fraction = (age - age_start) / (age_end - age_start)
    return score_start + fraction * (score_end - score_start)


def compute_potential_score(birth_date: dt.date, as_of_date: dt.date) -> float:
    """Score 0-100 de marge de progression de valeur restante, dérivé de
    l'âge du joueur à `as_of_date` (anti-fuite : n'utilise que des données
    connues à cette date, cf. section 4 du recap -- "Cadrage actés pour le
    MVS").

    Lève `ValueError` si `as_of_date` est antérieure à `birth_date` (donnée
    invalide, on ne renvoie pas un score fantaisiste)."""
    age = _age_in_years(birth_date, as_of_date)

    if age <= YOUNG_AGE_ANCHOR:
        return MAX_SCORE
    if age <= PEAK_AGE_START:
        return _interpolate(age, YOUNG_AGE_ANCHOR, MAX_SCORE, PEAK_AGE_START, PEAK_SCORE)
    if age <= PEAK_AGE_END:
        return PEAK_SCORE
    if age <= DECLINE_AGE_ANCHOR:
        return _interpolate(age, PEAK_AGE_END, PEAK_SCORE, DECLINE_AGE_ANCHOR, MIN_SCORE)
    return MIN_SCORE
