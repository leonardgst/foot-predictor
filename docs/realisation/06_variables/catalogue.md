# Catalogue des variables

> **Fichier généré** par `python -m foot_predictor.features catalogue` depuis `src/foot_predictor/features/registry.yaml`. Ne pas le modifier à la main : modifier le registre, puis régénérer (un test vérifie qu'il est à jour).

96 colonnes au jeu de données, dont 82 variables (G0 à G6), celles de G0 à G3 sont à l'horizon H1 (avant composition), celles de G4 à G6 à l'horizon H2 (avec composition, ADR-0010). Une colonne `opp_…` est la même variable pour l'adversaire, lue sur sa ligne du même match. Règle temporelle : une variable du jour J n'utilise que des matchs terminés avant le jour J.

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
- **Définition** : « rodage » avant 2015-16, « apprentissage » de 2015-16 à 2020-21, « validation » de 2021-22 à 2024-25, « scelle » ensuite (jeu du test scellé seulement, ADR-0012)
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

### `round`

- **Colonnes** : `round`
- **Définition** : journée du match selon API-FOOTBALL (« Regular Season - 12 ») ; bloc du bootstrap par (championnat, saison, journée)
- **Source** : staging.match.round
- **Horizon** : sans objet ; **disponible en live** : oui : calendrier API figé ; vide pour un match hors API
- **Paramètres** : —
- **Historique minimal** : aucun
- **Valeur manquante** : vide pour un match hors API (le bootstrap prend alors la semaine ISO)
- **Risque de fuite** : nul — identifiant de regroupement, jamais une variable

### `shots_source`

- **Colonnes** : `shots_source`
- **Définition** : source des tirs de ce match pour l'xg_proxy de l'historique (api, football_data, vide si aucune) ; même valeur pour les deux lignes du match
- **Source** : features/xg_proxy.py (select_shots, ADR-0035)
- **Horizon** : sans objet ; **disponible en live** : non : décrit les statistiques du match, connues après lui
- **Paramètres** : api_depuis = 2015
- **Historique minimal** : aucun
- **Valeur manquante** : vide si aucune source n'a de tirs pour ce match
- **Risque de fuite** : élevé — jamais une variable (connue après le match) ; sert au contrôle du changement de source après le gel

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
- **Source** : tirs de staging.team_match_stats (API, depuis 2015-16, si complets) sinon staging.team_match_stats_external (football-data), ADR-0035 ; features/params/xg_proxy.json
- **Horizon** : H1 ; **disponible en live** : oui : tirs de football-data seulement après le gel (changement de source, ADR-0035)
- **Paramètres** : demi_vie_jours = 60, 120, 240; anciennete_max_jours = 730; poids_a_priori = 3; fichier = features/params/xg_proxy.json
- **Historique minimal** : un match de championnat avec les tirs des deux équipes dans les 730 jours
- **Valeur manquante** : vide si aucun match avec tirs (D2 avant 2015-16, et en partie jusqu'en 2016-17) ; xgp_weight_h{h} = 0 le dit
- **Risque de fuite** : faible — coefficients estimés sur 2015-16 à 2020-21 seulement, avant tous les plis de validation

### `xgp_against_ewm_h{h}`

- **Colonnes** : `xgp_against_ewm_h60`, `opp_xgp_against_ewm_h60`, `xgp_against_ewm_h120`, `opp_xgp_against_ewm_h120`, `xgp_against_ewm_h240`, `opp_xgp_against_ewm_h240`
- **Définition** : comme xgp_for_ewm_h{h}, pour l'xg_proxy concédé (tirs de l'adversaire)
- **Source** : tirs de staging.team_match_stats (API, depuis 2015-16, si complets) sinon staging.team_match_stats_external (football-data), ADR-0035 ; features/params/xg_proxy.json
- **Horizon** : H1 ; **disponible en live** : oui : tirs de football-data seulement après le gel (changement de source, ADR-0035)
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
- **Horizon** : H1 ; **disponible en live** : oui : tirs de football-data seulement après le gel (changement de source, ADR-0035)
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

## G4 — Entraîneur (horizon H2)

### `coach_tenure_days`

- **Colonnes** : `coach_tenure_days`, `opp_coach_tenure_days`
- **Définition** : jours entre le premier match de la période en cours du même entraîneur dans le club (suite ininterrompue des derniers matchs de championnat terminés, entraîneur connu) et le jour du match, plafonnés à 365 ; 0 pour un entraîneur qui arrive
- **Source** : staging.team_match et staging.coach (entraîneur de la feuille de match, via la porte load_team_sheets) ; features/coach.py
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : plafond_jours = 365
- **Historique minimal** : entraîneur de la feuille de match connu (API, depuis 2016-17 ; l'ancienneté n'est fiable qu'à partir d'août 2017, censure à gauche)
- **Valeur manquante** : vide si l'entraîneur du match est inconnu (toute la période avant 2016-17, 1 à 2 % ensuite en 2019-20 et 2020-21) ou le match non joué ; un match à entraîneur inconnu sort de l'historique sans couper la période
- **Risque de fuite** : faible — matchs d'un jour strictement antérieur ; l'entraîneur du match évalué est celui de la feuille annoncée à T-60

### `coach_is_new`

- **Colonnes** : `coach_is_new`, `opp_coach_is_new`
- **Définition** : 1 si la période en cours du même entraîneur compte moins de 5 matchs de championnat avant le match, sinon 0
- **Source** : staging.team_match et staging.coach (via load_team_sheets) ; features/coach.py
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : matchs_nouvel_entraineur = 5
- **Historique minimal** : entraîneur de la feuille de match connu (depuis 2016-17 ; censure à gauche, les 5 premiers matchs observés de 2016-17 passent pour des débuts)
- **Valeur manquante** : vide comme coach_tenure_days
- **Risque de fuite** : faible — comme coach_tenure_days

## G5 — Qualité du XI (horizon H2)

### `xi_quality`

- **Colonnes** : `xi_quality`, `opp_xi_quality`
- **Définition** : moyenne des 11 titulaires de la note rétrécie vers la moyenne du poste, (M·r̄ + k·μ) / (M + k), avec r̄ la note moyenne du joueur pondérée par les minutes, M ses minutes notées, μ la note moyenne du poste, sur les matchs de championnat d'un jour strictement antérieur
- **Source** : staging.lineup, staging.player_match_stats (notes, minutes) via load_lineups ; features/xi_quality.py ; features/params/xi_quality.json
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : k_minutes_fichier = features/params/xi_quality.json; note_valide = 3, 10; minutes_valides = 1, 130
- **Historique minimal** : une note antérieure au poste (donc après 2014-15) ; rodage 2015-16, apprentissage à partir de 2016-17 (D3)
- **Valeur manquante** : vide si le onze est incomplet (moins de 11 titulaires identifiés, entrée sans identifiant ou exclue pour collision), si un titulaire n'a ni poste ni note antérieure, ou si aucune note antérieure n'existe au poste ; un joueur sans note antérieure vaut la moyenne de son poste (ADR-0013, règle 3), compté
- **Risque de fuite** : moyen — notes d'un jour strictement antérieur ; poste de la composition annoncée, jamais des statistiques du match évalué ; k estimé sur 2015-16 à 2019-20 seulement

### `xi_regulars_missing`

- **Colonnes** : `xi_regulars_missing`, `opp_xi_regulars_missing`
- **Définition** : part des habituels du club (au moins 5 débuts sur les 10 derniers matchs de l'historique du club) absents du onze du match
- **Source** : staging.lineup via load_lineups et load_team_sheets ; features/xi_quality.py
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : fenetre_matchs = 10; debuts_minimum = 5
- **Historique minimal** : 10 matchs de championnat au onze complet dans le club (depuis 2010-11)
- **Valeur manquante** : vide si le onze est incomplet ou si l'historique compte moins de 10 matchs ; un départ compte comme une absence tant que le joueur est dans la fenêtre
- **Risque de fuite** : faible — matchs d'un jour strictement antérieur, limités au club

### `xi_mean_age`

- **Colonnes** : `xi_mean_age`, `opp_xi_mean_age`
- **Définition** : âge moyen des 11 titulaires, en années, au jour du match
- **Source** : staging.player (date de naissance) et staging.lineup via load_lineups ; features/xi_quality.py
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : —
- **Historique minimal** : aucun ; onze complet et date de naissance de chacun des titulaires
- **Valeur manquante** : vide si le onze est incomplet ou si une date de naissance manque
- **Risque de fuite** : nul — la date de naissance ne dépend pas du résultat

## G6 — Stabilité du onze (horizon H2)

### `xi_overlap_prev`

- **Colonnes** : `xi_overlap_prev`, `opp_xi_overlap_prev`
- **Définition** : nombre de titulaires communs (0 à 11) avec le dernier match de championnat terminé du club, au onze complet, d'un jour strictement antérieur
- **Source** : staging.lineup via load_lineups et load_team_sheets ; features/lineup_stability.py
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : —
- **Historique minimal** : un match de championnat au onze complet dans le club (depuis 2010-11)
- **Valeur manquante** : vide si le onze est incomplet, le match non joué ou sans match antérieur (jamais 1 ni 0, rapport H.2)
- **Risque de fuite** : moyen — le match évalué n'est jamais dans l'historique ; test d'invariance à la troncature sur données réelles

### `xi_cohesion_ewm_h{h}`

- **Colonnes** : `xi_cohesion_ewm_h3`, `opp_xi_cohesion_ewm_h3`, `xi_cohesion_ewm_h5`, `opp_xi_cohesion_ewm_h5`, `xi_cohesion_ewm_h10`, `opp_xi_cohesion_ewm_h10`, `xi_cohesion_ewm_h20`, `opp_xi_cohesion_ewm_h20`, `xi_cohesion_ewm_hinf`, `opp_xi_cohesion_ewm_hinf`
- **Définition** : moyenne des s(s − 1) / 110 sur l'historique du club, avec s le nombre de titulaires communs avec chaque match antérieur, pondérée par 0,5^((rang − 1) / {h}) selon le rang du match (rang 1 = match précédent) ; demi-vie {h} matchs, inf = poids égaux ; égale la somme de la matrice cumulée des paires restreinte au onze (H.3)
- **Source** : staging.lineup via load_lineups et load_team_sheets ; features/lineup_stability.py
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : demi_vie_matchs = 3, 5, 10, 20, inf
- **Historique minimal** : un match de championnat au onze complet dans le club ; sans remise à zéro par saison, limitée au club
- **Valeur manquante** : comme xi_overlap_prev ; la demi-vie se choisit par validation interne du pli (ADR-0047, D2)
- **Risque de fuite** : moyen — comme xi_overlap_prev

### `xi_new_starters`

- **Colonnes** : `xi_new_starters`, `opp_xi_new_starters`
- **Définition** : nombre de titulaires du match qui ont moins de 3 titularisations de championnat dans le club sur les 365 jours précédents
- **Source** : staging.lineup via load_lineups et load_team_sheets ; features/lineup_stability.py
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : fenetre_jours = 365; titularisations_minimum = 3
- **Historique minimal** : un match de championnat au onze complet dans le club
- **Valeur manquante** : comme xi_overlap_prev
- **Risque de fuite** : faible — titularisations d'un jour strictement antérieur

### `xi_cohesion_reset`

- **Colonnes** : `xi_cohesion_reset`, `opp_xi_cohesion_reset`
- **Définition** : variante de diagnostic (rapport H.8) de la cohésion, avec remise à zéro par saison ; moyenne à poids égaux des s(s − 1) / 110 sur les seuls matchs du club de la même saison, d'un jour strictement antérieur
- **Source** : staging.lineup via load_lineups et load_team_sheets ; features/lineup_stability.py
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : diagnostic = ADR-0047 D2
- **Historique minimal** : un match de championnat au onze complet dans le club, de la même saison
- **Valeur manquante** : vide au premier match de la saison du club (n = 0), comme xi_overlap_prev sinon ; mesurée en diagnostic, jamais choisie sur les plis de test
- **Risque de fuite** : moyen — comme xi_overlap_prev

### `xi_cohesion_win10`

- **Colonnes** : `xi_cohesion_win10`, `opp_xi_cohesion_win10`
- **Définition** : variante de diagnostic (rapport H.8) de la cohésion, sur fenêtre ; moyenne à poids égaux des s(s − 1) / 110 sur les 10 derniers matchs de l'historique du club (tous, s'il y en a moins)
- **Source** : staging.lineup via load_lineups et load_team_sheets ; features/lineup_stability.py
- **Horizon** : H2 ; **disponible en live** : non : compositions non fournies après la fin de l'abonnement (ADR-0010, ADR-0011)
- **Paramètres** : fenetre_matchs = 10; diagnostic = ADR-0047 D2
- **Historique minimal** : un match de championnat au onze complet dans le club
- **Valeur manquante** : comme xi_overlap_prev ; mesurée en diagnostic, jamais choisie sur les plis de test
- **Risque de fuite** : moyen — comme xi_overlap_prev
