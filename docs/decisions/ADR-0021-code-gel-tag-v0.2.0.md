# ADR-0021 — Session de gel : code du tag `v0.2.0`, aucune mise à jour du checkout principal avant le tag du gel

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : complète l'ADR-0018 (exploitation jusqu'au gel) ; ADR-0005 (calendrier) ; ADR-0006 (sauvegarde) ; rapport de cadrage, J.2 (tags) ; `docs/realisation/03_collecte/gel.md`

## Contexte

La procédure de gel du 19 octobre, écrite en partie 1, faisait deux choses :

- un `git pull --ff-only` dans `C:/foot-predictor` avant le dernier `refresh` (étape 1) ;
- une branche du gel créée depuis `origin/main` (étape 4), d'où `freeze` est lancé.

Le 19 octobre, `main` contiendra la partie 2 : dépendances modifiées (`hdbscan` retiré, `ruff`), `config.py` modifié, outillage nouveau. Le code répété à blanc le 29 septembre (9 min 18 s, 16 421 fichiers vérifiés) est celui de `b1aee22`. Un `uv sync` qui échoue, ou un comportement changé, le jour de l'échéance ne laisserait que les 20 et 21 octobre de marge, avant la fin de l'abonnement le 22 à 07:56 UTC.

Les tâches planifiées tournent depuis `C:/foot-predictor`, avec le code de `b1aee22` : le mettre à jour pendant la collecte changerait aussi leur code.

## Options envisagées

1. **Garder `origin/main`** : le gel profite des corrections de la partie 2, mais exécute un code jamais répété, sous une échéance ferme.
2. **Figer le code du gel au tag `v0.2.0`** (`b1aee22`, collecteur v2, collecte P1 à P4 contrôlée) : le code est celui des tâches planifiées et de la répétition.

## Décision

Option 2.

- Tag annoté `v0.2.0` sur `b1aee22`, poussé le 2026-09-29.
- **`C:/foot-predictor` n'est pas mis à jour** entre la partie 1 et l'étape 7 de la procédure de gel : pas de `git pull`, pas de changement de branche. Seul `lock-status` est exigé avant le `git pull` de l'étape 7, qui a lieu après la fusion de la PR du gel et le tag `data-freeze-2026-10`.
- **La branche du gel part du tag** : `git switch --no-track -c data/03-gel-2026-10 v0.2.0`, puis `uv sync --all-groups` et les tests sans base. Sa PR (`docs/DATA_FREEZE.md` et un résumé de contrôle, fichiers nouveaux) se fusionne ensuite dans `main` normalement.
- Sur cette branche, le commit se fait avec `PRE_COMMIT_ALLOW_NO_CONFIG=1` : les hooks pre-commit de la partie 2 sont communs à tous les checkouts du dépôt, et le tag n'a pas de configuration pre-commit.

## Conséquences

- `gel.md` et `ETAT_PROJET.md` (« Commandes de la session de gel ») sont corrigés en conséquence.
- Les corrections de la partie 2 sur les chemins gelés (`collect/`, `rawstore/`, `scripts/taches_planifiees/`, YAML de collecte) n'entrent en service qu'après le gel (partie 2, phase B).
- La partie 2 répète, avant le gel, le passage du worktree sur `v0.2.0` (`uv sync`, tests), puis le retour sur `main`.
- **Critère de révision** : un défaut du code de `v0.2.0` découvert avant le 19 octobre, qui menacerait le gel. Le corriger alors sur une branche partie de `v0.2.0`, taguée `v0.2.1`, et mettre à jour cette ADR par une nouvelle.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
