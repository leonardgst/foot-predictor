# Étape 04 : référentiel reconstruit depuis le brut (jalon J3)

Mode d'emploi de `load` et de `check-referentiel`, des YAML de rapprochement et des bruts externes. Décisions : ADR-0008 (API-FOOTBALL fait foi pour les identifiants), ADR-0009 (cible et exclusions), ADR-0020 (collisions), ADR-0023 (sources externes), ADR-0024 (bruts externes), ADR-0025 (bases), ADR-0027 (périmètre des chargeurs).

## En bref

- `staging` n'est **jamais corrigé à la main** : il se reconstruit entièrement depuis le brut par `load`, et toute correction est un YAML de `src/foot_predictor/ingestion/mappings/` (ADR-0008, règle 4).
- Les entités (joueurs, entraîneurs, équipes, matchs) viennent des **identifiants API-FOOTBALL**. football-data ne crée jamais de joueur ; il s'apparie aux matchs API, et ne crée des matchs qu'hors de la couverture API.
- Deux chargements du même brut donnent les mêmes tables (empreintes md5 identiques, vérifié le 2026-09-29).
- Un brut **plus grand** décale des identifiants internes, attribués dans l'ordre des identifiants API : le 2026-10-19, les matchs API gardent le leur, mais les matchs « hors_api » sont décalés de 104 et 924 équipes sur 3 267 changent d'identifiant (E-058). Hors de `staging`, on rapproche par les identifiants API.
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
# Reconstruction complète (8 à 13 minutes sur le portable : 778 s le 2026-09-30, 493 s le 2026-10-19)
APP_ENV=dev uv run python -m foot_predictor.ingestion load \
    --raw-dir C:/foot-predictor/data/raw --external-raw-dir data/raw --confirm-db foot_predictor_travail

# Contrôle J3 : reports/data_quality/referentiel_<date>.md (versionné, chiffres seulement ;
# section 6 : recouvrement des tirs football-data et API, avant le scellé)
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
   tirs et tirs cadrés de football-data (`HS`, `HST`, `AS`, `AST`) par équipe dans `staging.team_match_stats_external`, vides si absents (migration 0005, ADR-0029) ;
   cotes plus/moins 2,5 dans `staging.match_odds`, une ligne par version (« avant clôture », « clôture ») quand une colonne est lisible, selon l'ordre de priorité de `ingestion/football_data_odds.py` (migration 0007, ADR-0036) ;
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

- **football-data** : CSV tels que téléchargés, dans `C:/fp-travail/data/raw/football_data/csv/season=<année>/<division>__<horodatage>.csv`, journal `_manifest/football_data.jsonl`. 10 divisions (E0, E1, SP1, SP2, D1, D2, I1, I2, F1, F2), saisons 2000-01 à 2026-27 : 270 fichiers, téléchargés le 2026-09-29, plus 1 fichier `fixtures/` (répétition du live, 2026-10-04).
- **Recopie dans le brut principal** (2026-10-19, phase B, 2.10) : `football_data/` (271 fichiers) et son journal sont aussi dans `C:/foot-predictor/data/raw`, aux sha256 vérifiés. C'est une **archive** du brut au gel. Le dossier du worktree reste le dossier de travail des bruts externes : `load` le lit par `--external-raw-dir data/raw`, et le collecteur live refuse un dossier qui contient le brut API (`collect/football_data/live.py`).
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
#   (fait le 2026-10-19 par un script ponctuel, sans le backup intermédiaire : voir « Résultats de 2.10 »)
uv run python -m foot_predictor.collect.api_football --raw-dir data/raw backup --dest C:/fp_bruts_externes_copie
#   puis copie de football_data/ et de _manifest/football_data.jsonl vers C:/foot-predictor/data/raw
#   (écriture dans C:/foot-predictor : sur accord), vérification :
uv run python -c "from foot_predictor.rawstore.backup import verify; r = verify(__import__('pathlib').Path('C:/foot-predictor/data/raw')); print(r.verified, r.ok, len(r.mismatched), len(r.missing))"

