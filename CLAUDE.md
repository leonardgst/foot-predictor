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
- Lancer `load` sur une autre base que la base de travail reconstructible : il vide `staging` (et `features`). L'ancienne base `foot_predictor_dev` (brut JSONB, 19 fusions manuelles) reste intacte ; le garde-fou la refuse, ne jamais le contourner (ADR-0025).
- Corriger le référentiel en base : toute correction est un YAML de `ingestion/mappings/`, rejoué par `load` (ADR-0008, règle 4).
- Lire une valeur (score, tirs, xG, cotes) d'un match joué à partir du **1er juillet 2025** (scellé, ADR-0012). Le code lit les matchs par la seule porte `features/sources.py` (ADR-0028) ; une requête à la main (`psql`) porte un filtre `match_date < '2025-07-01'` explicite, et après cette date on ne fait que des décomptes de présence.

## Collecte : verrou et tâches planifiées (ADR-0018)

- **Avant tout `git pull` dans `C:/foot-predictor`** : `uv run python -m foot_predictor.collect.api_football lock-status` doit répondre « libre » (code 0). Sinon, une commande écrit dans le brut : attendre.
- Toute commande qui écrit dans `data/raw/` prend le verrou `data/raw/_lock/collecte.lock` ; une nouvelle commande de ce type doit le prendre aussi. Ne jamais supprimer ce fichier à la main : un verrou périmé est remplacé automatiquement.
- Des tâches planifiées Windows `FootPredictor_*` lancent `refresh`, `run` et `t60` (liste dans `docs/realisation/03_collecte/README.md`). Ne pas les modifier ni les supprimer hors de la session prévue ; voir leurs journaux dans `data/logs/`.
- Toute commande qui consomme du quota porte `--max-requests`.
- **Jamais de `load` pendant une tâche planifiée** (lundis de `refresh`, de 07:45 à 11:00) ni quand `lock-status` répond « occupé » : il lit tout le brut pendant environ 13 minutes (778 s depuis la migration 0007).

## Architecture (résumé)

