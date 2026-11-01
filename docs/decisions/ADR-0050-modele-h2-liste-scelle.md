# ADR-0050 — Modèle H2 retenu et liste figée du test scellé H2

- **Statut** : acceptée
- **Date** : 2026-11-01
- **Référence** : ADR-0012 (règle 5 b), ADR-0037 (tag `protocole-v1`), ADR-0039, ADR-0043, ADR-0045, ADR-0047 (D5, D6), ADR-0048, ADR-0049 ; E-059, E-060 ; cadrage de la partie 6, sections 7 et 8 (6.9) ; `docs/resultats/h2_ablations.md`, `docs/resultats/h2_structures.md`

## Contexte

- **Le modèle H2 est choisi.** 6.7 a retenu G5 par la règle de l'ADR-0037, dans l'ordre G6, G5, G4 (ADR-0048) : +0,00078 [+0,00003 ; +0,00151] de log-loss du total, 4 plis sur 4. G6 et G4 ne sont pas retenus. 6.8 a gardé la structure M3 : M6 ne la remplace pas, M7 est significativement moins bon (ADR-0049). Le modèle H2 est donc **M3 sur G0 + G1 + G2 + G5**, top 5, demi-vie de G2 choisie par validation interne, rodage de G5 en 2015-16 (apprentissage à partir de 2016-17), jeu `ds-2026-11-01-e0defb32`.
- **L'ADR-0047 (D5) fixe le principe du test scellé H2** : la référence est la procédure H1 du premier test, `[M3_G0G2, H2]` est la seule comparaison de décision, B1 et le marché avant clôture sont publiés en contexte. Il reste à écrire la liste elle-même, puis à la figer par le tag `pre-scelle-h2`.
- **Le code ne savait faire qu'un test** :
  - `modeling/sealed.py` fixait le tag `pre-scelle-h1` ;
  - `features build` refusait `--horizon H2 --sealed-test`, et les compositions des matchs scellés n'étaient pas lues.

  Une fois `features/` gelé, ces deux points ne pourraient plus changer avant le test : ils se règlent **avant** le tag.
- **Préventions dues au premier test** :
  - E-059 : le rapport n'a pas pu s'écrire, parce que le fichier contenait une date YAML ; il a fallu une relance (ADR-0043) ;
  - E-060 : la ligne « règle de décision » n'avait pas de sens sur un pli unique (corrigé par la PR #92).
- **Ce que l'utilisateur a vu des matchs scellés** (rappel de l'ADR-0045) :
  - les variables du live, agrégées ;
  - les 434 lignes de la période scellée, contrôlées identiques au jeu `94969da0` sans affichage des valeurs ;
  - les métriques publiées du test H1 (`docs/resultats/test_scelle_h1.md`).

  Il n'a vu aucun score match par match, aucune cote, et rien des variables G4 à G6 sur ces matchs.
- **Matchs du test** : ceux de `staging` (chargement n° 7, brut gelé), donc les mêmes que pour le test H1 (2 096 matchs de championnat du top 5, du 1er juillet 2025 au gel). Les matchs du live, superposés en mémoire après le gel (ADR-0042), n'en font pas partie.
- **Puissance** (ADR-0047) : un gain inférieur à environ 0,007 sortira probablement non significatif. Le gain de G5 en validation (0,0008) est neuf fois plus petit.

## Options envisagées

1. **Liste réduite à ce que fixe D5, code du test préparé et répété avant le tag.** Le fichier comprend quatre modèles et trois comparaisons, dont une seule de décision. Le tag et les chemins gelés se déduisent du nom du fichier. Le jeu H2 scellé se construit par la commande habituelle. Le vrai fichier est répété de bout en bout sur données synthétiques. Conséquence : rien à corriger dans un chemin gelé au moment du test.
2. **Ajouter des comparaisons** : B0, marché à la clôture, `[B1, M3_G0G2]`. Elles n'apportent rien à la question du test (H2 contre H1), et chaque ligne de plus est une lecture de plus. Le test H1 en publie déjà la plupart. Écartée.
3. **Préparer d'avance un lanceur de secours**, sur le modèle de `sealed_rerun.py`. C'est prévoir l'échec plutôt que l'empêcher, et un second chemin d'exécution pour le même test. La prévention se fait plutôt par la répétition du vrai fichier, par la même fonction que la commande. Écartée.
4. **Reporter la construction du jeu H2 scellé à 6.12, comme l'annonçait le code.** Ce serait modifier `features/` après le tag, ce que le garde-fou refuse. Écartée.

