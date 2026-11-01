# ADR-0048 — Spécification des modèles H2 et des expériences de la sous-étape 6.7, fixées avant toute mesure

- **Statut** : acceptée
- **Date** : 2026-11-01
- **Référence** : ADR-0010, ADR-0013, ADR-0037 (tag `protocole-v1`), ADR-0038, ADR-0039, ADR-0047 ; rapport de cadrage, H.3 à H.8, I.3, I.7 ; cadrage de la partie 6, sections 6 et 9 (D1 à D4, D9)

## Contexte

L'ADR-0047 a fixé l'ordre des groupes (G6, puis G5, puis G4), le rodage (D3), le choix de la demi-vie de la cohésion par validation interne (D2) et les diagnostics. Elle laisse ouvert ce qu'il faut écrire pour exécuter les expériences sans rien décider après coup : quelles colonnes de chaque groupe entrent dans le modèle, comment les choisir, quelle liste exacte d'expériences et de comparaisons.

**Ce qui a déjà été vu à la date de cette ADR** (la règle du protocole veut qu'on le dise) :

- **Aucune métrique de modèle** (log-loss, RPS, calibration) n'a été calculée avec une variable H2.
- Les lots 6.2 à 6.6 ont regardé des **statistiques descriptives** du jeu H2 : valeurs vides, distributions, corrélations entre variables, corrélation de chaque variable avec l'Elo et avec les buts marqués (brute, puis après retrait de la part linéaire de l'Elo). Les chiffres sont dans `docs/realisation/07_exploration/README.md`. Ils ont montré que `xi_quality` est corrélée à 0,83 avec l'Elo, que les habituels absents recoupent la cohésion (−0,85) et que, à Elo donné, seule `xi_quality` a une corrélation non négligeable avec les buts (0,07). Rien dans la spécification ci-dessous n'en découle : elle suit les groupes de l'ADR-0047 et du rapport.
- Le jeu `ds-2026-11-01-94e07897` de 6.5 a été reconstruit en `ds-2026-11-01-e0defb32` pour ajouter deux variantes de diagnostic de la cohésion (remise à zéro, fenêtre de 10 matchs) ; les 24 colonnes H2 précédentes y sont identiques, et les colonnes H1 le sont à `ds-2026-10-22-bf786ef1`.

## Options envisagées

1. **Choisir les colonnes et les expériences au fil des résultats.** Rejetée : c'est ce que le protocole interdit.
2. **Fixer ici la spécification et la liste des expériences.** Retenue.

## Décision

### Variables de chaque groupe dans le modèle

Modèle **M3** (Poisson par équipe, ADR-0038), population d'apprentissage et d'évaluation top 5. Les colonnes de l'équipe **et** celles de l'adversaire entrent (comme pour G2), **standardisées dans le pli**, linéairement dans log λ (aucune transformation choisie après coup), sauf l'indicateur « nouvel entraîneur », laissé binaire.

| Groupe | Colonnes de l'équipe (et `opp_…` pour l'adversaire) |
|---|---|
| G6 stabilité | `xi_overlap_prev`, **une** cohésion parmi `xi_cohesion_ewm_h3`, `_h5`, `_h10`, `_h20`, `_hinf`, `xi_new_starters` |
| G5 qualité du XI | `xi_quality`, `xi_regulars_missing`, `xi_mean_age` |
| G4 entraîneur | `coach_tenure_days`, `coach_is_new` |

Soit au plus 3 variables par équipe et par groupe (ADR-0013, ADR-0047). Les autres colonnes du jeu H2 ne servent qu'aux diagnostics.

### Hyperparamètres

