# Catalogue des variables

> **Fichier généré** par `python -m foot_predictor.features catalogue` depuis `src/foot_predictor/features/registry.yaml`. Ne pas le modifier à la main : modifier le registre, puis régénérer (un test vérifie qu'il est à jour).

66 colonnes au jeu de données, dont 54 variables (G0 à G3), toutes à l'horizon H1 (avant composition, ADR-0010). Une colonne `opp_…` est la même variable pour l'adversaire, lue sur sa ligne du même match. Règle temporelle : une variable du jour J n'utilise que des matchs terminés avant le jour J.

## Identifiants et découpage

### `match_id`

- **Colonnes** : `match_id`
- **Définition** : identifiant interne du match (staging.match.id)
- **Source** : staging.match
- **Horizon** : sans objet ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — identifiant, jamais utilisé comme variable

### `team_id`

- **Colonnes** : `team_id`, `opp_team_id`
- **Définition** : équipe de la ligne (et son adversaire, opp_team_id)
- **Source** : staging.team_match
- **Horizon** : sans objet ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — identifiant, jamais utilisé comme variable

### `match_date`

- **Colonnes** : `match_date`
- **Définition** : coup d'envoi UTC (minuit UTC pour un match hors API)
- **Source** : staging.match.match_date
- **Horizon** : sans objet ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — sert au découpage temporel et au scellé

### `match_day`

- **Colonnes** : `match_day`
- **Définition** : date UTC du match, le « jour J » de la règle temporelle
- **Source** : staging.match.match_date
- **Horizon** : sans objet ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — toutes les variables n'utilisent que des matchs de jours antérieurs

### `competition_id`

- **Colonnes** : `competition_id`
- **Définition** : identifiant interne du championnat
- **Source** : staging.match
- **Horizon** : sans objet ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — identifiant ; le championnat comme variable est api_league_id (G0)

### `country`

- **Colonnes** : `country`
- **Définition** : pays du championnat (échelle de l'Elo)
- **Source** : staging.competition
- **Horizon** : sans objet ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — identifiant de regroupement

### `division_level`

- **Colonnes** : `division_level`
- **Définition** : 1 pour une D1, 2 pour une D2
- **Source** : features/leagues.py
- **Horizon** : sans objet ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — identifiant de regroupement

### `phase`

- **Colonnes** : `phase`
- **Définition** : « rodage » avant 2015-16, « apprentissage » de 2015-16 à 2020-21, « validation » de 2021-22 à 2024-25 (ADR-0012)
- **Source** : season_year
- **Horizon** : sans objet ; **disponible en live** : oui
- **Paramètres** : apprentissage_depuis = 2015; validation_depuis = 2021
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — découpage fixé par l'ADR-0012, pas par les données

### `eval_population`

- **Colonnes** : `eval_population`
- **Définition** : vrai pour un match de championnat du top 5 (population d'évaluation, ADR-0012)
- **Source** : features/leagues.py
- **Horizon** : sans objet ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — définie par l'ADR-0012

## Cible (jamais une variable)

### `goals_for`

- **Colonnes** : `goals_for`
- **Définition** : buts marqués par l'équipe au temps réglementaire (ADR-0009)
- **Source** : staging.match.home_goals_90 / away_goals_90
- **Horizon** : sans objet ; **disponible en live** : non : c'est le résultat à prédire
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : ligne absente du jeu (match sans score)
- **Risque de fuite** : élevé — jamais une variable ; les tests vérifient qu'aucune variable ne change si on la modifie

### `goals_against`

- **Colonnes** : `goals_against`
- **Définition** : buts encaissés au temps réglementaire (la cible de la ligne de l'adversaire)
- **Source** : staging.match.home_goals_90 / away_goals_90
- **Horizon** : sans objet ; **disponible en live** : non : c'est le résultat à prédire
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : ligne absente du jeu (match sans score)
- **Risque de fuite** : élevé — jamais une variable ; sert à l'évaluation au niveau du match

## G0 — Contexte

### `is_home`

- **Colonnes** : `is_home`
- **Définition** : vrai si l'équipe joue à domicile
- **Source** : staging.team_match.is_home
- **Horizon** : H1 ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — connu à l'avance (calendrier)

### `api_league_id`

- **Colonnes** : `api_league_id`
- **Définition** : championnat (identifiant de ligue API-FOOTBALL), pour des effets fixes
- **Source** : staging.competition.api_league_id
- **Horizon** : H1 ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — connu à l'avance

### `season_year`

- **Colonnes** : `season_year`
- **Définition** : année de début de la saison (2024 pour 2024-25)
- **Source** : staging.season.year
- **Horizon** : H1 ; **disponible en live** : oui
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — connu à l'avance ; une tendance ajustée dans le pli seulement (partie 4)

### `behind_closed_doors`

- **Colonnes** : `behind_closed_doors`
- **Définition** : 1 si le match est dans une période sûre de huis clos de son championnat, 0 sinon (périodes incertaines comprises)
- **Source** : features/huis_clos.yaml
- **Horizon** : H1 ; **disponible en live** : oui : 0 hors période documentée
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide (0 hors période sûre ; les périodes incertaines sont listées dans le YAML)
- **Risque de fuite** : nul — décision publique connue avant le match

## G1 — Force globale (Elo)

### `elo_pre`

- **Colonnes** : `elo_pre`, `opp_elo_pre`
- **Définition** : note Elo de l'équipe avant le match, échelle nationale, mise à jour par jour (features/elo.py)
- **Source** : staging.match (championnats des échelles), features/params/elo.json
- **Horizon** : H1 ; **disponible en live** : oui : résultats de football-data
- **Paramètres** : fichier = features/params/elo.json
- **Historique minimal** : aucun (note d'entrée à la première apparition)
- **Valeur manquante** : jamais vide ; elo_matches dit combien de matchs la fondent
- **Risque de fuite** : faible — note d'avant-match, variations d'un jour appliquées à la fin du jour (test du même jour)

### `elo_diff`

- **Colonnes** : `elo_diff`
- **Définition** : elo_pre − opp_elo_pre, sans l'avantage du terrain (porté par is_home)
- **Source** : features/elo.py
- **Horizon** : H1 ; **disponible en live** : oui : résultats de football-data
- **Paramètres** : fichier = features/params/elo.json
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : faible — comme elo_pre

### `elo_matches`

- **Colonnes** : `elo_matches`, `opp_elo_matches`
- **Définition** : nombre de matchs d'échelle joués par l'équipe avant le match, depuis 2000-01
- **Source** : features/elo.py
- **Horizon** : H1 ; **disponible en live** : oui : résultats de football-data
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide (0 pour une première apparition)
- **Risque de fuite** : nul — compte des matchs antérieurs seulement

## G2 — Attaque et défense (glissants)

### `goals_for_ewm_h{h}`

- **Colonnes** : `goals_for_ewm_h60`, `opp_goals_for_ewm_h60`, `goals_for_ewm_h120`, `opp_goals_for_ewm_h120`, `goals_for_ewm_h240`, `opp_goals_for_ewm_h240`
- **Définition** : moyenne des buts marqués en championnat, poids 0,5^(jours/h), au plus 730 jours, retirée vers la moyenne du championnat avec un poids a priori de 3 matchs
- **Source** : staging.match (championnats des échelles), features/rolling.py
- **Horizon** : H1 ; **disponible en live** : oui : résultats de football-data
- **Paramètres** : demi_vie_jours = 60, 120, 240; anciennete_max_jours = 730; poids_a_priori = 3
- **Historique minimal** : un match de championnat dans les 730 jours
- **Valeur manquante** : vide si aucun match ; goals_weight_h{h} = 0 le dit
- **Risque de fuite** : faible — matchs des jours antérieurs seulement (test « modifier le match m ne change pas sa ligne »)

### `goals_against_ewm_h{h}`

- **Colonnes** : `goals_against_ewm_h60`, `opp_goals_against_ewm_h60`, `goals_against_ewm_h120`, `opp_goals_against_ewm_h120`, `goals_against_ewm_h240`, `opp_goals_against_ewm_h240`
- **Définition** : comme goals_for_ewm_h{h}, pour les buts encaissés
- **Source** : staging.match, features/rolling.py
- **Horizon** : H1 ; **disponible en live** : oui : résultats de football-data
- **Paramètres** : demi_vie_jours = 60, 120, 240; anciennete_max_jours = 730; poids_a_priori = 3
- **Historique minimal** : un match de championnat dans les 730 jours
- **Valeur manquante** : vide si aucun match ; goals_weight_h{h} = 0 le dit
- **Risque de fuite** : faible — comme goals_for_ewm_h{h}

### `xgp_for_ewm_h{h}`

- **Colonnes** : `xgp_for_ewm_h60`, `opp_xgp_for_ewm_h60`, `xgp_for_ewm_h120`, `opp_xgp_for_ewm_h120`, `xgp_for_ewm_h240`, `opp_xgp_for_ewm_h240`
- **Définition** : comme goals_for_ewm_h{h}, pour l'xg_proxy de l'équipe (a · tirs cadrés + b · tirs non cadrés)
- **Source** : staging.team_match_stats_external (football-data), features/params/xg_proxy.json
- **Horizon** : H1 ; **disponible en live** : oui : tirs de football-data
- **Paramètres** : demi_vie_jours = 60, 120, 240; anciennete_max_jours = 730; poids_a_priori = 3; fichier = features/params/xg_proxy.json
- **Historique minimal** : un match de championnat avec les tirs des deux équipes dans les 730 jours
- **Valeur manquante** : vide si aucun match avec tirs (4 D2 avant 2017-18) ; xgp_weight_h{h} = 0 le dit
- **Risque de fuite** : faible — coefficients estimés sur 2015-16 à 2020-21 seulement, avant tous les plis de validation

### `xgp_against_ewm_h{h}`

- **Colonnes** : `xgp_against_ewm_h60`, `opp_xgp_against_ewm_h60`, `xgp_against_ewm_h120`, `opp_xgp_against_ewm_h120`, `xgp_against_ewm_h240`, `opp_xgp_against_ewm_h240`
- **Définition** : comme xgp_for_ewm_h{h}, pour l'xg_proxy concédé (tirs de l'adversaire)
- **Source** : staging.team_match_stats_external (football-data), features/params/xg_proxy.json
- **Horizon** : H1 ; **disponible en live** : oui : tirs de football-data
- **Paramètres** : demi_vie_jours = 60, 120, 240; anciennete_max_jours = 730; poids_a_priori = 3; fichier = features/params/xg_proxy.json
- **Historique minimal** : un match de championnat avec les tirs des deux équipes dans les 730 jours
- **Valeur manquante** : vide si aucun match avec tirs ; xgp_weight_h{h} = 0 le dit
- **Risque de fuite** : faible — comme xgp_for_ewm_h{h}

### `goals_weight_h{h}`

- **Colonnes** : `goals_weight_h60`, `opp_goals_weight_h60`, `goals_weight_h120`, `opp_goals_weight_h120`, `goals_weight_h240`, `opp_goals_weight_h240`
- **Définition** : somme des poids 0,5^(jours/h) des matchs de championnat retenus (quantité d'information des moyennes de buts)
- **Source** : features/rolling.py
- **Horizon** : H1 ; **disponible en live** : oui : résultats de football-data
- **Paramètres** : demi_vie_jours = 60, 120, 240; anciennete_max_jours = 730
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide (0 sans historique)
- **Risque de fuite** : faible — comme goals_for_ewm_h{h}

### `xgp_weight_h{h}`

- **Colonnes** : `xgp_weight_h60`, `opp_xgp_weight_h60`, `xgp_weight_h120`, `opp_xgp_weight_h120`, `xgp_weight_h240`, `opp_xgp_weight_h240`
- **Définition** : somme des poids des matchs de championnat retenus dont les tirs des deux équipes sont connus
- **Source** : features/rolling.py
- **Horizon** : H1 ; **disponible en live** : oui : tirs de football-data
- **Paramètres** : demi_vie_jours = 60, 120, 240; anciennete_max_jours = 730
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide (0 sans historique)
- **Risque de fuite** : faible — comme xgp_for_ewm_h{h}

### `days_since_last_league_match`

- **Colonnes** : `days_since_last_league_match`, `opp_days_since_last_league_match`
- **Définition** : jours depuis le dernier match de championnat retenu (au plus 730)
- **Source** : features/rolling.py
- **Horizon** : H1 ; **disponible en live** : oui : résultats de football-data
- **Paramètres** : anciennete_max_jours = 730
- **Historique minimal** : un match de championnat dans les 730 jours
- **Valeur manquante** : vide au-delà de 730 jours ou sans historique
- **Risque de fuite** : nul — matchs des jours antérieurs seulement

## G3 — Calendrier (rejeu seulement)

### `rest_days`

- **Colonnes** : `rest_days`, `opp_rest_days`
- **Définition** : jours depuis le dernier match terminé de l'équipe, toutes compétitions présentes dans staging
- **Source** : staging.match (championnats et coupes), features/rest.py
- **Horizon** : H1 ; **disponible en live** : non : aucune source gratuite ne couvre les coupes après l'abonnement (ADR-0011)
- **Paramètres** : —
- **Historique minimal** : un match antérieur
- **Valeur manquante** : vide sans match antérieur ; rest_reliable dit si les coupes sont couvertes
- **Risque de fuite** : nul — rétrospectif seulement, jamais la date du prochain match

### `matches_last_14d`

- **Colonnes** : `matches_last_14d`, `opp_matches_last_14d`
- **Définition** : nombre de matchs terminés de l'équipe du jour J − 14 au jour J − 1, toutes compétitions
- **Source** : features/rest.py
- **Horizon** : H1 ; **disponible en live** : non : coupes non couvertes après l'abonnement
- **Paramètres** : fenetre_jours = 14
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide (compte ; rest_reliable dit si les coupes sont couvertes)
- **Risque de fuite** : nul — rétrospectif seulement

### `european_match_last_4d`

- **Colonnes** : `european_match_last_4d`, `opp_european_match_last_4d`
- **Définition** : vrai si l'équipe a joué un match de coupe d'Europe du jour J − 4 au jour J − 1
- **Source** : features/rest.py
- **Horizon** : H1 ; **disponible en live** : non : coupes non couvertes après l'abonnement
- **Paramètres** : fenetre_jours = 4
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide (faux ; rest_reliable dit si les coupes sont couvertes)
- **Risque de fuite** : nul — rétrospectif seulement

### `rest_reliable`

- **Colonnes** : `rest_reliable`
- **Définition** : vrai si toutes les coupes du pays sont dans staging cette saison (Angleterre, Allemagne, France depuis 2015-16 ; Italie depuis 2016-17 ; Espagne depuis 2018-19)
- **Source** : features/leagues.py (mesure 4 de la partie 3)
- **Horizon** : H1 ; **disponible en live** : non : coupes non couvertes après l'abonnement
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : jamais vide
- **Risque de fuite** : nul — fixé par la couverture des données, pas par les résultats