## Décision

Option 1, avec le tag posé à la fin de 6.9, comme prévu (choix de l'utilisateur, 2026-11-01).

### Liste figée : `experiments/scelle_h2.yaml`

| Identifiant | Modèle | Rôle |
|---|---|---|
| `M3_G0G2` | M3, G0 + G1 + G2, demi-vie ∈ {60, 120, 240} | référence : **même ligne** que `scelle_h1.yaml` |
| `M3_H2` | M3, G0 + G1 + G2 + G5, demi-vie ∈ {60, 120, 240} | modèle H2 retenu : **même ligne** que `structures_h2.yaml` |
| `B1` | moyenne glissante, fenêtre ∈ {1, 2, 3, 6} | contexte |
| `marche_avant_cloture` | cote avant clôture | contexte (plus/moins 2,5) |

- **Comparaisons** :
  - `[M3_G0G2, M3_H2]`, **seule comparaison de décision**. Elle est en premier, parce que la ligne de résultat du journal recopie la première comparaison ;
  - `[B1, M3_H2]` et `[M3_H2, marche_avant_cloture]`, en contexte.
- **Procédure**, identique pour les quatre modèles et identique au premier test :
  - apprentissage sur 2015-16 à 2024-25 (G5 : à partir de 2016-17, lignes de rodage comptées) ;
  - hyperparamètres choisis par validation interne (apprentissage jusqu'en 2023-24, mesure sur 2024-25) ;
  - réajustement, puis une seule évaluation sur les matchs scellés, restreints à l'intersection des trois lois complètes.

  Graine 20260930, 10 000 rééchantillonnages.
- `test_from` est écrit entre guillemets : c'est un texte, et non plus une date (E-059).

### Code, avant le tag

- **`modeling/sealed.py`** :
  - le fichier `experiments/scelle_<v>.yaml` désigne la version ; tout autre nom est refusé avant même l'appel à Git ;
  - H1 : tag `pre-scelle-h1`, mêmes chemins qu'avant ;
  - H2 : tag `pre-scelle-h2`, chemins gelés `modeling/`, `features/`, `experiments/` **et `seal.py`**. `seal.py` porte la frontière et le journal du scellé ; `CLAUDE.md` le gelait déjà en règle, le garde-fou le gèle maintenant dans le code.
- **`features build --horizon H2 --sealed-test --experiment experiments/scelle_h2.yaml`** :
  - matchs, compositions et feuilles de match passent par la porte, scellé levé : trois lignes au journal ;
  - `build_frame_h2` reçoit `sealed_test`.

  Testé : les lignes scellées reçoivent leurs variables H2, avec exactement les valeurs d'une même table décalée de six ans, et la commande transmet le scellé aux trois lectures.

### Répétition et préventions (tests sans base ni scellé)

- `tests/test_scelle_h2.py` :
  - le **vrai fichier**, tel quel (10 000 rééchantillonnages, marché compris), passe par `run_experiment` sur données synthétiques avec colonnes H2 ;
  - le rapport s'écrit et les tableaux se relisent : « non applicable : 1 pli », aucun « remplace » ;
  - la ligne du journal porte `M3_G0G2 − M3_H2` ;
  - deux exécutions donnent des prédictions identiques octet pour octet ;
  - `M3_G0G2` prédit, au bit près, comme celui de `scelle_h1.yaml` sur les mêmes données ;
  - la liste est celle de cette ADR ;
  - les garde-fous acceptent la liste H2 une seule fois.
- `tests/modeling/test_experiment.py` : **chaque** fichier d'`experiments/` passe par l'encodeur du rapport. Seul `scelle_h1.yaml`, figé avec sa date et déjà relancé, reste refusé (constaté par le test).

### Contrôles et règles de lecture, fixés avant le test (6.12)

1. **Avant l'évaluation** : les colonnes H1 du jeu H2 scellé doivent être identiques, ligne à ligne et au bit près, à celles de `ds-2026-10-22-94969da0`. Seul le verdict s'affiche, jamais une valeur. En cas d'écart : arrêt avant l'évaluation, constat et nouvelle ADR. Aucun résultat n'aura été vu.
2. Le nombre de lignes scellées sans G5, et donc écartées par l'intersection, est publié.
3. **Un seul lancement.** Le résultat est publié tel quel dans `docs/resultats/test_scelle_h2.md`, avec des tableaux générés par `modeling summary`. Un échec technique ne se relance pas sans une nouvelle ADR qui dit ce qui a été vu (précédent : ADR-0043).
4. **Lecture** :
   - la conclusion principale reste celle de la validation glissante (7 156 matchs) ; le scellé la confirme ou non ;
   - un écart non significatif est le résultat attendu, vu la puissance, et ne retire pas G5 ;
   - H2 significativement **moins bon** : publié, et le rejeu garde H1 (ADR-0047) ;
   - H2 significativement meilleur : publié comme confirmation.
5. **Après la publication** : les prédictions de `M3_G0G2` sont comparées à celles de la relance du test H1 (`scelle-h1-20261022T120542`) sur les matchs communs. L'écart attendu est nul. Un écart serait publié et expliqué, sans changer le résultat.
6. **Pas de modèle final H2** appris avec les matchs scellés (D6). Le code ne l'interdit pas (`train --final --include-sealed` sur ce fichier) : c'est la règle qui l'interdit. En rejeu des saisons scellées, le modèle de 2025-26 et de 2026-27 est celui du test.

### Gel

Le tag annoté `pre-scelle-h2` est posé sur le commit de fusion de la PR de 6.9. Jusqu'au test, `src/foot_predictor/modeling/`, `src/foot_predictor/features/`, `src/foot_predictor/seal.py` et `experiments/` ne changent plus : `git diff --stat pre-scelle-h2 -- <ces chemins>` doit être vide avant chaque fusion. Le tag ne se déplace jamais.

## Conséquences

- **Fichiers** :
  - nouveaux : `experiments/scelle_h2.yaml`, `tests/test_scelle_h2.py` ;
  - modifiés : `modeling/sealed.py`, `modeling/__main__.py` (aide), `features/build.py`, `features/__main__.py` (aide) ;
  - tests adaptés : `tests/modeling/test_sealed_and_final.py`, `tests/modeling/test_experiment.py`, `tests/features/test_dataset_h2.py`, `tests/test_seal.py` ; `synthetic_odds` déplacé dans `tests/modeling/synthetic.py`.

  Aucune nouvelle dépendance.
- **Garde H1** : aucun modèle ni aucune variable H1 ne change. `features/build.py` ne change que le chemin H2 scellé. `inference check --only replay` reproduit le rejeu.
- **6.10 et 6.11** (H2 en rejeu, clôture de la phase A) ne touchent que `inference/`, `api/`, `ui/`, les tests et la documentation. Le rejeu H2 des saisons 2021-22 à 2024-25 lit la procédure de `M3_H2` dans `scelle_h2.yaml`, comme le rejeu H1 lit `scelle_h1.yaml`.
- **On s'interdit** :
  - tout changement d'un chemin gelé avant le test ;
  - tout nouveau `build --sealed-test` ou `evaluate --sealed-test` avant 6.12 ;
  - toute lecture du scellé par le développement avant le test.
- **Critères de révision** :
  - un défaut trouvé dans un chemin gelé avant le test passe par une nouvelle ADR. Le garde-fou refuse le test tant que le code diffère du tag, et on ne déplace pas le tag pour le contourner ;
  - si le contrôle 1 échoue, une nouvelle ADR décide avant toute évaluation.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