- La **demi-vie de G2** (60, 120, 240 jours) et la **variante de cohésion** de G6 (5 valeurs) se choisissent **ensemble** par la validation interne de l'ADR-0037 (apprentissage 2015-16 à s − 2, mesure sur s − 1, critère : log-loss du total du top 5) : 15 candidats avec G6, 3 sans. La saison de test n'est jamais lue pour choisir.
- **Rodage (D3)** : un modèle avec G5 apprend à partir de 2016-17, un modèle avec G4 à partir de 2017-18 (le plus tardif des deux s'il a les deux). Ce début s'applique à la validation interne comme à l'ajustement. Les lignes d'apprentissage écartées pour cette raison sont **comptées** (`run_in_rows`), à côté des lignes à valeur manquante (`excluded_train_rows`) et des matchs de test sans prédiction.
- **Témoins de fenêtre** : le modèle H1 appris à partir de 2016-17 et à partir de 2017-18 (`train_from`), pour séparer le coût d'une fenêtre plus courte de l'apport d'un groupe.

### Expériences (fichiers `experiments/`, datés avant leur exécution)

1. **`ablations_h2.yaml`**, la décision. Dix modèles évalués sur les mêmes matchs : la base `A2_G0G2` (le modèle H1), les sept sous-ensembles non vides de {G6, G5, G4}, et les deux témoins de fenêtre. La règle de l'ADR-0037 s'applique **mécaniquement**, dans l'ordre G6, G5, G4, chaque groupe s'ajoutant au modèle **retenu** juste avant lui :
   - étape 1 : `A2_G0G2` → `G6` ;
   - étape 2 : `G6` → `G6_G5` si G6 est retenu, sinon `A2_G0G2` → `G5` ;
   - étape 3 : contre le modèle retenu après l'étape 2 : `G6_G5` → `G6_G5_G4`, `G6` → `G6_G4`, `G5` → `G5_G4`, ou `A2_G0G2` → `G4`.
   Toutes ces comparaisons figurent dans le fichier, parce que la suite dépend de l'issue de la précédente ; le chemin suivi est celui que la règle dicte, et lui seul décide. **Le modèle H2 retenu est celui où le chemin s'arrête.** Si aucune étape n'est retenue, le modèle H2 est le modèle H1, et ce résultat nul est publié (ADR-0013, règle 5).
   Diagnostics sans pouvoir de décision : chaque groupe seul contre la base (déjà des comparaisons de l'étape 1, de l'étape 2 sans G6 et de l'étape 3 sans G6 ni G5), les trois groupes ensemble contre la base, le coût des fenêtres courtes, et les groupes comparés à fenêtre égale (`A2_depuis_2016` → `G5`, `A2_depuis_2017` → `G4` et → `G6_G5_G4`).
2. **`stabilite_h2.yaml`**, le diagnostic de la stabilité (D2) : huit variantes de G6, jamais choisies sur les plis de test. Les sept cohésions (demi-vies 3, 5, 10, 20 et ∞, remise à zéro par saison, fenêtre de 10 matchs) et le recouvrement seul s'ajoutent chacune à la base H1 ; chaque variante est comparée à la base et au recouvrement seul (la plus simple). La remise à zéro est vide au premier match de la saison : ces matchs sortent de l'intersection de tous les modèles de cette expérience, et leur nombre est publié.
3. **`ablations_h2_mesure_duree.yaml`** : même contenu que le 1, avec 200 rééchantillonnages, pour mesurer la durée avant le vrai lancement. Ses intervalles ne décident rien. C'est un essai de plus dans l'index.

Tous les essais sont conservés et comptés dans l'index. Le protocole ne change pas : mêmes plis, métriques, 10 000 rééchantillonnages, graine 20260930, règle de décision à trois conditions, intersection des matchs, aucun remplissage.

### Diagnostics publiés avec chaque comparaison

- Écart par pli et poolé, avec intervalle ; nombre de plis gagnés ; calibration poolée (condition iii).
- **Écart par tranche de journées** (1-5, 6-10, 11-19, 20 et plus), avec intervalle par bootstrap de blocs sur la tranche (ajouté au moteur dans cette sous-étape, descriptif, hors de la règle).
- Lignes exclues par pli et par modèle (valeurs manquantes, rodage, matchs de test sans prédiction, matchs écartés par l'intersection).
- Hyperparamètres retenus dans chaque pli.
- D9 : 0,3 % des titulaires des plis n'ont aucune note antérieure (lot 6.3), très loin du seuil de 10 % : la variante corrigée par championnat n'est pas déclenchée.

## Conséquences

- **Code** : `Design` gagne G4, G5, G6 et `cohesion` ; `M3` gagne `cohesion` et `train_from` ; `protocol.select_and_fit` gagne le début d'apprentissage ; le moteur gagne l'écart par tranche de journées. Aucun de ces ajouts ne change un modèle H1 : la description et les paramètres d'un modèle H1 sont identiques, et le rejeu et les prédictions du modèle final H1 sont reproduits (garde H1, ADR-0044).
- **Gel** : à `pre-scelle-h2` (6.9), ces fichiers et ceux de `modeling/` et `features/` ne bougent plus jusqu'au test scellé.
- **Comparaisons multiples** : treize comparaisons dans `ablations_h2.yaml` (dont trois seulement décident), quinze dans `stabilite_h2.yaml` (aucune ne décide), et l'index donne le nombre d'essais.
- **Critère de révision** : si une variable H2 se révèle incalculable sur plus de 10 % des lignes d'un pli, ou si le chemin de décision ne tient pas dans les comparaisons écrites, une nouvelle ADR dit ce qui avait déjà été évalué (ADR-0047).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
