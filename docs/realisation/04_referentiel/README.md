# Étape 04 : référentiel reconstruit depuis le brut (jalon J3)

Mode d'emploi de `load` et de `check-referentiel`, des YAML de rapprochement et des bruts externes. Décisions : ADR-0008 (API-FOOTBALL fait foi pour les identifiants), ADR-0009 (cible et exclusions), ADR-0020 (collisions), ADR-0023 (sources externes), ADR-0024 (bruts externes), ADR-0025 (bases), ADR-0027 (périmètre des chargeurs).

## En bref

- `staging` n'est **jamais corrigé à la main** : il se reconstruit entièrement depuis le brut par `load`, et toute correction est un YAML de `src/foot_predictor/ingestion/mappings/` (ADR-0008, règle 4).
- Les entités (joueurs, entraîneurs, équipes, matchs) viennent des **identifiants API-FOOTBALL**. football-data ne crée jamais de joueur ; il s'apparie aux matchs API, et ne crée des matchs qu'hors de la couverture API.
- Deux chargements du même brut donnent les mêmes tables (empreintes md5 identiques, vérifié le 2026-09-29).
- Le brut n'est lu qu'en **lecture seule**.

## Bases (ADR-0025)

| Base | Serveur | Usage |
|---|---|---|
| `foot_predictor_travail` | dev, 5440 | base de travail, reconstruite par `load` |
| `foot_predictor_test_travail` | test, 5433 | tests `db` du worktree |
| `foot_predictor_dev` | dev, 5440 | **ancienne base, intacte** : ancien référentiel par noms, brut JSONB. `load` la refuse |

Les `.env.dev` et `.env.test` du worktree visent le rôle `fp_travail`, sans clé API. Sauvegarde de l'ancienne base : `C:/fp_dumps/foot_predictor_dev_2026-09-29.dump` (et son `.sha256`).

Recréer la base de travail, si besoin (aucune suppression : un nouveau nom) :

```bash
docker exec foot-predictor-dev sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE foot_predictor_travail_2 OWNER fp_travail"'
# puis POSTGRES_DB=foot_predictor_travail_2 dans .env.dev du worktree (sans afficher le fichier)
APP_ENV=dev uv run alembic upgrade head
```

## Commandes

```bash
# Reconstruction complète (6 à 10 minutes sur le portable)
APP_ENV=dev uv run python -m foot_predictor.ingestion load \
    --raw-dir C:/foot-predictor/data/raw --external-raw-dir data/raw --confirm-db foot_predictor_travail

# Contrôle J3 : reports/data_quality/referentiel_<date>.md (versionné, chiffres seulement)
APP_ENV=dev uv run python -m foot_predictor.ingestion check-referentiel
```

| Option de `load` | Rôle |
|---|---|
| `--raw-dir` | brut API-FOOTBALL (lecture seule) |
| `--external-raw-dir` | bruts externes (CSV football-data) ; absent : API seule |
| `--confirm-db` | nom de la base à reconstruire ; doit être celui de la base connectée |
| `--config` | périmètre de collecte (type ligue ou coupe des compétitions) |

