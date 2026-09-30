# ADR-0037 — Protocole d'évaluation et règle de décision, pré-enregistrés avant toute évaluation de modèle

- **Statut** : acceptée
- **Date** : 2026-09-30
- **Référence** : ADR-0009 (cible, métriques), ADR-0012 (plis, scellé), ADR-0028 (porte), ADR-0036 (marché) ; rapport de cadrage, C.2, E.1, I.5, I.6, I.7, I.8 ; décisions 5 à 9 de la partie 4 ; tag **`protocole-v1`**

## Contexte

Le rapport (I.7) exige une **règle de décision écrite avant l'expérience** : sans elle, on choisit après coup le critère qui arrange, et l'on multiplie les comparaisons jusqu'à trouver un gain. Cette ADR fixe le protocole complet et la règle, **avant toute évaluation d'un modèle** : à la date de sa fusion, seul le code du protocole existe (PR de 4.3, tests sur données synthétiques) et aucune métrique n'a été calculée sur les plis, pas même celles des références B0, B1 et du marché (4.5, après cette ADR). Elle ne se modifie plus ensuite ; le tag `protocole-v1` marque le commit.

## Options envisagées

1. **Règle de la proposition de la partie 4, telle quelle.**
2. **La même, précisée** là où elle laissait un choix de calcul ouvert (calibration poolée ou par pli, départage, cas d'un gain négatif significatif, hyperparamètres, population d'apprentissage).
3. **Une correction pour comparaisons multiples** (Bonferroni, Holm) : trop conservatrice pour des comparaisons emboîtées et ordonnées ; le nombre d'essais est publié à la place (index des expériences).

## Décision

Option 2. Tout ce qui suit est **figé**.

### Données et plis

