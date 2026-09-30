# ADR-0029 — Tirs et tirs cadrés chargés depuis football-data (révision partielle de l'ADR-0027)

- **Statut** : acceptée ; complétée par l'ADR-0035 (tirs d'API-FOOTBALL depuis 2015-16 quand elle est complète)
- **Date** : 2026-09-29
- **Référence** : ADR-0027 (critère de révision atteint) ; ADR-0023 (xG d'API-FOOTBALL seulement) ; ADR-0011 (live après l'abonnement) ; décision d.1 de la partie 3 ; `reports/data_quality/referentiel_2026-09-29.md`, section 6

## Contexte

Sans xG avant 2022-23 (ADR-0023), le groupe G2 du MVP s'appuie sur un **xG estimé à partir des tirs** (`xg_proxy`, décision d.1 de la partie 3). Il faut donc les tirs et les tirs cadrés de chaque équipe, pour toute la période d'apprentissage et après le gel.

Mesures de l'étape 0 (2026-09-29), matchs de championnat avant le 1er juillet 2025 :

| Source | Couverture des tirs et tirs cadrés (les deux équipes) |
|---|---|
| CSV football-data, top 5, de 2015-16 à 2024-25 | 100 %, sauf 2 matchs |
| CSV football-data, Premier League et Championship | depuis 2000-01 |
| CSV football-data, La Liga, Serie A, Ligue 1 | depuis 2005-06 (Bundesliga : 2000-01 et 2001-02, puis depuis 2006-07) |
| CSV football-data, Segunda, 2. Bundesliga, Serie B, Ligue 2 | **seulement depuis 2017-18** |
| `staging.team_match_stats` (API), top 5 | 0 % jusqu'en 2013-14, de 99,7 à 100 % depuis 2015-16 |

L'ADR-0027 avait reporté le chargement des colonnes de football-data autres que le score. Son critère de révision est atteint : une variable du MVP a besoin d'une donnée reportée.

## Options envisagées

1. **Tirs d'API-FOOTBALL** : déjà chargés, mais absents avant 2015-16 (donc pour l'amorçage des glissants), et **indisponibles en live** après la fin de l'abonnement (ADR-0011).
2. **Tirs de football-data** pour tous les matchs, les statistiques d'API-FOOTBALL servant de **contrôle** sur les matchs communs : une seule définition de 2000 à aujourd'hui, disponible en live (football-data publie les résultats avec ces colonnes).
3. **Mélange** (football-data, sinon API) : deux définitions qui se relaient selon la saison et la division, avec un risque de rupture artificielle dans les variables.

## Décision

Option 2.

- Migration **0005, additive** : `staging.team_match_stats_external` (`source`, `team_match_id`, `shots`, `shots_on_target`), une ligne par (source, équipe-match). `staging.team_match_stats` (API) ne change pas.
- `load` (`ingestion/load_external.py`) écrit, pour chaque ligne de football-data **appariée à un match API ou créée hors API**, une ligne par équipe : `HS` et `HST` à domicile, `AS` et `AST` à l'extérieur. Une valeur absente ou illisible, ou une colonne absente d'un ancien fichier, reste **vide, jamais 0**.
- Les tirs des matchs scellés sont chargés (c'est permis), mais ni comparés ni résumés (ADR-0012, ADR-0028).
- `check-referentiel` mesure, avant le scellé, la couverture de chaque source et leur recouvrement sur les matchs communs : nombre de matchs, part identique, écart moyen absolu.
- **Pas de complément par l'API** pour les quatre D2 avant 2017-18 (décision d.10d de la partie 3) : leurs valeurs restent vides, et les variables le signalent par leur poids d'information.

## Conséquences

- **Limites** :
  - les définitions diffèrent un peu selon la source (tirs contrés comptés ou non, fournisseur des données) : l'écart est mesuré, pas corrigé ;
  - « tirs non cadrés » se lit `HS − HST` ; les tirs contrés y sont compris ;
  - les quatre D2 n'ont pas de tirs avant 2017-18.
- Le `xg_proxy` (partie 3, sous-étape 3.5) lit ces colonnes par la porte `features/sources.py`.
- `load` vise la révision 0005 (`ALEMBIC_HEAD`).
- Les cotes de football-data restent non chargées (ADR-0027) ; leur chargeur viendra avec les références du protocole (partie 4).
- **Critère de révision** (écrit avant la mesure) : un recouvrement de moins de 90 % de valeurs identiques entre les deux sources sur les matchs communs, ou un écart moyen de plus d'un tir par équipe, laisserait douter de la source ; il faudrait alors revoir le choix de la source dans une nouvelle ADR.

## Constat du 2026-09-29 : critère de révision atteint dès la première mesure

Deux chargements identiques (`ops.load_run` 3 et 4, 352 s et 444 s ; seule la nouvelle table diffère du chargement 2). `check-referentiel`, section 6, matchs communs de championnat avant le scellé : **68,7 % de matchs identiques** (tirs et tirs cadrés des deux équipes), écart moyen absolu 0,38 tir et 0,13 tir cadré par équipe. Par championnat et par saison, top 5, de 2015-16 à 2024-25 :

| Cas | Écart moyen, tirs | Biais football-data − API, tirs | Biais, tirs cadrés |
|---|---|---|---|
| Premier League, La Liga, Ligue 1, toutes saisons | 0,01 à 0,20 | de −0,12 à +0,02 | ≈ 0 |
| Bundesliga, 2017-18 à 2023-24 | 0,28 à 0,75 | de −0,29 à 0 | de 0 à +0,15 |
| **Serie A, 2018-19 à 2020-21** | **1,9 à 3,8** | **de −3,7 à −1,5** | **de +0,8 à +1,0** |
| Serie A, autres saisons | 0,04 à 0,23 | ≈ 0 | ≈ 0 |

Lecture : football-data change de définition des tirs pour la Serie A de 2018-19 à 2020-21 (tirs contrés vraisemblablement exclus, tirs cadrés comptés autrement). Ce n'est pas du bruit, c'est une **rupture de série** de la source retenue, sur trois saisons de la période d'apprentissage.

**Suite retenue en attendant la relecture de l'utilisateur** (choix prudent, noté au retour de la partie 3) : la source reste football-data, comme décidé à l'étape 0 (d.1). Changer de source est une décision de l'utilisateur. L'effet de la rupture sur l'`xg_proxy` est mesuré dans `reports/variables/xg_proxy.md`, sous-étape 3.5 : l'`xg_proxy` pèse surtout les tirs cadrés, et la baisse des tirs non cadrés compense en partie leur hausse. Options à trancher : garder football-data partout ; ou prendre les tirs d'API-FOOTBALL pour la Serie A de 2018-19 à 2020-21, voire pour tous les matchs où l'API les a (depuis 2015-16).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
