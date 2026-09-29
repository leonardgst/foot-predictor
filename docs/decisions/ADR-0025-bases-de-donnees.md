# ADR-0025 — Bases : une base de travail reconstructible, une base de test éphémère, l'ancienne base intacte

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : rapport de cadrage, B.7, décision M14 ; décision d.3 de la session « partie 2 » du 2026-09-29 ; ADR-0008 (référentiel reconstruit depuis le brut)

## Contexte

Trois bases existaient : dev (port 5440), test (5433) et une base « prod » sur Neon (`APP_ENV=prod`), sans vraie production. La base dev contient l'ancien référentiel (`staging` identifié par les noms, 19 fusions manuelles faites à la main) et une copie JSONB d'une partie du brut (`raw.*`, 16 591 détails de match). Le nouveau `load` vide `staging` avant de le reconstruire.

Le 2026-09-29, la copie des `.env` vers le worktree a été refusée par les permissions de la session : la règle qui interdit de lire un `.env` couvre aussi sa copie (E-031).

## Options envisagées

1. Garder dev, test et Neon : triple maintenance, aucune vraie production.
2. **Une base de travail reconstructible et une base de test éphémère** ; Neon et `APP_ENV=prod` retirés.
3. SQLite : sans Docker, moins formateur.

## Décision

Option 2.

- **Ancienne base `foot_predictor_dev` intacte et conservée**, jamais vidée. Sauvegarde `pg_dump -Fc` vérifiée (lecture complète par `pg_restore`, sha256) dans `C:/fp_dumps/`. Le checkout principal (`C:/foot-predictor`) y reste connecté par son `.env.dev`, inchangé.
- **Base de travail `foot_predictor_travail`** sur le même serveur (5440), reconstruite par `load` depuis le brut.
- **Base de test `foot_predictor_test_travail`** sur le serveur de test (5433) ; en CI, un service Postgres 16 éphémère.
- **Accès depuis le worktree** : un rôle dédié `fp_travail`, propriétaire de ces deux bases seulement. Son mot de passe, aléatoire, a été écrit par un script directement dans les `.env.dev` et `.env.test` du worktree (ignorés par Git, **sans clé API**), sans jamais être affiché. Aucun `.env` existant n'a été lu ni copié.
- **Garde-fous de `load`** : nom de base confirmé (`--confirm-db`) ; refus de toute base dont le schéma `raw` contient des lignes, c'est-à-dire l'ancienne base ; base à la dernière migration.
- Neon et `APP_ENV=prod` : plus utilisés ni documentés. Les fichiers `.env.prod` existants ne sont ni lus ni supprimés (hors du dépôt).

## Conséquences

- Aucune suppression de base ni de schéma dans la partie 2.
- Le worktree ne peut pas consommer de quota : ses `.env` n'ont pas de clé API.
- Pour recréer la base de travail : `createdb` par `docker exec`, `alembic upgrade head`, puis `load` (voir `docs/realisation/04_referentiel/README.md`).
- **Critère de révision** : un besoin réel d'une base partagée ou distante (déploiement de l'API, rapport F.8) ; il ferait l'objet d'une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
