# Récap — Mise en place Git, GitHub, Docker et environnements

Ce document complète `recap_decisions_projet.md` (section 7 — Stack technique). Il détaille concrètement ce qui a été mis en place pour démarrer le projet : dépôt Git, hébergement GitHub, et environnements PostgreSQL via Docker.

---

## 1. Dépôt Git local

- Dossier de travail : `foot-predictor/`
- Structure initiale créée conformément à la section 7 du récap projet (`src/foot_predictor/`, `migrations/versions/`, `tests/`, etc.)
- `git init` effectué, premier commit réalisé sur la structure de base
- `.gitignore` créé **avant** la création des fichiers `.env.*`, pour ne jamais committer de secrets par erreur (ignore notamment `.env.dev`, `.env.test`, `.env.prod`, `.venv/`, `__pycache__/`)

## 2. Branches

Conformément à la convention retenue (`main` ↔ prod, `dev` ↔ test, `feature/*` ↔ développement quotidien) :

- `main` : créée et poussée sur GitHub, tracke `origin/main`
- `dev` : créée à partir de `main`, poussée sur GitHub, tracke `origin/dev`
- Le travail quotidien se fera sur des branches `feature/xxx` créées à partir de `dev`, puis mergées dans `dev`. `dev` sera mergée dans `main` uniquement quand une version est stable et prête pour la prod.

## 3. Hébergement GitHub

- Dépôt distant créé : `github.com/leonardgst/foot-predictor` (**privé**)
- Remote local relié via `git remote add origin ...` (corrigé une fois après une erreur de nommage initiale)
- Authentification gérée via la fenêtre de connexion navigateur (ou token si nécessaire)

## 4. Environnements PostgreSQL — dev et test

**Décision confirmée** : dev et test tournent en local via **Docker Compose**, avec **deux conteneurs séparés** (plutôt qu'un seul conteneur avec deux bases), pour une isolation complète — cohérent avec le choix initial de la section 7 et avec le comportement futur de la prod (base isolée sur Neon).

| Environnement | Conteneur | Port hôte | Base | Fichier de config |
|---|---|---|---|---|
| Dev | `foot-predictor-dev` | 5432 | `foot_predictor_dev` | `.env.dev` |
| Test | `foot-predictor-test` | 5433 | `foot_predictor_test` | `.env.test` |
| Prod | *(hors Docker)* | — | à créer sur Neon | `.env.prod` |

- Chaque conteneur a son propre volume Docker persistant (`pg_dev_data`, `pg_test_data`) — les données survivent à un redémarrage du conteneur, mais peuvent être réinitialisées proprement avec `docker compose down -v`.
- Les fichiers `.env.dev` et `.env.test` contiennent les identifiants (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) et ne sont **jamais commités** (protégés par `.gitignore`).
- Un `.env.example` est commité, avec des valeurs `changeme`, pour documenter le format attendu sans exposer de secret.

### Pourquoi ce choix plutôt qu'une installation PostgreSQL native

| | Installation native (idée de départ) | Docker Compose (retenu) |
|---|---|---|
| Isolation | Une seule instance système partagée | Un conteneur par environnement, indépendant |
| Reset | Manuel, risque d'impacter d'autres projets | `docker compose down -v` puis `up`, en 10 secondes |
| Reproductibilité | Dépend de la machine | Décrite dans `docker-compose.yml`, versionnée dans Git |

L'installation PostgreSQL native faite initialement n'est donc pas utilisée pour ce projet.

## 5. Environnement de prod — Neon

- Prod hébergée sur **Neon** (PostgreSQL serverless, cloud, tier gratuit), pas en local et pas dans Docker
- Accessible depuis internet (nécessaire pour une appli déployée), avec fonctionnalité de branching pour tester des migrations avant application réelle
- *(Compte Neon à créer — étape non encore réalisée à ce stade)*

## 6. Bascule entre environnements

La variable d'environnement `APP_ENV` détermine quel fichier `.env.*` est chargé par `pydantic-settings`, donc à quelle base l'application se connecte :

```bash
APP_ENV=dev uv run alembic upgrade head      # local, conteneur Docker
APP_ENV=test uv run alembic upgrade head     # local, conteneur Docker
APP_ENV=prod uv run alembic upgrade head     # Neon, cloud
```

## 7. État actuel / prochaines étapes

Fait :
- [x] Dépôt Git initialisé, structure de base créée
- [x] Branches `main`/`dev` créées et poussées sur GitHub
- [x] `docker-compose.yml` écrit, conteneurs dev et test démarrés et fonctionnels

À faire :
- [ ] Créer le compte et le projet Neon (prod)
- [ ] Vérifier la connexion aux bases dev/test depuis VSCode (extension SQLTools ou pgAdmin4)
- [ ] Mettre en place Alembic et créer les schémas `raw`, `staging`, `features` dans chaque base
- [ ] Reste des points ouverts listés en section 8 du récap projet principal (détail des tables, choix du modèle statistique, stratégie de scraping, réconciliation des identifiants, orchestration, stratégie de tests)

---

*Document généré à partir de l'échange avec Claude — à mettre à jour au fil des décisions futures.*