**Garde-fous**, avant toute écriture : nom de base confirmé ; base à la dernière migration ; **refus de toute base dont le schéma `raw` contient des lignes** (l'ancienne base). Un refus n'écrit rien, pas même une trace. Sinon, chaque exécution laisse une ligne dans `ops.load_run` : commit, sha256 des journaux lus, décomptes, empreintes, durée, statut `ok` ou `failed`.

**Ce que fait `load`**, en une transaction :

1. listes de matchs API (dernière version) : compétitions, saisons, équipes, matchs ;
2. catalogue des détails et des profils : présences, collisions « même jour » et « deux naissances » ;
3. émission : compositions, statistiques joueurs et d'équipe, compteurs par équipe et par match ;
4. football-data : appariement (domicile, extérieur, date à ± 1 jour) dans les saisons couvertes par l'API ; création des matchs et des équipes « hors_api » ailleurs ;
5. `TRUNCATE` de `staging` (et, par cascade, des tables `features`), `COPY`, séquences recalées, empreintes.

Règles de chargement : voir la docstring de `src/foot_predictor/ingestion/load_api.py` (identifiant 0, équipe prise dans la composition, collisions, alias, scores, exclusions, dates de naissance).

## YAML de rapprochement (`src/foot_predictor/ingestion/mappings/`)

| Fichier | Contenu | Comment le mettre à jour |
|---|---|---|
| `competitions.yaml` | division football-data -> `league.id` | à la main (10 lignes) |
| `football_data_team_ids.yaml` | équipe football-data -> `team.id` ; `hors_api` ; `non_apparies` | `mapping_builder teams`, puis relecture du diff |
| `player_aliases.yaml` | doublon : identifiant secondaire -> principal | `mapping_builder player-aliases`, puis relecture du diff |
| `player_collisions.yaml` | exceptions à l'exclusion des collisions, avec preuve | à la main, preuve obligatoire (ADR-0020) |

```bash
uv run python -m foot_predictor.mapping_builder --raw-dir C:/foot-predictor/data/raw teams --external-raw-dir data/raw
uv run python -m foot_predictor.mapping_builder --raw-dir C:/foot-predictor/data/raw player-aliases
git diff src/foot_predictor/ingestion/mappings/
FP_RAW_DIR=C:/foot-predictor/data/raw uv run pytest -m raw   # chaque identifiant existe dans le brut
```

- Équipes : appariement **par le calendrier** (dates et côtés domicile ou extérieur), jamais par le nom. Toute correspondance incertaine reste dans `non_apparies`, avec sa raison (E-033).
- Alias : groupe retenu seulement si ses identifiants ne jouent jamais le même match ni le même jour. Le 2026-09-29 : 97 groupes, 65 retenus, 32 douteux laissés hors du fichier.
- Les YAML de joueurs contiennent des **identifiants API numériques**, jamais de nom ni de date de naissance (exception prévue par l'ADR-0008).

## Bruts externes (ADR-0023, ADR-0024)

- **football-data** : CSV tels que téléchargés, dans `C:/fp-travail/data/raw/football_data/csv/season=<année>/<division>__<horodatage>.csv`, journal `_manifest/football_data.jsonl`. 10 divisions (E0, E1, SP1, SP2, D1, D2, I1, I2, F1, F2), saisons 2000-01 à 2026-27 : 270 fichiers, téléchargés le 2026-09-29.
- **Understat** : écarté, son `robots.txt` refuse tout accès automatisé (ADR-0023).

```bash
uv run python -m foot_predictor.collect.football_data download --max-requests 300 --dry-run
uv run python -m foot_predictor.collect.football_data download --max-requests 300   # 1 requête par seconde au plus
uv run python -m foot_predictor.collect.football_data check                          # lignes et colonnes par fichier
```

Le collecteur refuse un dossier qui contient le brut API (`api_football/` ou `_queue/`), sauf `--allow-api-raw-dir` après le gel.

## Phase B : après la session de gel du 19 octobre (sur demande)

À ne lancer qu'une fois le tag `data-freeze-2026-10` posé et `C:/foot-predictor` mis à jour à l'étape 7 de `gel.md`.

```bash
# 2.10 Vérifications
cd /c/fp-travail && git fetch origin --tags && git tag -l data-freeze-2026-10 && git log -1 --oneline origin/main
git show origin/main:docs/DATA_FREEZE.md | head -20
cd /c/foot-predictor && git log -1 --oneline && uv run python -m foot_predictor.collect.api_football lock-status
schtasks //Query //FO TABLE | grep FootPredictor     # aucune ligne attendue (tâches supprimées)

# 2.10 Référentiel sur le brut définitif
cd /c/fp-travail && git switch --detach origin/main && uv sync --all-groups
APP_ENV=dev uv run python -m foot_predictor.ingestion load \
    --raw-dir C:/foot-predictor/data/raw --external-raw-dir data/raw --confirm-db foot_predictor_travail
APP_ENV=dev uv run python -m foot_predictor.ingestion check-referentiel   # appariement >= 99,5 %

# 2.10 Recopie des bruts externes vers le brut principal, avec vérification
uv run python -m foot_predictor.collect.api_football --raw-dir data/raw backup --dest C:/fp_bruts_externes_copie
#   puis copie de football_data/ et de _manifest/football_data.jsonl vers C:/foot-predictor/data/raw
#   (écriture dans C:/foot-predictor : sur accord), vérification :
uv run python -c "from foot_predictor.rawstore.backup import verify; r = verify(__import__('pathlib').Path('C:/foot-predictor/data/raw')); print(r.verified, r.ok, len(r.mismatched), len(r.missing))"

# 2.11 PR après gel : ruff et pre-commit sur les chemins gelés ; raw_check appelle ingestion/collisions.py
#      (résumé identique octet pour octet, hors date, sur le brut définitif : comparer avant et après)
# 2.12 Clôture : tag v0.3.0, ETAT_PROJET.md, docs/retours/partie-2_<date>.md
```

## Tests

```bash
uv run pytest tests/ingestion tests/mapping_builder tests/db -q
```

Brut synthétique (noms et identifiants fictifs), construit dans les tests à partir des constructeurs de `tests/quality/test_raw_check.py`. Il couvre l'identifiant 0, les statistiques inversées, les entrées répétées, les deux numéros (résolu ou non), les deux équipes, le même jour, les deux naissances, les corrections de date, les alias, le tapis vert, les lots incomplets et les versions multiples.
