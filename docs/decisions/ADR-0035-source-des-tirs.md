# ADR-0035 — Source des tirs de l'`xg_proxy` : API-FOOTBALL depuis 2015-16 quand elle est complète, sinon football-data

- **Statut** : acceptée
- **Date** : 2026-09-30
- **Référence** : complète l'ADR-0029 (tirs de football-data, critère de révision atteint) et l'ADR-0032 (`xg_proxy`) ; ADR-0011 (live après l'abonnement) ; décisions 1 et 7 de la partie 4 ; `reports/variables/xg_proxy.md`

## Contexte

L'ADR-0029 a retenu les tirs de football-data pour tous les matchs, les tirs d'API-FOOTBALL servant de contrôle. Son critère de révision est atteint dès la première mesure : football-data change de définition des tirs en **Serie A de 2018-19 à 2020-21** (3,7 tirs de moins et 0,8 tir cadré de plus par équipe que l'API), et s'écarte de l'API en Bundesliga. Effet sur l'`xg_proxy` de la Serie A sur ces trois saisons : **+0,27 xG par équipe et par match** (ADR-0032). La question a été laissée à l'utilisateur au retour de la partie 3. Réponse (décision 1 de la partie 4) : prendre les tirs de l'API là où elle les a.

Couverture mesurée le 2026-09-30 (matchs de championnat terminés, avant le scellé), part des matchs où l'API a les quatre valeurs (tirs et tirs cadrés des deux équipes) :

| Saison | Top 5 | 2. Bundesliga | Ligue 2 | Serie B | Segunda |
|---|---|---|---|---|---|
| 2014-15 et avant | de 0 à 4,5 % | 0 à 8 % | 0 à 5 % | 0 % | 0 % |
| 2015-16 | 99,7 à 100 % | 100 % | 15,8 % | 0 % | 0 % |
| 2016-17 | 99,7 à 100 % | 100 % | 75,8 % | 98,1 % | 99,8 % |
| 2017-18 et après | 99,7 à 100 % | 99,7 à 100 % | 99,4 à 100 % | 94,2 à 100 % | 95,1 à 100 % |

## Options envisagées

1. **Garder football-data partout** (ADR-0029) : une seule définition en live, mais une rupture de série connue sur trois saisons d'apprentissage de la Serie A.
2. **API pour la seule Serie A de 2018-19 à 2020-21** : correction minimale, mais l'écart de la Bundesliga reste.
3. **API pour tout match joué depuis 2015-16 où elle a les quatre valeurs, sinon football-data** : une définition homogène sur toute la période d'apprentissage et de validation ; deux sources qui se relaient avant 2015-16 et après le gel.

## Décision

Option 3 (décision 1 de la partie 4).

- **Règle, par match** (`features/xg_proxy.py`, `select_shots`) : pour un match joué à partir de **2015-16** (`API_SHOTS_FROM`), si l'API a les tirs et les tirs cadrés **des deux équipes**, les quatre valeurs viennent de l'API ; sinon, de football-data, valeurs vides comprises. Jamais une équipe d'une source et l'autre de l'autre. Aucune valeur n'est inventée.
- **Top 5 et D2** : la règle vaut pour les 10 championnats. Elle revient en partie sur la décision d.10d de la partie 3 (« pas de tirs API pour les D2 ») : l'API remplit la 2. Bundesliga dès 2015-16 et les autres D2 en grande partie en 2016-17. Avant 2015-16, les D2 restent sans tirs.
- **`shots_source`** : colonne d'identification du jeu (`api`, `football_data`, vide si aucune source), même valeur pour les deux lignes d'un match. Elle décrit les statistiques du match, connues **après** lui : ce n'est **jamais** une variable du modèle.
- **`xg_proxy` réestimé** avec les mêmes règles (2015-16 à 2020-21, moindres carrés sans constante, coefficients positifs ou nuls, puis figé) : **xg_proxy = 0,3076 · tirs cadrés** (b = 0 ; estimation libre : 0,3312 et −0,0156). Ancienne valeur : 0,3033 avec les seuls tirs de football-data.
- **`round`** : colonne d'identification ajoutée au jeu (journée d'API-FOOTBALL), pour les blocs du bootstrap (décision 7). Vide pour un match hors API.
- Nouveau jeu : **`ds-2026-09-30-ba2b91f7`** (196 098 lignes, deux `build` aux sha256 identiques, invariance à la date de coupe exacte au 2019-01-01 et au 2023-03-01).

## Conséquences

- Part des matchs de championnat par source retenue : top 5, 99,9 % API sur 2015-16 à 2020-21 et 100 % sur 2021-22 à 2024-25 ; D2, 88,5 % API sur 2015-16 à 2020-21 (10,9 % sans tirs) et 99,9 % ensuite. Valeurs vides des glissants d'`xg_proxy` : 30,1 % des lignes (32,3 % avant), l'écart venant des D2 de 2015-16 et 2016-17.
- **Risque après le gel** (écrit ici, contrôlé en partie 5) : les matchs joués après le 22 octobre 2026 n'auront que les tirs de football-data (ADR-0011). Sur les matchs communs du top 5 de 2015-16 à 2024-25, les deux sources ne coïncident exactement que sur **72,0 %** des matchs (68,7 % sur la population plus large mesurée par l'ADR-0029) : 90,9 % en Premier League, 84,4 % en Liga, 80,9 % en Ligue 1, 56,2 % en Serie A, 42,1 % en Bundesliga. En `xg_proxy`, l'écart football-data − API reste faible hors rupture : biais +0,020 et écart moyen absolu 0,035 par équipe et par match, au plus +0,081 en Serie A (rupture comprise). Sur 2022-23 à 2024-25, l'`xg_proxy` calculé avec les seuls tirs de football-data garde la même qualité contre l'xG API (corrélation 0,685 contre 0,687). La partie 5 mesurera, sur les saisons de développement, l'effet sur les prédictions d'un historique dont la fin vient de football-data.
- `load` n'a pas changé : les tirs de l'API étaient déjà dans `staging.team_match_stats`.
- Phase B de la partie 3 (3.11) : la comparaison des lignes d'avant le 1er juillet 2025 se fait avec **`ds-2026-09-30-ba2b91f7`**, et non plus `ds-2026-09-29-83d28f3b`.
- **Critère de révision** : en partie 5, un écart de prédiction (log-loss du total) significatif entre un historique « API » et un historique « football-data » sur les saisons de développement ; il faudrait alors recalibrer les tirs de football-data sur ceux de l'API, par championnat, dans une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