- Couches : brut en fichiers `data/raw/**.json.gz` + journal de requêtes (ADR-0003) → Postgres `staging` (référentiel, reconstruit par `load`, identifiants API ; ADR-0008) → `features` → modèles → prédictions.
- Bruts externes (CSV football-data) : dossier racine séparé jusqu'à leur recopie après le gel (ADR-0024). Understat écarté (ADR-0023).
- Code : `src/foot_predictor/` (`config.py`, `db/`, `ingestion/`, `features/`, `modeling/` avec ses anciens modules dans `modeling/legacy/`, `market_value/` gelé), tests dans `tests/` (même organisation), migrations dans `migrations/versions/`.
- Règle temporelle : toute variable d'un match est calculée à partir de données **strictement antérieures** au match et disponibles à l'horizon de prédiction.
- **Porte unique des données** (ADR-0028) : toute lecture des matchs pour les variables, les notebooks et les modèles passe par `features/sources.py` (`load_matches`, `load_dataset`, `load_odds`), qui filtre le scellé en SQL. Aucun autre module de `features/` ne lit `staging.match`, et aucun module de `modeling/` (hors `legacy/`) ne lit la base (tests d'architecture).
- **Variables** : fonctions pures (historique → valeurs, sans base), une fiche par colonne dans `features/registry.yaml` (horizon obligatoire), catalogue régénéré par `features catalogue`. Jeu de données : instantané Parquet versionné dans `data/datasets/` + `features.dataset_version` (ADR-0030). Aucun remplissage silencieux : une valeur incalculable reste vide.

## Protocole et modèles (partie 4)

- **Protocole figé** par l'ADR-0037 (tag `protocole-v1`) : plis, métriques, blocs, 10 000 rééchantillonnages, graine 20260930, règle de décision. On ne le modifie jamais après coup ; un changement passe par une nouvelle ADR qui dit ce qui avait déjà été évalué.
- Une expérience = `experiments/<nom>.yaml` → `reports/experiments/<id>.json` ; **tous les essais sont conservés**, échecs compris (`INDEX.md` en donne le nombre). Mesurer d'abord avec peu de rééchantillonnages. Les chiffres de `docs/resultats/` sont générés (`modeling summary`), jamais recopiés à la main.
- Tout modèle : `fit(lignes d'apprentissage)` puis `predict(lignes sans cible)` ; ajustements dans le pli ; lignes à valeur manquante exclues et comptées ; comparaisons sur l'intersection des matchs.
- Les cotes sont une **référence**, jamais une variable ; la clôture n'est jamais une référence de l'horizon H1 (ADR-0036).
- **Test scellé** (`--sealed-test`, `sealed_test=True`) : **une seule fois par version**, en phase B, sur la liste figée par le tag `pre-scelle-h1` (ADR-0039) ; résultat publié tel quel, aucun modèle modifié ensuite. La commande refuse elle-même un code changé depuis le tag ou un second test.
- **Depuis le tag `pre-scelle-h1`** : aucun changement sous `src/foot_predictor/modeling/`, `src/foot_predictor/features/`, `experiments/` avant le test scellé H1.
- **Un lot par session** : finir le lot, écrire son retour, mettre à jour la ligne « Reprise » d'`ETAT_PROJET.md` (dernière modification de chaque PR), puis s'arrêter.

## Inférence, API et interface (partie 5)

- **Chemins figés par `pre-scelle-h1`** jusqu'à la fin du test scellé : `src/foot_predictor/modeling/`, `src/foot_predictor/features/`, `src/foot_predictor/seal.py`, `experiments/`, `tests/modeling`, `tests/features` : on les **importe**, jamais on ne les modifie (contrôle `git diff --stat pre-scelle-h1..HEAD -- <ces chemins>` vide avant chaque fusion). Le code de la partie 5 vit dans `inference/`, `api/`, `ui/` et de nouveaux fichiers de `collect/football_data/`.
- **Même fonction** : l'inférence n'a aucune formule de variable propre ; elle appelle `features.dataset.build_frame` sur l'historique tronqué au jour du match, un jour à la fois (ADR-0040). Tout écart entre entraînement et inférence est un défaut.
- **Disponibilité** : une variable requise est présente, manquante (raison) ou périmée (source en retard) ; une seule non présente ⇒ `unavailable`, aucune prédiction, jamais de valeur de remplacement.
- **Rejeu** : modèle du pli de la saison, jamais un modèle qui a vu la saison ; saisons 2021-22 à 2024-25 tant que le test scellé n'est pas fait. **Live** : prédiction écrite avant le coup d'envoi seulement.

## Commandes principales

```bash
uv sync --all-groups                      # installer l'environnement
docker compose up -d                      # bases Postgres dev (5440) et test (5433)
APP_ENV=dev uv run alembic upgrade head   # migrations
uv run pytest -m "not db" -q              # tests sans base (CI)
uv run pytest -q                          # tous les tests (base de test démarrée)
uv run ruff check . && uv run ruff format .   # contrôle et formatage (chemins gelés exclus)
uv run python -m foot_predictor.ingestion load --raw-dir <brut API> --external-raw-dir <bruts externes> --confirm-db <base>
uv run python -m foot_predictor.ingestion check-referentiel   # rapport chiffré du référentiel (J3)
uv run python -m foot_predictor.features build                 # jeu de données versionné (J4)
uv run python -m foot_predictor.features check --invariance    # contrôle du jeu, anti-fuite sur données réelles
uv run python -m foot_predictor.modeling evaluate experiments/<nom>.yaml   # expérience sur les 4 plis (J5)
pre-commit run --all-files                # hooks : secrets, ruff, caractères de contrôle
```

## Conventions

- Identifiants de code en anglais ; documentation, docstrings et messages de commit en français.
- Branches : `<type>/<etape>-<sujet>` (ex. `fix/03-collecteur-lots-ids`, `docs/01-integration-cadrage`).
- Commits atomiques, format Conventional Commits : `type(portée): résumé à l'impératif` (72 caractères max), corps qui explique le **pourquoi**. Types : `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `build`, `ci`, `data`, `exp`.
- Fusion par PR avec merge commit, après CI verte et base vérifiée (`gh pr view <n> --json baseRefName` : `main`) ; branches locale et distante supprimées après fusion. « CI verte » = une exécution **terminée en succès** pour le commit de tête (`gh run list --commit <sha>`) : `gh pr checks --watch` rend la main sans rien attendre si la CI n'a pas démarré (E-047).
- Workflow Git (ADR-0022) : `main` seule branche longue, tags annotés aux jalons, hooks pre-commit et pre-push (`pre-commit install`). Jamais de `--force`, de `reset --hard` sur une branche partagée, ni de changement de la configuration Git globale.

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
