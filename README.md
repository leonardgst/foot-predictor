# foot-predictor

Prédire la **distribution du nombre de buts** d'un match de football des cinq grands championnats européens, avec une application locale qui explique chaque prédiction.

Le modèle estime les buts attendus de chaque équipe, puis en déduit la loi du total : P(0 but), P(1 but)…, le total attendu, P(plus de 2,5 buts) et un intervalle avec sa couverture annoncée. La métrique principale est le log-loss du total ([ADR-0009](docs/decisions/ADR-0009-cible-metrique.md)).

C'est un **projet d'apprentissage** mené seul : la clarté, la justification des choix et la documentation comptent autant que la performance. Contraintes : gratuit, local, sources légales.

## État

L'état courant (partie en cours, prochaines actions, dates) est tenu à jour dans [`docs/ETAT_PROJET.md`](docs/ETAT_PROJET.md), et les décisions dans l'[index des ADR](docs/decisions/README.md). Cette page ne le recopie pas, pour ne pas se périmer.

## Démarrage rapide

Prérequis : Docker, [`uv`](https://docs.astral.sh/uv/), fichiers `.env.dev` et `.env.test` créés à partir de `.env.example` (encodage UTF-8 **sans BOM**).

```bash
uv sync --all-groups                      # installer l'environnement
docker compose up -d                      # bases Postgres dev (5440) et test (5433)
APP_ENV=dev uv run alembic upgrade head   # migrations
uv run pytest -m "not db" -q              # tests sans base (CI)
uv run pytest -q                          # tous les tests (base de test démarrée)
```

Les commandes sont écrites pour un terminal bash (Git Bash sous Windows).

## Documentation

- [`docs/README.md`](docs/README.md) : index de la documentation, ordre de lecture.
- [`CLAUDE.md`](CLAUDE.md) : règles du projet et consignes pour Claude Code.