# 2.11 PR après gel : ruff et pre-commit sur les chemins gelés ; raw_check appelle ingestion/collisions.py
#      (résumé identique octet pour octet, hors date, sur le brut définitif : comparer avant et après)
#      fait le 2026-10-19 : voir « Résultats de 2.11 » ; raw_check écrit alors ailleurs que reports/ :
uv run python -m foot_predictor.quality.raw_check --raw-dir C:/foot-predictor/data/raw --output-dir <dossier temporaire>/avant
# 2.12 Clôture : tag v0.3.0, ETAT_PROJET.md, docs/retours/partie-2_<date>.md
```

### Résultats de 2.10 (2026-10-19)

- **Vérifications** : tag `data-freeze-2026-10` présent ; `main` en `546124d`, avec `DATA_FREEZE.md` ; `C:/foot-predictor` sur `546124d`, propre ; verrou libre ; aucune tâche `FootPredictor_*` ; base de travail en 0008.
- **`load` n° 6** (commit `546124d`) : code 0, 493 s ; 102 554 détails et 4 015 379 présences lus, comme au gel.

| Table | n° 5 (2026-09-30) | n° 6 (2026-10-19) | Écart |
|---|---|---|---|
| `match` | 167 876 | 167 980 | +104 (FA Cup +48, Copa del Rey +56) |
| `team` | 3 267 | 3 272 | +5 |
| `coach` | 3 622 | 3 652 | +30 |
| `player` | 67 012 | 67 113 | +101 |
| `team_match` | 335 752 | 335 960 | +208 |
| `team_match_stats` | 168 640 | 169 570 | +930 (détails arrivés depuis le 30/09) |
| `lineup` | 3 984 757 | 4 004 245 | +19 488 |
| `player_match_stats` | 2 831 343 | 2 850 869 | +19 526 |
| `match_source_mapping`, `team_match_stats_external`, `match_odds` | 102 397 ; 204 794 ; 120 983 | identiques | 0 (CSV inchangés) |

- **`check-referentiel`** (`reports/data_quality/referentiel_2026-10-19.md`) :
  - identité des joueurs OK (67 113 joueurs, autant d'identifiants API distincts) ;
  - appariement football-data **56 715 / 56 729 (99,98 %)**, seuil 99,5 % : OK, identique au 30/09 ; 14 non appariés avant le scellé, 0 après ;
  - entrées exclues : 812 (compositions) et 929 (statistiques) ; top 5 : 41 matchs sur 29 261 (0,14 %, seuil 1 %) ;
  - entrées sans identifiant : 1 310 et 1 995 (1 007 et 1 680 le 30/09) ;
  - tirs (avant le scellé) identiques ; cotes 2026-27 : présence en baisse, les CSV datant du 29/09 (présence seulement).
- **Identifiants internes** (photo avant et après, lecture seule ; matchs d'avant le 1er juillet 2025 seulement) :
  - inchangés : compétitions, saisons et les 104 917 matchs API ;
  - décalés : les 45 682 matchs « hors_api » (+104), 924 équipes sur 3 267 (dont 9 sur 218 dans le top 5), 3 461 entraîneurs sur 3 622, 65 236 joueurs sur 67 012 ;
  - `ops.prediction` (78 lignes de rejeu) : `match_id` toujours justes, `api_fixture_id` vide partout, 1 équipe à domicile qui désigne désormais une autre équipe (E-058).
- **Recopie** :
  - source vérifiée : 271 fichiers au journal et sur le disque, sha256 conformes ;
  - script ponctuel sous le verrou de collecte du brut principal, qui refuse d'écraser (`copytree` vers un dossier absent, journal ouvert en création exclusive) ;
  - `verify` : **17 607** fichiers vérifiés (17 336 + 271), 0 différent, 0 absent ; journal API inchangé (sha256 `38c111a0…`) ; journal football-data identique à la source (`3b2fc1fe…`) ;
  - pas de `backup` intermédiaire : il n'aurait laissé qu'un dossier à supprimer, la vérification de la source donne la même garantie, et une copie existe déjà sur `D:` (`copies-2026-10-19/`).

### Résultats de 2.11 (2026-10-19)

Chemins gelés jusqu'au gel : `collect/api_football/`, `rawstore/`, `quality/raw_check.py`, `scripts/taches_planifiees/` et leurs tests. Règle 3 tenue jusqu'au bout : aucun diff sur ces chemins entre `v0.2.0` et `3f1e834`.

- **ruff et pre-commit** sur ces chemins :
  - 34 corrections automatiques (`dt.timezone.utc` → `dt.UTC`, imports triés) et 4 à la main (B007, E741) ;
  - formatage de 37 fichiers : arbre syntaxique identique avant et après, fichier par fichier ; commit ajouté à `.git-blame-ignore-revs` ;
  - exclusions retirées de `pyproject.toml` (restent les migrations 0001 à 0003) : `ruff check .` et `ruff format --check .` verts sur les 407 fichiers.
- **`raw_check` appelle `ingestion/collisions.py`** (ADR-0020) : `classify_match`, `same_day_collisions`, `classify_births`. Sur le brut définitif (`--output-dir` hors de `reports/`, pour ne pas écraser le résumé du gel), avant et après :
  - résumé (1 562 lignes) et détails (54 230 lignes) **identiques octet pour octet**, hors la ligne « Généré le » ;
  - les détails, qui contiennent des valeurs de matchs, n'ont été comparés que par un script qui ne donne que les numéros des lignes différentes ;
  - ancienne et nouvelle `same_day_groups` identiques sur 2 000 tirages aléatoires ;
  - effet de la recopie de 2.10, seul écart avec le résumé du gel : intégrité sur 17 607 fichiers au lieu de 17 336.
- **E-036** corrigé (`test_freeze`) : 12 exécutions de suite réussies, test de non-régression.
- **E-052** corrigé : `download.py` vise le domaine sans `www`.

## Tests

```bash
uv run pytest tests/ingestion tests/mapping_builder tests/db -q
```

Brut synthétique (noms et identifiants fictifs), construit dans les tests à partir des constructeurs de `tests/quality/test_raw_check.py`. Il couvre l'identifiant 0, les statistiques inversées, les entrées répétées, les deux numéros (résolu ou non), les deux équipes, le même jour, les deux naissances, les corrections de date, les alias, le tapis vert, les lots incomplets et les versions multiples.