- Jeu de données versionné (ADR-0030), lu par la porte `features/sources.load_dataset` ; version en vigueur au 2026-09-30 : `ds-2026-09-30-ba2b91f7` (ADR-0035). Chaque rapport d'expérience écrit la version et le sha256 du manifeste.
- **Population d'évaluation** : matchs de championnat (saison régulière) du top 5, exclusions de l'ADR-0009. Unité d'évaluation : le match.
- **4 plis à fenêtre croissante** : apprentissage sur les lignes (match, équipe) de 2015-16 à s − 1, test sur la saison s ∈ {2021-22, 2022-23, 2023-24, 2024-25}. Rodage (avant 2015-16) : historique des variables seulement.
- **Hyperparamètres** (demi-vie de G2 parmi 60, 120 et 240 jours, force de régularisation, fenêtre de B1) : **validation interne** du pli s, apprentissage sur 2015-16 à s − 2, mesure sur s − 1, **critère : log-loss du total sur les matchs du top 5 de s − 1** ; puis réajustement du candidat retenu sur 2015-16 à s − 1. La saison s n'est jamais lue pour choisir.
- **Population d'apprentissage** : `top5` ou `top5_d2`, comparées par la **règle de décision** (B = `top5_d2`, A = `top5`), et non par la validation interne ; les autres championnats n'ont pas de variables.
- **Dans le pli** : imputation (s'il y en a une), standardisation et toute étape ajustable apprennent sur les seules lignes d'apprentissage du pli.
- **Aucun remplissage silencieux** : une ligne d'apprentissage à valeur manquante dans une variable du modèle est exclue et comptée ; un match de test sans toutes ses variables n'a pas de prédiction.
- **Mêmes matchs** : chaque comparaison se fait sur l'intersection des matchs prédits par tous les modèles de l'expérience ; le nombre de matchs écartés est publié par pli.
- **Scellé** : aucune saison de test ≥ 2025-26 ; l'exécuteur et la porte refusent les matchs scellés ; `--sealed-test` est réservé à 4.16.

### Métriques (ADR-0009)

| Rôle | Métrique |
|---|---|
| Principale (décision) | log-loss du total : moyenne de −ln P̂(T = t), T replié sur 0..9 et « 10 et plus » |
| Secondaires | RPS du total (0 à 6 et « 7 et plus », somme des carrés des écarts de fonctions de répartition, divisée par 7) ; Brier de P(T > 2,5) |
| Diagnostics | calibration de P(T ≥ 3) par décile (classes d'effectifs égaux : tableau, écart absolu moyen, pente et ordonnée d'une régression logistique sur logit(p)) ; PIT randomisé ; couverture de [q10 ; q90] contre couverture annoncée ; log-loss par équipe ; log-loss du score exact ; Brier du 1N2 ; calibration de P(T = 0), P(T = 1), P(T = 2) ; log-loss par tranche de journées (1-5, 6-10, 11-19, 20 et plus) |
| Descriptives | MAE et RMSE de E[T] : jamais pour sélectionner |

Le **marché** (ADR-0036) n'est évalué que sur l'événement plus/moins 2,5 (Brier et log-loss binaire), sur les matchs de l'intersection qui ont une cote.

### Inférence

- Écart apparié match par match, d = perte(A) − perte(B) (positif : B meilleur).
- **Bootstrap par blocs** : bloc = (championnat, saison, journée `round`) ; à défaut de `round`, (championnat, semaine ISO). Rééchantillonnage des blocs **stratifié par pli**, calcul par sommes par bloc ; **10 000** rééchantillonnages ; **graine 20260930** (écrite dans chaque fichier d'expérience) ; intervalle à 95 % par percentiles 2,5 et 97,5.
- **Diebold-Mariano** en complément, variance groupée par bloc ; il n'entre pas dans la règle.

### Règle de décision

Un groupe de variables ou un modèle plus complexe **B remplace A** si et seulement si les trois conditions sont vraies :

1. **(i)** le gain moyen de log-loss du total sur les 4 plis poolés, A − B, est **positif et son intervalle à 95 % exclut 0** ;
2. **(ii)** le gain moyen est positif dans **au moins 3 plis sur 4** ;
3. **(iii)** la **calibration ne se dégrade pas**, mesurée sur les prédictions des 4 plis **poolées** (environ 7 000 matchs, 10 déciles d'environ 700 matchs) : l'écart absolu moyen par décile de P(T ≥ 3) de B ne dépasse pas celui de A de plus de **0,5 point**, et la **pente** de calibration de B est dans **[0,9 ; 1,1]**.

Précisions (écart à la proposition, justifié) :

- (iii) se calcule **poolé**, et non par pli : par pli, un décile ne compte qu'environ 175 matchs, et l'erreur d'échantillonnage (environ 3,7 points) noierait le seuil de 0,5 point.
- Un B **significativement moins bon** (intervalle entièrement négatif) est rejeté comme un B non significatif : on garde A.
- **À gain non significatif, on garde le plus simple** : G0 < G1 < G2 < G3 ; M2 < M3 < M4 < M5 < M6 ; `top5` < `top5_d2`.
- **Ordre des comparaisons** : les structures (M3 à M6) se comparent avec les variables **G0 + G1** (décision 5), chacune à la structure retenue avant elle ; puis les groupes G2 et G3 s'ajoutent un par un à la structure retenue (ablations cumulatives) ; enfin la population d'apprentissage.
- **M1 et M2** sont des étapes pédagogiques, **pas des candidats** au choix final (ADR-0009).
- La règle s'applique mécaniquement (`modeling/experiment.decision`) ; le rapport de chaque comparaison écrit les trois booléens.
- Critère de révision de l'ADR-0009 conservé : un modèle meilleur en log-loss mais moins bon en RPS **et** en calibration sur plusieurs plis fait revoir la métrique principale, pas retenir ce modèle.

### Objectif de réussite du MVP (rapport E.1, reformulé)

- **Critère** : le modèle retenu bat **B1** en validation glissante, sur le log-loss du total, avec un intervalle à 95 % qui exclut 0.
- **Critère** : la couverture observée de [q10 ; q90] est à **±3 points** de la moyenne des couvertures annoncées (ADR-0009).
- **Diagnostic, non bloquant** : la calibration de P(T > 2,5) à ±3 points par décile. Avec environ 700 matchs par décile, l'erreur d'échantillonnage seule atteint environ 2 points (√(0,5 · 0,5 / 700) ≈ 1,9) : le résultat est publié tel quel.

### Journalisation

- Une expérience = un fichier `experiments/<nom>.yaml` (modèles, grilles, plis, population, graine, rééchantillonnages, comparaisons) ; un rapport `reports/experiments/<id>.json` (métriques par pli et poolées, intervalles, calibration, décision) ; les prédictions par match dans `data/experiments/<id>/` (ignoré par Git).
- **Tous les essais sont conservés**, y compris les échecs ; `reports/experiments/INDEX.md` (généré) en donne le nombre.

## Conséquences

- Le tag annoté `protocole-v1` est posé sur le commit de fusion de cette ADR. Toute modification ultérieure du protocole passe par une **nouvelle** ADR, qui dit ce qui avait déjà été évalué à sa date.
- Les références (4.5) sont les premières évaluations ; les modèles M1 à M6 viennent ensuite (lot 2).
- **Critères de révision** : un intervalle trop large pour trancher G1 et G2 contre B1 (ADR-0012 : ajouter un pli 2020-21, huis clos traité) ; le critère de révision de l'ADR-0009 ci-dessus.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
