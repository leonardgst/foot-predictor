# Documentation

Index de la documentation de `foot-predictor`. En cas de désaccord entre deux documents, **les ADR font foi**.

## Ordre de lecture

1. [`../CLAUDE.md`](../CLAUDE.md) : règles stables du projet (interdits, conventions, définition de « terminé »).
2. [`ETAT_PROJET.md`](ETAT_PROJET.md) : où on en est, prochaines actions, commandes de la prochaine session.
3. [`decisions/README.md`](decisions/README.md) : index des ADR, puis les ADR concernées par la tâche.
4. [`cadrage/rapport_cadrage_2026-09-24.md`](cadrage/rapport_cadrage_2026-09-24.md) : la section citée dans la tâche (par exemple « G.6 »). C'est un instantané, jamais modifié.
5. Le mode d'emploi de l'étape en cours, dans [`realisation/`](realisation/).

## Où trouver quoi

| Question | Document |
|---|---|
| Où en est le projet ? Que faire ensuite ? | [`ETAT_PROJET.md`](ETAT_PROJET.md) |
| Pourquoi tel choix ? | [`decisions/`](decisions/README.md) (ADR) |
| But, périmètre, architecture cible, stratégie de données et de modélisation, feuille de route | [`cadrage/rapport_cadrage_2026-09-24.md`](cadrage/rapport_cadrage_2026-09-24.md) |
| Cette erreur a-t-elle déjà été vue ? | [`JOURNAL_ERREURS.md`](JOURNAL_ERREURS.md) (chercher le message d'erreur) |
| Collecter API-FOOTBALL : commandes, `refresh`, profils ciblés, verrou, journal T-60, tâches planifiées, sauvegarde | [`realisation/03_collecte/README.md`](realisation/03_collecte/README.md) |
| Gel des données du 19 octobre : procédure pas à pas | [`realisation/03_collecte/gel.md`](realisation/03_collecte/gel.md) |
| Identifiants et couverture des compétitions | [`realisation/03_collecte/couverture.md`](realisation/03_collecte/couverture.md) (généré par `coverage`) |
| Contrôler la qualité du brut | [`realisation/05_controle_qualite/README.md`](realisation/05_controle_qualite/README.md) |
| Constats des paliers P1 et P2 | [`realisation/05_controle_qualite/constats_P1_P2.md`](realisation/05_controle_qualite/constats_P1_P2.md) |
| Constats du palier P3 | [`realisation/05_controle_qualite/constats_P3.md`](realisation/05_controle_qualite/constats_P3.md) |
| Collisions d'identifiants de joueurs (P1 à P3) | [`realisation/05_controle_qualite/constats_collisions.md`](realisation/05_controle_qualite/constats_collisions.md) |
| Rapports de contrôle datés (versionnés) | [`../reports/data_quality/`](../reports/data_quality/README.md) |
| Retours de session (bilan, écarts, reste à faire) | [`retours/`](retours/) : [`partie-1_2026-09-29.md`](retours/partie-1_2026-09-29.md), [`partie-2a_2026-09-29.md`](retours/partie-2a_2026-09-29.md), [`partie-3a_2026-09-29.md`](retours/partie-3a_2026-09-29.md), [`partie-4-lot1_2026-09-30.md`](retours/partie-4-lot1_2026-09-30.md), [`partie-4-lot2_2026-09-30.md`](retours/partie-4-lot2_2026-09-30.md), [`partie-4a_2026-09-30.md`](retours/partie-4a_2026-09-30.md) |
| Équations des modèles A (Poisson) et B (Dixon-Coles) | [`MODELE_MATHEMATIQUE.md`](MODELE_MATHEMATIQUE.md) |
| Résultats historiques A contre B, recalibration | [`RESULTATS_MODELE.md`](RESULTATS_MODELE.md) et [`model_results.json`](model_results.json) |
| Environnement : ruff, pre-commit, CI, bases, workflow Git (ADR-0022) | [`realisation/02_environnement/README.md`](realisation/02_environnement/README.md) |
| Référentiel : `load`, `check-referentiel`, YAML de rapprochement, bruts externes, commandes de la phase B | [`realisation/04_referentiel/README.md`](realisation/04_referentiel/README.md) |
| Contrôle du référentiel (chiffres, dont les cotes : section 7) | [`../reports/data_quality/referentiel_2026-09-30.md`](../reports/data_quality/referentiel_2026-09-30.md) |
| Variables du MVP : `build`, `check`, registre, versions du jeu de données, scellé | [`realisation/06_variables/README.md`](realisation/06_variables/README.md) |
| Fiche de chaque variable (généré depuis le registre) | [`realisation/06_variables/catalogue.md`](realisation/06_variables/catalogue.md) |
| Exploration statistique : notebooks et conclusions | [`realisation/07_exploration/README.md`](realisation/07_exploration/README.md) |
| Rapports des variables (réglage de l'Elo, `xg_proxy`, contrôle du jeu) | [`../reports/variables/`](../reports/variables/) |
| Journal des tests scellés (vide pendant le développement) | [`../reports/sealed_tests.md`](../reports/sealed_tests.md) |
| Protocole d'évaluation, expériences, métriques, références B0, B1 et marché | [`realisation/08_protocole_et_references/README.md`](realisation/08_protocole_et_references/README.md) |
| Modèles M1 à M6 : commandes, classes, ajout d'un modèle | [`realisation/09_modeles/README.md`](realisation/09_modeles/README.md) |
| Modèle MVP H1, test scellé, entraînement final, carte d'identité | [`realisation/10_selection_et_entrainement_final/README.md`](realisation/10_selection_et_entrainement_final/README.md) |
| Cartes d'identité des modèles entraînés | [`../reports/model_cards/`](../reports/model_cards/) |
| Résultats lisibles (références, puis modèles) | [`resultats/`](resultats/) : [`references.md`](resultats/references.md), [`modeles.md`](resultats/modeles.md), [`ablations.md`](resultats/ablations.md) |
| Rapports d'expériences (JSON) et index de tous les essais | [`../reports/experiments/INDEX.md`](../reports/experiments/INDEX.md) |
| Chapitres mathématiques LaTeX (compilation sur Overleaf) | [`latex/mathematiques/`](latex/mathematiques/) |
| Anciens récaps, RECAP_PROJET, guide d'abonnement | [`archives/`](archives/) (non maintenus) |

## Règles de la documentation

- **État** : `ETAT_PROJET.md` est mis à jour à chaque fin de session, en 100 lignes au plus.
- **Erreurs** : chaque erreur résolue reçoit une entrée dans `JOURNAL_ERREURS.md`.
- **Décisions** : chaque décision est une ADR, ajoutée à l'index. Une ADR acceptée ne se réécrit pas.
- **Étapes** : le mode d'emploi d'une étape va dans `realisation/<NN_etape>/README.md`.
- **Dossiers** : aucun dossier vide. Les dossiers prévus par le rapport (K.1) sont créés avec leur premier contenu ([ADR-0014](decisions/ADR-0014-tri-documentation.md)).
- **Archives** : un document dépassé part dans `archives/` par `git mv`, avec un bandeau d'archive ; rien n'est supprimé.
- **Fichiers générés** : `realisation/03_collecte/couverture.md`, `realisation/06_variables/catalogue.md`, `model_results.json`, `reports/data_quality/*`, `reports/variables/*` et `reports/experiments/*` sont produits par le code, ainsi que les tableaux de `resultats/`. On ne les modifie pas à la main.

## Anciens chemins

Le rapport de cadrage, certaines ADR et des commentaires de code citent ces chemins d'avant le tri du 2026-09-28 :

| Ancien chemin | Nouveau chemin |
|---|---|
| `docs/RECAP_PROJET.md` | [`archives/RECAP_PROJET.md`](archives/RECAP_PROJET.md) |
| `docs/OBJECTIFS.md` | [`archives/OBJECTIFS.md`](archives/OBJECTIFS.md) |
| `docs/API_FOOTBALL_ABONNEMENT.md` | [`archives/API_FOOTBALL_ABONNEMENT.md`](archives/API_FOOTBALL_ABONNEMENT.md) |
| `docs/recaps/<nom>.md` | [`archives/recaps/<nom>.md`](archives/recaps/README.md) |
| `scripts/one_off/` (partie 2) | [`../scripts/archives/`](../scripts/archives/) |
