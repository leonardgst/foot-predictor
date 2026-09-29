# Étape 02 : environnement de développement

Outils et conventions du dépôt : environnement Python, bases, qualité du code, hooks Git, intégration continue, workflow Git. Décisions : ADR-0022 (workflow Git), ADR-0025 (bases), ADR-0026 (environnement).

## Machine et dossiers

- Windows 11, terminal **Git Bash** (ADR-0026). Les options Windows qui commencent par `/` s'écrivent `//` (`schtasks //Query`), et un chemin à antislash se met entre apostrophes (E-029).
- `C:/foot-predictor` : checkout principal. Il fait tourner la collecte et ses tâches planifiées jusqu'au gel.
- `C:/fp-travail` : worktree où s'écrit le code, sur des branches courtes. `main` n'y est pas extractible : partir d'`origin/main` (`git switch --no-track -c <branche> origin/main`).
- Les deux dossiers partagent le même dépôt Git, donc les mêmes hooks (`.git/hooks`).

## Environnement Python et bases

```bash
uv sync --all-groups                          # environnement du projet (.venv)
APP_ENV=dev uv run alembic upgrade head       # base de travail
APP_ENV=test uv run alembic upgrade head      # base de test
```

Bases et `.env` : voir `docs/realisation/04_referentiel/README.md` et l'ADR-0025. Ne jamais afficher un `.env`.

## Qualité du code : ruff

```bash
uv run ruff check .          # contrôle (E, W, F, I, UP, B ; E501 et B905 ignorés)
uv run ruff format .         # formatage, longueur 120
```

Configuration dans `pyproject.toml`. **Exclus** :

- les chemins gelés jusqu'au gel (`collect/api_football/`, `rawstore/`, `quality/raw_check.py`, `scripts/taches_planifiees/` et leurs tests) ; les fichiers **ajoutés** dans ces dossiers sont contrôlés ;
- les migrations déjà appliquées (0001 à 0003), qui ne se réécrivent jamais, même pour le formatage (E-030).

Le commit de formatage de masse est listé dans `.git-blame-ignore-revs` (`git config blame.ignoreRevsFile .git-blame-ignore-revs`).

## Hooks Git : pre-commit

```bash
uv tool install pre-commit     # une fois par machine, hors de l'environnement du projet
pre-commit install             # installe les hooks pre-commit et pre-push
pre-commit run --all-files     # tout vérifier (5 minutes la première fois : installation de Go pour gitleaks)
```

| Hook | Quand | Rôle |
|---|---|---|
| gitleaks | commit | refuse un secret (clé, mot de passe) |
| check-added-large-files | commit | refuse un fichier de plus de 500 Ko (données, modèles) |
| check-merge-conflict, check-yaml | commit | marqueurs de conflit, YAML invalide |
| mixed-line-ending (`--fix=no`) | commit | signale un fichier qui mélange LF et CRLF, sans rien réécrire |
| ruff, ruff-format | commit | versions de `uv.lock` |
| caractères de contrôle | commit | tabulations et caractères de contrôle dans `.md`, `.py`, `.yaml`, `.cmd` (E-029) |
| tests sans base | push | `uv run pytest -m "not db" -q` |

- **Pourquoi pre-commit hors du projet** : le hook doit rester utilisable quand le worktree passe sur un ancien tag (session de gel, tag `v0.2.0`).
- Sur une branche sans `.pre-commit-config.yaml` (tag `v0.2.0`), committer et pousser avec `PRE_COMMIT_ALLOW_NO_CONFIG=1`.
- `git pull` et `git fetch` ne déclenchent aucun de ces hooks.
- Fins de ligne : Git convertit à l'extraction sous Windows ; les `.cmd` restent en CRLF (`.gitattributes`).

## Intégration continue

`.github/workflows/tests.yml`, sur `main` et chaque PR :

1. `uv sync --all-groups` ;
2. `ruff check` et `ruff format --check` ;
3. service Postgres 16 éphémère, `alembic upgrade head` ;
4. **tous les tests**, base comprise. `FP_REQUIRE_DB=1` fait échouer un test `db` au lieu de le sauter si la base manque.

Les tests marqués `raw` lisent le vrai brut : ils ne tournent qu'en local (`FP_RAW_DIR=... uv run pytest -m raw`).

## Workflow Git (ADR-0022)

- `main` est la seule branche longue, toujours verte. Une tâche = une branche = une PR.
- Branches `<type>/<étape>-<sujet>`. Commits atomiques, Conventional Commits en français, corps qui explique le pourquoi.
- Avant de fusionner :
  - `gh pr view <n> --json baseRefName` doit donner `main` (E-021) ;
  - CI verte (`gh pr checks <n> --watch`) ;
  - jusqu'au gel, contrôle de la règle 3 : `git diff --diff-filter=MDR --stat b1aee22..HEAD -- <chemins gelés>` doit être vide.
- Fusion par merge commit (`gh pr merge <n> --merge --delete-branch`), puis suppression de la branche locale. Dans le worktree, repasser d'abord sur `origin/main` détaché.
- Tags annotés aux jalons : `v0.1.0`, `v0.2.0` (code du gel), `data-freeze-2026-10`, `v0.3.0` (référentiel)…
- Interdits : `git push --force`, `git reset --hard` sur une branche partagée, modifier la configuration Git globale.
