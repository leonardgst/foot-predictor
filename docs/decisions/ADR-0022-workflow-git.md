# ADR-0022 — Workflow Git : `main` et branches courtes, PR pour tout, merge commit, tags

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : rapport de cadrage, J.1 à J.3, décision M15 ; décision d.4 de la session « partie 2 » du 2026-09-29 ; ADR-0021 (code du gel)

## Contexte

Le workflow d'origine passait par une branche longue `dev` (`feature` → `dev` → `main`). Depuis la partie 0, le projet applique à titre provisoire le workflow du rapport J.2 : `main` et des branches courtes, fusionnées par PR. Au 2026-09-29, `dev` et 6 autres branches distantes sont entièrement fusionnées dans `main`.

Contraintes :

- une seule personne, 10 heures par semaine ;
- dépôt privé sur GitHub Free : pas de protection de branche ;
- deux checkouts du même dépôt sur le portable (`C:/foot-predictor`, qui fait tourner la collecte, et le worktree `C:/fp-travail`, où s'écrit le code). Ils partagent `.git/hooks`.

## Options envisagées

1. **Workflow d'origine** (`feature` → `dev` → `main`) : une branche longue de plus, sans besoin pour une personne seule.
2. **Rapport J.2** : `main` et branches courtes, PR pour tout le code, merge commit, tags annotés.

## Décision

Option 2, adoptée définitivement.

- **`main`** est la seule branche longue : toujours verte, toujours relançable.
- **Une tâche = une branche = une PR.** Nommage `<type>/<étape>-<sujet>`. Seuls `docs/ETAT_PROJET.md` et `docs/JOURNAL_ERREURS.md` peuvent se committer directement sur `main`.
- **Commits** atomiques, Conventional Commits en français. Le corps explique le pourquoi.
- **Fusion** par merge commit, après une CI verte et une base vérifiée (`gh pr view <n> --json baseRefName` : `main`, E-021). Les branches locale et distante sont supprimées après la fusion.
- **Tags annotés** aux jalons : `v0.1.0` (état avant la refonte), `v0.2.0` (collecteur v2, code du gel, ADR-0021), `data-freeze-2026-10`, `v0.3.0` (référentiel), et ainsi de suite (rapport J.2).
- **Hooks locaux** (pre-commit, installé comme outil uv hors de l'environnement du projet) :
  - `pre-commit` : gitleaks, ruff, fins de ligne, fichiers volumineux, caractères de contrôle ;
  - `pre-push` : `pytest -m "not db"`. Il remplace la protection de `main`, indisponible.
- **CI** : tous les tests, base comprise (service Postgres 16), et ruff, sur `main` et chaque PR.
- **Interdits** : `git push --force`, `git reset --hard` sur une branche partagée, modification de la configuration Git globale par un outil.

## Conséquences

- `dev` et les 6 branches fusionnées antérieures à la partie 1 sont supprimées du dépôt distant (2026-09-29).
- `CLAUDE.md` ne parle plus de workflow « provisoire ».
- Mode d'emploi : `docs/realisation/02_environnement/README.md`.
- **Critère de révision** : un second contributeur, ou un besoin de publier des versions parallèles (correctif sur une version figée). Il faudrait alors des branches de maintenance, comme le prévoit l'ADR-0021 pour un correctif éventuel du code du gel (`v0.2.1`).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
