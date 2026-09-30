# ADR-0032 — Glissants (G2) : moyennes à décroissance en jours, retrait vers le championnat ; `xg_proxy` à la place de l'xG avant 2022-23

- **Statut** : acceptée ; complétée par l'ADR-0035 (source des tirs, `xg_proxy` réestimé)
- **Date** : 2026-09-29
- **Référence** : rapport de cadrage, H.4, I.3 (G2), I.5, I.8 ; ADR-0012, ADR-0013 (xG dans le MVP), ADR-0023 (pas d'Understat), ADR-0029 (tirs de football-data) ; décisions d.1, d.3 et d.10d de la partie 3 ; `reports/variables/xg_proxy.md`

## Contexte

Le groupe G2 du MVP porte l'attaque et la défense des équipes : l'xG pour et contre, lissé dans le temps (ADR-0013). Mais l'xG d'API-FOOTBALL est absent de 2010-11 à 2021-22, et Understat est écarté (ADR-0023). Les tirs de football-data couvrent le top 5 à 99,99 % depuis 2015-16 (ADR-0029). Il faut aussi une règle de lissage qui ne remette pas tout à zéro à chaque saison (rapport H.4) et qui ne remplisse jamais un manque par 0 (rapport I.8).

## Options envisagées

Pour l'attaque et la défense (question laissée ouverte par l'ADR-0023) :

1. **Buts seuls.**
2. **Buts et `xg_proxy`**, un xG estimé à partir des tirs.
3. **xG d'API-FOOTBALL** là où il existe : la période d'apprentissage serait presque vide. Écartée d'office.

Pour le lissage :

1. **Fenêtre de n matchs**, remise à zéro chaque saison (ancien code).
2. **Décroissance par nombre de matchs.**
3. **Décroissance par nombre de jours**, sans remise à zéro, avec une ancienneté maximale et un retrait vers la moyenne du championnat.

## Décision

Option 2 pour le contenu (défaut de d.1, seuil de 95 % atteint), option 3 pour le lissage (d.3).

- **`xg_proxy`** (`features/xg_proxy.py`) : xg_proxy = a · tirs cadrés + b · tirs non cadrés, tirs de football-data.
  - a et b sont estimés **une seule fois**, par moindres carrés sans constante et **à coefficients positifs ou nuls**, sur 2015-16 à 2020-21 (avant tous les plis de validation), puis figés dans `features/params/xg_proxy.json`.
  - La contrainte de positivité est un choix de principe, fait avant de regarder la qualité (un xG est une somme de probabilités). Sans elle, b sort à −0,013 ; avec elle, b = 0. Résultat : **xg_proxy = 0,3033 · tirs cadrés**.
  - Pour chaque équipe, un même match donne son `xg_proxy` pour (ses tirs) et contre (ceux de l'adversaire). Un tir manquant donne une valeur vide.
  - L'xG d'API-FOOTBALL est chargé mais n'est **pas** une variable du MVP (couverture inégale) : c'est un candidat pour la version intermédiaire.
- **Glissants** (`features/rolling.py`), pour les buts marqués, les buts encaissés, l'`xg_proxy` pour et l'`xg_proxy` contre :
  - matchs de **championnat** de l'équipe dans les 10 championnats, barrages compris : couverture homogène depuis 2000, contrairement aux coupes ;
  - poids w = 0,5^(jours/h), sur les matchs terminés **avant le jour J** et vieux d'au plus **730 jours** ;
  - moyenne retirée vers μ, la moyenne par équipe-match du championnat du match sur les 730 jours avant J, avec un poids a priori k = 3 : x̂ = (Σ w·x + k·μ) / (Σ w + k) ;
  - **sans remise à zéro** à chaque saison ; la décroissance en jours fait compter la pause d'été ;
  - la **somme des poids** est une variable à part (`goals_weight_h{h}`, `xgp_weight_h{h}`), avec l'ancienneté du dernier match ;
  - sans historique, la valeur reste **vide** et le poids vaut 0, jamais 0 ni μ par défaut ;
  - trois demi-vies candidates (60, 120 et 240 jours) sont calculées ; le choix se fait en partie 4, par validation interne dans chaque pli, jamais ici.
- Les quatre D2 sans tirs avant 2017-18 (Segunda, 2. Bundesliga, Serie B, Ligue 2) gardent un `xg_proxy` vide sur cette période (d.10d).

## Conséquences

- Qualité, contrôlée sur 2022-23 à 2024-25 contre l'xG d'API-FOOTBALL : corrélation 0,685 par équipe et par match (de 0,631 en Serie A à 0,725 en Bundesliga), écart moyen absolu 0,495, biais −0,05.
- **Rupture de série de la Serie A** (tirs de football-data de 2018-19 à 2020-21, ADR-0029) : les mêmes coefficients appliqués aux tirs de football-data et à ceux de l'API diffèrent en moyenne de **+0,265 xG par équipe et par match**. L'`xg_proxy` de la Serie A est donc surestimé d'environ 20 % sur ces trois saisons. Point laissé à la décision de l'utilisateur (retour de la partie 3).
- Réglage reproductible : `python -m foot_predictor.features.xg_proxy_estimation`.
- **Critère de révision** : un `xg_proxy` qui n'apporte rien au-delà des buts en partie 4 (ablation), ou une source d'xG historique gratuite et légale ; dans ce cas, une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
