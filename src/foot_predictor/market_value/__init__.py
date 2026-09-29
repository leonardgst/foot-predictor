"""Score de valeur marchande (MVS) maison : GELÉ (ADR-0013).

Code et tests conservés, sans évolution, hors du MVP et de la version intermédiaire.
Possible exercice non supervisé en version avancée. Les tables
`features.player_market_value_score` et `features.player_style_profile` restent en
place, sans être alimentées. `hdbscan` n'est plus une dépendance : le regroupement
utilise son repli existant (mélange gaussien), voir `clustering/build_clusters.py`.
"""
