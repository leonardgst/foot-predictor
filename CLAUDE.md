# CLAUDE.md — consignes pour Claude Code

Ce fichier contient les règles **stables** du projet. L'état courant est dans `docs/ETAT_PROJET.md`, pas ici.

## Le projet en bref

`foot-predictor` : prédire la **distribution du nombre de buts** d'un match de football (top 5 européen), avec une application locale qui explique chaque prédiction. C'est un **projet d'apprentissage** mené seul, à 10 h par semaine : la clarté, la justification des choix et la documentation comptent autant que la performance.

## À lire au début de chaque session, dans cet ordre

1. `docs/ETAT_PROJET.md` : où on en est, prochaine action.
2. Les ADR concernées dans `docs/decisions/`. **Elles font foi.**
3. La section du rapport `docs/cadrage/rapport_cadrage_2026-09-24.md` citée dans la demande (par exemple « G.6 », « H.7 »). Le rapport est un instantané : ne jamais le modifier.

## Comportement attendu

- Reformuler la tâche en 2-3 lignes et proposer un plan **avant** de modifier des fichiers. Poser une question si la demande est ambiguë ou contredit une ADR.
- Une tâche = une branche = une PR. Ne jamais committer directement sur `main`, sauf pour `docs/ETAT_PROJET.md` et `docs/JOURNAL_ERREURS.md`.
- Rester dans le périmètre demandé ; signaler le reste au lieu de le faire.
- Expliquer les choix non évidents : l'utilisateur apprend en relisant.
- Ne pas introduire de nouvelle dépendance sans la justifier (besoin concret, alternative plus simple).

## Interdits absolus

- **Consommer du quota API-FOOTBALL** (tout appel réel à l'API) sans accord explicite dans la conversation.
- Afficher, logguer, committer ou recopier un secret (`API_FOOTBALL_KEY`, mots de passe des `.env.*`).
- Modifier ou supprimer quoi que ce soit dans `data/raw/`.
- Lancer `docker compose down -v` ou supprimer une base.
- Committer des données (`data/`, `models/`) : licences et volume.
- Exécuter `ingestion/api_football.py` (raw → staging) : il identifie les joueurs par leur nom et sera remplacé par le nouveau chargeur (ADR-0008).

## Architecture (résumé)

- Couches : brut en fichiers `data/raw/**.json.gz` + journal de requêtes (ADR-0003) → Postgres `staging` (référentiel) → `features` → modèles → prédictions.
- Code : `src/foot_predictor/` (`config.py`, `db/`, `ingestion/`, `features/`, `modeling/`, `market_value/` gelé), tests dans `tests/` (même organisation), migrations dans `migrations/versions/`.
- Règle temporelle : toute variable d'un match est calculée à partir de données **strictement antérieures** au match et disponibles à l'horizon de prédiction.

## Commandes principales

```bash
uv sync --all-groups                      # installer l'environnement
docker compose up -d                      # bases Postgres dev (5440) et test (5433)
APP_ENV=dev uv run alembic upgrade head   # migrations
uv run pytest -m "not db" -q              # tests sans base (CI)
uv run pytest -q                          # tous les tests (base de test démarrée)
```

## Conventions

- Identifiants de code en anglais ; documentation, docstrings et messages de commit en français.
- Branches : `<type>/<etape>-<sujet>` (ex. `fix/03-collecteur-lots-ids`, `docs/01-integration-cadrage`).
- Commits atomiques, format Conventional Commits : `type(portée): résumé à l'impératif` (72 caractères max), corps qui explique le **pourquoi**. Types : `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `build`, `ci`, `data`, `exp`.
- Fusion par PR avec merge commit ; branche supprimée après fusion.
- Workflow Git provisoire (rapport J.2) en attendant la décision M15.

## Tests

- Toute fonction nouvelle ou modifiée a des tests. Aucun appel réseau dans les tests (réponses simulées, payloads dans `tests/fixtures/`).
- Les tests nécessitant Postgres sont marqués `db`.
- Les tests passent **avant** l'ouverture de la PR.

## Documentation

- En fin de session : mettre à jour `docs/ETAT_PROJET.md` (cases cochées, prochaine action, commandes de la prochaine session).
- Chaque erreur résolue : une entrée dans `docs/JOURNAL_ERREURS.md`.
- Chaque nouvelle décision : une ADR dans `docs/decisions/` (modèle `_modele_adr.md`), ajoutée à l'index.
- Le mode d'emploi d'une étape va dans `docs/realisation/<NN_etape>/README.md`.

## Définition de « terminé »

Code relu et compréhensible, tests au vert, documentation mise à jour (état, journal, ADR si besoin, README de l'étape), PR ouverte avec : quoi, pourquoi, comment c'est testé, commandes à lancer.

## Contraintes du projet

Gratuit, local, légal (sources dont les conditions le permettent), adapté à un portable Windows de 3-4 ans.
