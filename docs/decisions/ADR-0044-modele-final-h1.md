# ADR-0044 — Clôture de la partie 4 : modèle final H1 appris avec les matchs scellés, jalon J6

- **Statut** : acceptée
- **Date** : 2026-10-22
- **Référence** : rapport, F.4 et jalon J6 ; ADR-0012 (règle 5), ADR-0037, ADR-0039, ADR-0040, ADR-0043 ; E-060, E-061 ; `docs/resultats/test_scelle_h1.md` ; carte `reports/model_cards/scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle.json`

## Contexte

- **Le test scellé H1 est terminé** (4.16, ADR-0043) : le modèle retenu bat B1 sur les matchs scellés, +0,0189 [+0,0102 ; +0,0282] de log-loss du total, sur 2 092 matchs ; couverture de [q10 ; q90] à 0,2 point de l'annoncée ; pente de calibration 1,00. Aucun modèle H1 ne se modifie ensuite (ADR-0012, règle 5).
- **L'ADR-0039 prévoit pour 4.17** le réentraînement du modèle retenu sur toutes les données disponibles, avec sa carte d'identité, puis le tag `v0.5.0`. La commande `train --final --include-sealed` a été écrite et figée avant le test (tag `pre-scelle-h1`). Elle refuse de s'exécuter tant que le journal ne contient pas « évaluation terminée ».
- **Ce que fait la procédure figée** (`modeling/final.py`) : elle apprend sur toutes les saisons présentes dans le jeu scellé, de 2015-16 à 2026-27 (matchs joués jusqu'au 2026-10-18). Elle choisit la demi-vie (60, 120 ou 240 jours) par validation interne sur la dernière de ces saisons, puis réajuste. Cette dernière saison n'est pas complète : la validation interne porte sur **341 matchs**, contre 1 752 sur 2024-25 lors du test scellé. Ce point a été relevé avant le lancement.

## Options envisagées

1. **Procédure figée telle quelle.** Validation interne sur le début de 2026-27 (341 matchs), puis réajustement sur toutes les saisons. Le choix est mécanique et fixé avant le test, et le code ne change pas. En contrepartie, le choix de la demi-vie repose sur un petit échantillon.
2. **Arrêter les données à 2025-26**, pour valider sur une saison complète. Il faut un appel hors de la commande (données filtrées), et l'apprentissage perd les 340 matchs les plus récents. Ce serait un écart à l'ADR-0039 (« toutes les données disponibles »), décidé après avoir vu le résultat scellé.
3. **Garder comme modèle final celui du test scellé** (appris sur 2015-16 à 2024-25). C'est exactement l'objet testé. Mais il ignore une saison et quart de matchs, les plus utiles au live, et l'ADR-0039 a tranché pour le réentraînement.

## Décision

Option 1, choisie par l'utilisateur le 2026-10-22, avant le lancement.

- **Modèle final H1** : `scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle`, entraîné le 2026-10-22 à 12:51 UTC en 4 s, depuis `c6d9454` (arbre propre).
  - Structure et variables : M3 (Poisson par équipe) sur G0 + G1 + G2, appris sur le top 5, mêmes 13 variables qu'au test.
  - Demi-vie : **240 jours**, la même qu'au test scellé et que dans 3 plis sur 4 en validation glissante.
  - Apprentissage : du 2015-08-07 au 2026-10-18, **40 180 lignes (20 090 matchs)**, dont les 4 184 lignes scellées du top 5 ; 26 lignes exclues pour valeur manquante, toutes antérieures au scellé (aucune ligne scellée exclue).
  - Jeu : `ds-2026-10-22-94969da0`. Carte : `reports/model_cards/scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle.json`. Modèle sérialisé : `models/<version>/model.joblib`, hors Git, sha256 `b121f30b…beff33840`.

  | Demi-vie | Log-loss du total, validation interne (début de 2026-27, 341 matchs) |
  |---|---|
  | 60 jours | 1,9754 |
  | 120 jours | 1,9702 |
  | **240 jours** | **1,9695** |

  L'écart entre 240 et 120 jours (0,0007) est petit pour un échantillon de 341 matchs. Au test scellé, sur les 1 752 matchs de 2024-25, l'ordre était le même et l'écart encore plus petit (1,8673 contre 1,8674). 120 et 240 jours sont donc presque équivalents ; 60 jours est moins bon dans les deux cas. Le niveau de la log-loss (1,97) ne se compare pas aux 1,88 du test scellé : l'échantillon est différent (début de saison, 341 matchs).
- **Stabilité** : les coefficients changent peu par rapport au modèle appris sans les matchs scellés (carte du 2026-09-30) ; l'écart absolu le plus grand est de 0,009, sur la constante de la Bundesliga.
- **Ce que garantit le test scellé** : il a mesuré la **procédure** (apprentissage jusqu'à une date, puis prédiction des matchs suivants). Le modèle final n'a, par construction, aucun match récent qu'il n'ait pas vu. Sa qualité attendue sur les matchs futurs est celle du test scellé, dont la carte reprend les métriques (rapport `scelle-h1-20261022T120542`).
- **Jalon J6 atteint** (rapport, calendrier) :

  | Critère | Où |
  |---|---|
  | M4, M5, M6 | `docs/resultats/modeles.md`, ADR-0038 |
  | Ablations G0 à G3 | `docs/resultats/ablations.md` |
  | Règle de décision appliquée | ADR-0037, ADR-0039 |
  | Test scellé une seule fois, résultat publié tel quel | `docs/resultats/test_scelle_h1.md`, ADR-0043 (deux lancements, un échec technique sans résultat) |
  | Carte d'identité du modèle | carte ci-dessus |
  | Modèle MVP choisi et justifié (ADR) ; tag `v0.5.0` | ADR-0039, cette ADR ; tag sur la fusion de la PR de 4.17 |

## Conséquences

- **Partie 5** :
  - en **live**, ce modèle devient le modèle actif à la sous-étape 5.13 (`ops.model_registry`, `inference/models.py`). Ce n'est pas fait ici : en attendant, l'inférence garde le modèle du 2026-09-30 ;
  - en **rejeu**, rien ne change : chaque saison utilise le modèle de son pli (ADR-0040). Depuis la fin du test, `check_replay_season` accepte aussi les saisons 2025-26 et suivantes ; leur mise en œuvre relève de la partie 5.
- **Fin du gel** (ADR-0043) : après la fusion de la PR de 4.17, les chemins figés par `pre-scelle-h1` peuvent de nouveau changer, par PR (corrections d'E-060 et d'E-061 d'abord). Le modèle H1 ne se modifie pas pour autant (ADR-0012, règle 5). Comme le fichier `joblib` relit les classes de `modeling/` à chaque chargement, toute PR qui touche `modeling/models/` doit montrer que les prédictions du modèle final H1 restent identiques.
- **Limites connues**, en plus de celles de la carte :
  - demi-vie choisie sur 341 matchs (ci-dessus) ;
  - la carte porte `code.dirty: true` alors que l'arbre était propre : la ligne du journal du scellé est écrite avant la lecture de l'état Git (E-061). Même cause pour `git_dirty: true` dans le manifeste du jeu `94969da0` ;
  - la ligne « règle de décision » des tableaux du test ne s'applique pas à un pli unique (E-060).
- On s'interdit : tout nouvel entraînement final H1 avec les matchs scellés, sauf pour reproduire celui-ci (même commit, même jeu), et toute modification de ce modèle.
- **Critère de révision** : si l'évaluation prospective de la partie 5 (matchs joués après le gel) montre que le modèle ne bat plus B1, le constat est publié tel quel. La version intermédiaire (H2, jalon J9) en repart dans une nouvelle ADR, sans retoucher H1.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
