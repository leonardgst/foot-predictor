# ADR-0043 — Test scellé H1 : relance unique après l'échec technique du premier lancement

- **Statut** : acceptée
- **Date** : 2026-10-22
- **Référence** : ADR-0012 (règle 5), ADR-0037, ADR-0039 ; E-059 ; `docs/resultats/test_scelle_h1.md` ; PR #80

## Contexte

Ce qui a déjà été lancé, le 2026-10-22 (sous-étape 4.16, PR #80) :

| Commande | Heure (UTC) | Commit | Issue | Lignes au journal |
|---|---|---|---|---|
| `features build --sealed-test --experiment experiments/scelle_h1.yaml` | 08:02 | `9724829` | jeu `ds-2026-10-22-94969da0`, 205 216 lignes, dont 9 118 scellées | 1 |
| `modeling evaluate experiments/scelle_h1.yaml --sealed-test --dataset ds-2026-10-22-94969da0` | 08:03 | `70f9766` | **échec technique** au bout de 8 s, à l'écriture du rapport | 2 (lectures du jeu et des cotes) |

- **Cause** (E-059) : dans `experiments/scelle_h1.yaml`, la clé descriptive `test_from: 2025-07-01` est lue comme une date par YAML. Le rapport recopie le fichier d'expérience, et son encodeur (`modeling.experiment._json_default`) refuse les dates. Le calcul, bootstrap compris, était terminé : les prédictions par match ont été écrites, puis le plantage a empêché le rapport et la ligne de résultat du journal.
- **Ce qui a été vu** : rien. Aucun rapport, aucune métrique, aucun chiffre affiché. Le fichier de prédictions (`data/experiments/scelle-h1-20261022T080319/predictions.parquet`) n'a jamais été ouvert ; son sha256 `14b103d3292cef4b3055034b8aea88a368f0b37b99fd77e66c9c1f2cdd560e44` a été relevé avant cette décision.
- **Contraintes** :
  - la règle 5 de l'ADR-0012 veut un test lancé une fois, publié tel quel, sans modèle modifié ensuite. Son but est d'empêcher qu'un résultat scellé vu influence un choix ; ici, aucun résultat n'a été vu, et aucun modèle ni fichier figé n'a changé ;
  - le code et la liste du test sont figés par le tag `pre-scelle-h1`, et `evaluate --sealed-test` refuse toute modification de `modeling/`, `features/` et `experiments/` depuis le tag ;
  - sans test terminé au journal, `train --final --include-sealed` (4.17) est refusé par le code.

## Options envisagées

1. **Relance unique par un lanceur placé hors des chemins figés.** Il appelle les mêmes garde-fous et la même fonction (`experiment.run_experiment`), sur le même jeu. Il ne remplace, le temps de l'appel, que l'encodeur du rapport, qui écrit en plus les dates. Le calcul est déterministe (graine fixée) : le sha256 des nouvelles prédictions doit être celui du premier lancement. Conséquences : code figé et liste figée inchangés ; une preuve vérifiable que la relance n'est pas une seconde chance.
2. **Corriger le fichier d'expérience (date entre guillemets) ou l'encodeur.** C'est modifier un chemin figé : le garde-fou refuse alors le test, sauf s'il est modifié lui aussi ou si un nouveau tag est posé. La liste figée change après coup. Plus lourd, et moins net.
3. **Reconstruire le rapport à partir du fichier de prédictions du premier lancement.** Il faudrait réécrire, hors du code figé, le calcul des métriques, du bootstrap et de la règle de décision : un second code d'évaluation, avec un risque d'écart avec le protocole. Écartée.
4. **Ne pas relancer.** H1 n'aurait aucun test scellé, le jalon J6 ne serait pas atteint, et 4.17 resterait refusé par le code.

## Décision

Option 1, choisie par l'utilisateur le 2026-10-22.

- **Lanceur** : `src/foot_predictor/sealed_rerun.py`, commande `uv run python -m foot_predictor.sealed_rerun`, sans argument. Le fichier d'expérience, le jeu, l'identifiant et le sha256 du premier lancement y sont des constantes.
- **Refus, sans rien lire ni écrire**, si l'une de ces conditions manque :
  1. les garde-fous de `evaluate --sealed-test` acceptent (tag, chemins figés inchangés, aucune évaluation terminée au journal) ;
  2. aucune modification suivie n'est en attente : le rapport nomme un commit exact ;
  3. le journal du scellé contient exactement les 3 lignes du premier lancement. **La relance n'a donc lieu qu'une fois, même si elle échoue à son tour** ;
  4. le fichier de prédictions du premier lancement est présent et inchangé (sha256 ci-dessus).
- **Même jeu** `ds-2026-10-22-94969da0` : aucun nouveau `build --sealed-test`.
- **Encodeur** : dates au format ISO. Toute autre valeur qu'aucun encodeur ne sait écrire est mise sous forme de texte et signalée, plutôt que de faire perdre le calcul.
- **Répétition préalable** (tests sans base ni scellé, `tests/test_sealed_rerun.py`) : le vrai `scelle_h1.yaml` (5 modèles, 10 000 rééchantillonnages, marché compris) passe de bout en bout sur des données synthétiques ; sans le nouvel encodeur, il échoue comme le premier lancement ; deux exécutions donnent des prédictions identiques octet pour octet.
- **Règles de lecture, fixées avant la relance** :
  - le résultat de la relance **est** le résultat du test scellé H1 : publié tel quel dans `docs/resultats/test_scelle_h1.md` (tableaux générés par `modeling summary`), quel qu'il soit ;
  - sha256 égaux : la relance reproduit exactement le calcul du premier lancement ;
  - sha256 différents : le résultat est publié quand même, avec l'écart. Le contenu des deux fichiers n'est comparé qu'**après** la publication, pour expliquer l'écart. Aucune autre exécution ;
  - relance en échec : aucune autre relance (le lanceur la refuse). Constat, puis nouvelle ADR ;
  - valeurs écrites sous forme de texte : signalées sur la page de résultats.
- **Comptage des essais** : le premier lancement n'a pas de rapport. `reports/experiments/INDEX.md` ne compte donc que la relance. Cette ADR et la page de résultats comptent deux lancements du test scellé, dont un échec technique sans résultat.

## Conséquences

- Fichiers : `src/foot_predictor/sealed_rerun.py`, `tests/test_sealed_rerun.py` ; E-059, README de l'étape 10 et `ETAT_PROJET.md` mis à jour. Aucun changement sous les chemins figés.
- Après la relance, le journal du scellé compte 6 lignes : les 3 du premier lancement, puis les deux lectures et la ligne de résultat de la relance.
- **On s'interdit**, pour H1 : `evaluate --sealed-test` lancé directement (il planterait de la même façon), un nouveau `build --sealed-test`, toute modification des chemins figés avant la fin de 4.17.
- 4.17 suit l'ADR-0039 : entraînement final avec les matchs scellés, une fois le résultat publié.
- Pour le test de la version intermédiaire (H2) : appliquer la prévention d'E-059 avant le tag de la liste. Chaque fichier d'expérience doit passer par l'encodeur du rapport, et le vrai fichier du test doit être répété de bout en bout sur des données synthétiques.
- **Critère de révision** : si les sha256 diffèrent et que la comparaison des deux fichiers montre un calcul non déterministe, la conclusion du test H1 est restreinte en conséquence, dans une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
