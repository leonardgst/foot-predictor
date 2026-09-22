# Récap projet — foot-predictor

Mémoire de référence unique du projet. Ce document consolide tous les récaps précédents (décisions de cadrage, mise en place Git/Docker, infra, schéma de tables, pipeline d'ingestion, abandon de Transfermarkt, conception du MVS, debug Understat, prochaine étape clustering). Il reflète l'**état actuel** : quand une décision initiale a été révisée, seule la version en vigueur est décrite, et l'historique des révisions est regroupé en section 1.

Pour le « pourquoi » du projet, voir `OBJECTIFS.md`. Pour l'état d'avancement rapide, voir `../README.md`.

---

## Sommaire

1. [Décisions révisées en cours de route](#1-décisions-révisées-en-cours-de-route)
2. [Cadrage et décisions produit](#2-cadrage-et-décisions-produit)
3. [Données retenues et sources](#3-données-retenues-et-sources)
4. [Abandon de Transfermarkt et Market Value Score](#4-abandon-de-transfermarkt-et-market-value-score)
5. [Architecture du SI et stack technique](#5-architecture-du-si-et-stack-technique)
6. [Schéma de base de données (22 tables)](#6-schéma-de-base-de-données-22-tables)
7. [Pipeline d'ingestion](#7-pipeline-dingestion)
8. [Règles de calcul des features](#8-règles-de-calcul-des-features)
9. [Incidents rencontrés et résolutions](#9-incidents-rencontrés-et-résolutions)
10. [Prochaine étape : clustering de style + MVS (Performance)](#10-prochaine-étape--clustering-de-style--mvs-performance)
11. [Points ouverts et backlog](#11-points-ouverts-et-backlog)
12. [Leçons apprises](#12-leçons-apprises)

---

## 1. Décisions révisées en cours de route

Les documents anciens contiennent des choix aujourd'hui périmés. Tableau de correspondance pour ne pas se tromper :

| Sujet | Décision initiale | Décision en vigueur | Raison |
|---|---|---|---|
| Source des compositions | Transfermarkt (scraping) | **API-Football** (`/fixtures?id=`) | Scraping Transfermarkt interdit (CGU + robots.txt) |
| Valeur marchande / « masse salariale » | Valeur marchande Transfermarkt sommée sur l'effectif | **Market Value Score (MVS)** maison, 0-100 | Idem ; aucune donnée de transfert légale disponible |
| `squad_valuation_eur` | Colonne de `team_match_features` | **Supprimée** (migration 0003) | Dépendait de Transfermarkt |
| Classement | Table `staging.standing` scrapée | **Calculé** depuis `team_match`, stocké en `features` | Moins de travail, plus fiable |
| Groupes de poste (MVS) | 8 groupes manuels | **3 groupes** (Defender / Midfielder / Attacker) + sous-styles détectés par clustering | API-Football ne fournit que 4 catégories brutes |
| Port Postgres dev | 5432 | **5440** | Une installation Postgres native occupait 5432 (voir section 9) |
| Postgres natif Windows | « Non utilisé pour ce projet » | Il tournait en réalité en arrière-plan | Cause d'un conflit de port |

---

## 2. Cadrage et décisions produit

- **Objectif fonctionnel** : prédire le résultat d'un match avant qu'il soit joué.
- **Objectif réel** : projet pédagogique end-to-end de data science (voir `OBJECTIFS.md`).
- **Produit visé** : application listant les prochains matchs, avec un bouton **« Prédire »** par match, grisé tant que les données nécessaires manquent, puis dégrisé avec affichage d'un tableau de variables de prédiction.
- **Compétitions** : quelques grands championnats européens (pas un seul, pas tous). Actuellement 5 : Premier League, La Liga, Bundesliga, Serie A, Ligue 1.
- **Sortie du modèle** : **score exact** (buts A / buts B), dont on dérive le 1N2 et des probabilités précises.
- **Budget** : sources gratuites en priorité, scraping léger accepté **seulement s'il est légal**. Pas de budget pour des API payantes (exception à revoir : abonnement API-Football, voir section 11).

### Décision UX critique : disponibilité de la prédiction

- Les compositions officielles ne sont connues que ~1h avant le coup d'envoi.
- Le bouton « Prédire » reste **grisé tant que la composition officielle n'est pas publiée**.
- **Pas de mode « estimation avec composition probable » en V1.**
- Le statut de disponibilité est donc un **booléen simple** (compo officielle publiée oui/non), pas une logique à plusieurs niveaux de confiance.

### Blessures / suspensions

Non incluses dans le modèle en V1. Les blessures sont toutefois capturées en `raw` (`raw.api_football_injuries`) et servent à la composante Disponibilité du MVS.

---

## 3. Données retenues et sources

### Variables de la V1

| Catégorie | Détail | Fenêtre de calcul |
|---|---|---|
| Calendrier | Matchs passés et à venir | — |
| Compositions | Onze de départ (historique + officiel à venir) | — |
| **Stabilité de l'effectif** | Score de cohésion du onze, basé sur une matrice cumulée de co-apparitions par paires de joueurs (méthodologie du mémoire de stage) | Cumulatif depuis le 1er match de la saison, reset chaque saison |
| Effectif / valeur | Remplacé par le **MVS** (section 4) | Snapshot à date de match |
| Âge | Calculé à partir de `birth_date` à la date du match | — |
| Classement | Position, points, différence de buts | Snapshot **strictement avant** le match |
| Forme récente | Points pris | 10 derniers matchs, même contexte dom./ext. |
| Buts marqués / encaissés | Séparés domicile / extérieur | 10 derniers matchs, même contexte |
| xG marqués / encaissés | Séparés domicile / extérieur | **5** derniers matchs, même contexte |

### Sources retenues

| Source | Fournit | Accès |
|---|---|---|
| **football-data.co.uk** | Résultats historiques, cotes | CSV téléchargés |
| **Understat** | xG par équipe, xG / xA / npxG par joueur et par match | Scraping léger |
| **API-Football** (`v3.football.api-sports.io`) | Compositions, stats par joueur et par match, blessures | API, header `x-apisports-key`, variable `API_FOOTBALL_KEY` (lue via `os.environ`, hors `pydantic-settings`) |

Point technique clé sur API-Football : l'endpoint `/fixtures?id={id}` renvoie **en un seul appel** compositions + stats par joueur + événements (coût quota divisé par ~2). À l'inverse, `/players?league=&season=` coûterait ~125 appels pour les 5 championnats, d'où une collecte **par match**. Plan gratuit : 100 requêtes/jour, reset 00:00 UTC.

---

## 4. Abandon de Transfermarkt et Market Value Score

### Constat

Transfermarkt interdit explicitement le scraping automatisé :

- **CGU** : interdiction explicite.
- **robots.txt** : confirmé en direct, un outil de récupération web a refusé l'accès pour cette raison.

### Options écartées

| Option | Verdict |
|---|---|
| Scraper quand même (requests + BeautifulSoup) | Abandonné : risque juridique refusé (droit sui generis des bases de données en UE, distinct du simple blocage IP) |
| Wrappers « API Transfermarkt » (`felipeall/transfermarkt-api`, offres payantes Zyla / Apify / Parse.bot) | Tous font le même scraping en coulisses, avec ou sans facturation. Vérifié dans le code et la doc. Pas une alternative légale |
| Datasets Kaggle (`transfermarkt-datasets` et similaires) | Même provenance (scraping par un tiers), en plus d'être figés |
| CIES Football Observatory | Seule source réellement indépendante (régression sur ~2400 transferts réels), mais pas d'API self-service, tarif non public, probablement B2B |

### Décision : construire un MVS maison

Score composite **0-100** calculé à partir de statistiques sportives légales (API-Football + Understat), sur le même principe que la méthodologie publique du CIES.

**Limite assumée** : aucun dataset de transferts réels n'est utilisable pour calibrer (tous remontent à Transfermarkt). Le MVS est donc un **score à dire d'expert** (pondérations manuelles), **pas un modèle supervisé** calibré sur des prix réels.

```
MVS = 0.35 × Performance + 0.25 × Potentiel + 0.15 × Réputation
    + 0.10 × NiveauChampionnat + 0.10 × Disponibilité + 0.05 × Expérience
```

| Composante | Source de calcul | Statut |
|---|---|---|
| Performance | Clustering de style + percentiles (section 10) | Spécifiée (section 10), bloquée par le backfill `player_match_stats` |
| Potentiel | Âge (`staging.player.birth_date`) | Implémentée : `market_value/components/potential.py` |
| Réputation | Niveau du club (`features.team_match_features.standing_position`) | Implémentée : `market_value/components/reputation.py` |
| Niveau championnat | Compétition du joueur | À spécifier (section 11) |
| Disponibilité | `staging.player_injury` | À spécifier (section 11) |
| Expérience | Minutes / matchs cumulés | À spécifier (section 11) |

Potentiel et Réputation sont des calculs directs à dire d'expert (pas de ML,
pas de calibration possible faute de données de transferts réelles, cf.
plus haut) : courbe âge -> score pour Potentiel, mapping linéaire de la
position au classement pour Réputation. Les 3 composantes restantes
(Niveau championnat, Disponibilité, Expérience) nécessitent des données pas
encore disponibles (cf. section 11).

### Cadrage actés pour le MVS

- **Fenêtre** : glissante sur les **50 derniers matchs** du joueur (pas un cumul saison).
- **Gardiens** : hors périmètre V1 (vecteur de style trop différent ; modèle séparé en V2 : arrêts, buts encaissés vs attendus).
- **Anti-fuite** : chaque calcul est ancré à une `as_of_date` et n'utilise que des matchs strictement antérieurs.

---

## 5. Architecture du SI et stack technique

### Architecture en couches (bronze / silver / gold)

1. **`raw`** : copie fidèle des données récupérées, sans transformation, pour pouvoir rejouer le pipeline si la logique de nettoyage change.
2. **`staging`** : réconciliation des identifiants entre sources, référentiels stables (équipes, joueurs, compétitions), typage, gestion des valeurs manquantes.
3. **`features`** : variables prêtes pour le modèle. Le modèle ne consomme **que** cette couche, jamais le brut (évite le training-serving skew).

**Vigilance transversale** : gestion stricte de la temporalité. Chaque ligne de `features` reflète l'état des données disponibles **strictement avant** le match (pas de data leakage).

### Stack

| Aspect | Choix | Justification |
|---|---|---|
| Base de données | PostgreSQL | Relationnel, données structurées liées |
| Environnements | 3 bases distinctes : dev, test, prod | Isolation complète |
| Dev / test | Docker Compose, **deux conteneurs séparés** | Reset facile, reproductible, versionné |
| Prod | **Neon** (Postgres serverless, tier gratuit) | Branching natif pour tester les migrations |
| Schémas | `raw`, `staging`, `features` (dans chaque base) | Reflète les 3 couches |
| Migrations | SQLAlchemy + Alembic | Historique versionné, rejouable dev → test → prod |
| Python | `uv` | Gestion rapide des dépendances |
| Config | `.env.dev` / `.env.test` / `.env.prod` (non commités) + `pydantic-settings`, bascule via `APP_ENV` | — |
| Éditeur | VSCode + SQLTools | Exploration des 3 bases |
| Versioning | Git | `main` ↔ prod, `dev` ↔ test, `feature/*` ↔ dev quotidien |

Dépendances actuelles : `sqlalchemy`, `alembic`, `psycopg[binary]`, `pydantic-settings`, `pyyaml`, `requests`, `understatapi`, et pour `market_value/` : `pandas`, `numpy`, `scikit-learn`, `hdbscan`, `joblib`. Le `pyproject.toml` déclare le layout `src/` via `[tool.hatch.build.targets.wheel] packages = ["src/foot_predictor"]`.

### Environnements

| Environnement | Conteneur | Port hôte | Base | Config |
|---|---|---|---|---|
| Dev | `foot-predictor-dev` | **5440** | `foot_predictor_dev` | `.env.dev` |
| Test | `foot-predictor-test` | 5433 | `foot_predictor_test` | `.env.test` |
| Prod | Hors Docker (Neon) | — | Neon | `.env.prod` (`sslmode=require`, connexion directe non-pooled) |

- Volumes Docker persistants (`pg_dev_data`, `pg_test_data`), réinitialisables via `docker compose down -v`.
- `.env.example` commité avec des valeurs `changeme`, à mettre à jour avec `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_SSLMODE`.
- `.gitignore` créé **avant** les fichiers `.env.*` pour ne jamais committer de secrets.

### Git / GitHub

- Dépôt privé : `github.com/leonardgst/foot-predictor`.
- Branches `main` et `dev` poussées, trackent `origin/*`.
- Travail quotidien sur `feature/xxx` créées depuis `dev`, mergées dans `dev`. `dev` est mergée dans `main` seulement quand une version est stable pour la prod.

### Structure du projet

```
foot-predictor/
├── .env.dev / .env.test / .env.prod   (non commités)
├── .env.example                        (commité)
├── .gitignore
├── pyproject.toml / uv.lock
├── docker-compose.yml
├── alembic.ini
├── migrations/versions/                (0001, 0002, 0003…)
├── scripts/one_off/                    (check_raw.py, check_duplicates.py, fusion.py, check_merged_teams_xg.sql)
├── src/foot_predictor/
│   ├── config.py
│   ├── db/ (models.py, session.py)
│   ├── ingestion/
│   ├── features/
│   └── market_value/
└── tests/
```

### Workflow de migration

```bash
APP_ENV=dev  uv run alembic revision --autogenerate -m "message"
APP_ENV=dev  uv run alembic upgrade head     # test en local
APP_ENV=test uv run alembic upgrade head     # validation
APP_ENV=prod uv run alembic upgrade head     # déploiement (Neon)
```

Migrations appliquées avec succès sur dev, test et prod : `0001_create_schemas`, puis 0002 (tables) et `0003_market_value_score`.

---

## 6. Schéma de base de données (22 tables)

| Schéma | Rôle | Tables |
|---|---|---|
| `raw` | Copie fidèle par source, jsonb | 6 |
| `staging` | Référentiel réconcilié, typé | 13 |
| `features` | Variables calculées pour le modèle | 3 |

### 6.1 `raw` — copie fidèle par source

Pas de FK vers d'autres tables raw, pas de typage strict : le payload est en `jsonb` pour rester résilient aux changements de format des sources (c'est `staging` qui impose la structure stricte).

```
raw.source_ingestion_log           -- traçabilité de chaque run
├── id, source_name ('football-data' | 'understat' | 'api-football'…)
├── ingested_at, payload_ref (fichier / URL), status ('success' | 'failed')

raw.football_data_match            -- résultats + cotes            (id, ingestion_id FK, raw_payload jsonb, ingested_at)
raw.understat_match_stats          -- xG équipe par match          (idem)
raw.api_football_fixture_detail    -- compos + stats joueurs par match, capture quasi verbatim (idem)
raw.understat_player_match         -- xG / xA par joueur et match  (idem)
raw.api_football_injuries          -- blessures, pas encore consommée en staging (idem)
```

### 6.2 `staging` — référentiel réconcilié

**Principes de conception**

- Granularité `(match, équipe)` dans `team_match`, avec un booléen `is_home` dénormalisé mais généré uniquement par le pipeline (pas de risque de désynchronisation). C'est la table de base des agrégations glissantes.
- Réconciliation multi-sources par **table de mapping dédiée par entité** (pas de table polymorphe, pour garder de vraies FK) : chaque table a `UNIQUE(source_name, source_ref)` et une FK vers l'entité interne.
- Compositions dans une table normalisée `lineup` (une ligne par joueur, match, équipe), plus exploitable que du JSON pour les paires de joueurs.
- `lineup.position` en **texte libre** (pas d'enum) : les sources n'ont pas la même granularité, une position normalisée pourra être dérivée plus tard en `features`.

```
staging.competition                 id PK, name, country, created_at
staging.competition_source_mapping  id PK, competition_id FK, source_name, source_ref — UNIQUE(source_name, source_ref)
staging.season                      id PK, competition_id FK, label ('2024-2025'), start_date, end_date

staging.team                        id PK, name, country, created_at
staging.team_source_mapping         id PK, team_id FK, source_name, source_ref — UNIQUE(source_name, source_ref)

staging.player                      id PK, full_name, birth_date, nationality, created_at
staging.player_source_mapping       id PK, player_id FK, source_name, source_ref — UNIQUE(source_name, source_ref)

staging.match
├── id PK, competition_id FK, season_id FK, match_date timestamptz
├── home_team_id FK, away_team_id FK
├── home_goals smallint NULL, away_goals smallint NULL      -- NULL tant que pas joué
├── status enum ('scheduled' | 'played' | 'postponed' | 'cancelled')
└── created_at
staging.match_source_mapping        id PK, match_id FK, source_name, source_ref — UNIQUE(source_name, source_ref)

staging.team_match                  -- une ligne par (match, équipe)
├── id PK, match_id FK, team_id FK, is_home boolean
├── goals_for, goals_against smallint NULL
├── xg_for, xg_against numeric(4,2) NULL
├── created_at
└── UNIQUE(match_id, team_id)

staging.lineup                      -- composition normalisée
├── id PK, match_id FK, team_id FK, player_id FK
├── started boolean, position text NULL, created_at
└── UNIQUE(match_id, team_id, player_id)

staging.player_match_stats          -- une ligne par (match, joueur), pivot du MVS
├── match_id, player_id, team_id
├── minutes, rating, position_bucket ∈ {Goalkeeper, Defender, Midfielder, Attacker}
├── goals, assists, shots, shots_on_target, key_passes, pass_accuracy_pct
├── tackles, interceptions, duels_total, duels_won
├── dribbles_attempts, dribbles_success, dribbled_past
├── fouls_drawn, fouls_committed, yellow_cards, red_cards
└── xg, xa, npxg                    -- NULL tant qu'Understat n'est pas ingéré pour ce match

staging.player_injury               -- périodes d'indisponibilité (composante Disponibilité du MVS)
```

**Supprimées / non créées**

- `staging.standing` : retirée, classement calculé en `features`.
- `staging.player_team_season` : non créée (indicateurs calculables depuis `lineup` + `team_match`). Pourra être ajoutée si besoin (ex. profondeur de banc).
- `staging.player_valuation` : supprimée avec l'abandon de Transfermarkt.

### 6.3 `features` — variables prêtes pour le modèle

**Choix** : une seule **table large** `team_match_features` (une ligne par `team_match`, toutes les variables en colonnes) plutôt qu'une table par famille. Un seul `SELECT` pour construire le dataset d'entraînement, au prix d'une table qui s'élargira.

```
features.team_match_features
├── id PK, team_match_id FK → staging.team_match (UNIQUE)
├── match_id FK, team_id FK           -- dénormalisés pour filtrage / jointures
├── computed_at
│
├── form_points_last10           smallint
├── form_matches_count           smallint       -- matchs réellement dispos (<10 en début de saison)
├── goals_for_last10             numeric(4,2)
├── goals_against_last10         numeric(4,2)
│
├── xg_for_last5                 numeric(4,2)
├── xg_against_last5             numeric(4,2)
├── xg_matches_count_last5       smallint       -- comptage dédié (fenêtre 5 ≠ 10)
│
├── standing_position            smallint
├── standing_points              smallint
├── standing_goal_diff           smallint
│
├── squad_avg_age                numeric(4,2)
└── squad_stability_score_season numeric(5,4)   -- score 0-1, reset par saison
```

(`squad_valuation_eur` supprimée, voir section 1.)

```
features.player_style_profile       -- cluster de style par joueur et as_of_date
└── player_id, as_of_date, position_bucket, cluster_id, cluster_label, matches_in_window (≤50), computed_at

features.player_market_value_score  -- score composite par joueur et as_of_date
└── player_id, as_of_date, performance_score, potential_score, reputation_score,
    league_score, availability_score, experience_score, mvs_total
```

Le nom `squad_stability_score_season` laisse la place à une future colonne `squad_stability_score_alltime` (cumul sans reset annuel) sans renommage. Cette évolution est prévue mais **pas en V1**.

---

## 7. Pipeline d'ingestion

### Ordre d'exécution (testé contre un vrai Postgres)

| # | Script | Rôle |
|---|---|---|
| 1 | `football_data_scraper.py` | Télécharge les CSV football-data.co.uk → `raw.football_data_match` |
| 2 | `football_data.py` | `raw → staging` : crée `match`, `team_match`, `competition`, `season`, `team` |
| 3 | `api_football_scraper.py` | Télécharge `/fixtures?id=` → `raw.api_football_fixture_detail` |
| 4 | `api_football.py` | `raw → staging` : `lineup` + `player_match_stats` (2 fonctions distinctes) |
| 5 | `understat_scraper.py` | Télécharge xG équipe par match → `raw.understat_match_stats` |
| 6 | `understat.py` | `raw → staging` : met à jour `team_match.xg_for` / `xg_against` |
| 7 | `understat_player_scraper.py` | Télécharge xG / xA par joueur et match → `raw.understat_player_match` |
| 8 | `understat_player.py` | `raw → staging` : complète `player_match_stats.xg` / `xa` / `npxg` |

Exemple de lancement : `APP_ENV=dev uv run python -m foot_predictor.ingestion.understat`.

### Principes communs (`ingestion/common.py`)

- **Réconciliation d'équipe** : mapping manuel par source (`mappings/*_teams.yaml`). Une entité « nouvelle » pour une source est reliée à l'entité canonique existante par nom.
- **Réconciliation de joueur** : par `(nom complet, date de naissance)` quand disponible, par nom seul sinon (API-Football et Understat ne fournissent pas la date de naissance à ce niveau). Risque d'homonymes assumé et documenté dans chaque script.
- **Réconciliation de match cross-source** : la première source qui voit un match le crée ; les suivantes le retrouvent via un mapping enregistré ou par clé naturelle (équipes + date), sans jamais créer de doublon. Tolérance de date de **±1 jour** (fuseaux horaires).
- **Idempotence systématique** : tous les scripts peuvent être relancés sans dupliquer ni perdre de données (upsert avec comparaison de contenu).

### État actuel des volumes

Après ingestion football-data + Understat (niveau équipe) : 306 / 380 / 306 / 380 / 380 matchs par compétition, **1752 lignes de xG équipe traitées, 0 ignorée**. Les ingestions API-Football n'ont **pas encore été lancées** (abonnement payant non pris).

---

## 8. Règles de calcul des features

- **Forme récente et buts** : moyenne glissante sur les **10 derniers matchs**, filtrés sur le **même contexte domicile / extérieur** que le match à prédire, **toutes compétitions confondues** (les grands championnats n'ont pas assez de matchs dom./ext. si on se limite à une compétition).
- **xG** : même logique de contexte, mais fenêtre plus courte de **5 matchs** (le xG est plus volatile). Comptage dédié, séparé de celui de la forme / buts.
- **Classement** : calculé depuis `staging.team_match`, snapshot **strictement avant la date du match**, dans la compétition du match.
- **Âge d'effectif** : calculé à la date du match à partir de `birth_date`.
- **Stabilité d'effectif** : voir ci-dessous.
- **Valeur d'équipe** : ancien mécanisme (dernière valeur Transfermarkt avant match) supprimé. Remplaçant à définir (voir section 11).

### Indicateur de stabilité d'effectif (source : mémoire de stage)

Pour chaque équipe, sur une saison donnée (reset à chaque nouveau championnat) :

1. Matrice symétrique joueur × joueur : `1` si les deux joueurs ont débuté ensemble sur un match, `0` sinon (diagonale à 0).
2. Cette matrice est **cumulée match après match** (calcul stateful, séquentiel, dans l'ordre chronologique).
3. Pour un match donné, on restreint la matrice cumulée aux 11 titulaires, on somme, et on normalise par le score maximum théorique : `110 × nombre de matchs joués`.
4. Résultat : un score entre 0 et 1 par équipe et par match.

Dans le mémoire, cet indicateur combiné à la différence de masse salariale et d'âge (régression logistique, victoire binaire) donnait un **odds ratio de 5,32** pour la stabilité, signal jugé solide. Le modèle du mémoire n'était qu'un exemple de méthodologie : **le modèle actuel est reconstruit de zéro**.

---

## 9. Incidents rencontrés et résolutions

### 9.1 Infra (étape 1)

**Conflit de port 5432** : une installation PostgreSQL native (Windows) tournait en arrière-plan et occupait le port 5432. SQLTools se connectait à ce serveur au lieu du conteneur Docker, d'où des `password authentication failed` malgré des identifiants corrects.

- **Diagnostic clé** : arrêter le conteneur supposé cible. Si l'erreur reste une erreur Postgres (`password authentication failed`) plutôt que `connection refused`, un autre serveur répond sur ce port.
- **Résolution** : port dev mappé sur `5440:5432` dans `docker-compose.yml`, `POSTGRES_PORT=5440` dans `.env.dev`.
- Recommandé : désactiver le service Windows `postgresql-x64-XX` (`services.msc`).

| Incident | Cause | Correction |
|---|---|---|
| `password authentication failed` persistant après reset du volume | Volume `pg_dev_data` pas réellement supprimé avant `up` | Toujours : `stop` → `rm -f` → `volume rm` → `up`. Vérifier via `docker logs` la présence de `running bootstrap script` |
| SQLTools : connexion invisible / `Received null` sur le mot de passe | Connexions résiduelles dans les settings VSCode (user **et** workspace) + credentials en cache dans le Gestionnaire d'identifiants Windows | Vider `sqltools.connections` dans les deux settings + nettoyer le Gestionnaire d'identifiants + `Developer: Reload Window` |
| `uv add` → `Project is missing a [project] table` | `pyproject.toml` vide | `rm pyproject.toml` puis `uv init --no-readme` |
| `alembic init migrations` → `Directory already exists` | Dossier `migrations/versions/` déjà présent | Déplacer `versions/` hors de `migrations/`, lancer `alembic init`, remettre `versions/` |
| `ModuleNotFoundError: foot_predictor` à `alembic upgrade head` | `prepend_sys_path` pointait sur `.` au lieu de `src` | `prepend_sys_path = src` dans `alembic.ini` + vérifier `src/foot_predictor/__init__.py` |
| `pydantic_core.ValidationError: postgres_user Field required` alors que la variable existe | Fichier `.env` en **UTF-8 with BOM** (corrompt le nom de la 1re variable) | Ré-enregistrer en **UTF-8 sans BOM** (`.env.dev`, `.env.test`, `.env.prod`) |

### 9.2 Migrations et schéma (étape 3)

- Type enum Postgres créé deux fois (une explicitement, une automatiquement par `create_table`) → retrait de la création explicite.
- Revision id Alembic trop long (`varchar(32)` dépassé) → raccourci.
- `pyproject.toml` de `uv init` sans layout `src/` → ajout de `[tool.hatch.build.targets.wheel]`.
- Dépendance `pyyaml` manquante → ajoutée.

### 9.3 Debug ingestion Understat (568 → 0 ligne ignorée)

**Symptôme** : `understat.py` traitait 1184 lignes dont **568 ignorées** (~32 %, match / `team_match` introuvable).

| # | Hypothèse | Verdict |
|---|---|---|
| 1 | Noms Understat avec underscore (`Manchester_United`) non normalisés | ❌ Écartée (aucune équipe avec `_` en base). Fix de normalisation gardé par précaution |
| 2 | Écart de couverture saison / compétition entre sources | ❌ Écartée (volumes identiques) |
| 3 | Décalage de date (fuseau horaire) | ✅ Confirmée mais marginale (2 cas sur 1752) |
| 4 | Équipes dupliquées suite à un mapping YAML corrigé après coup | ✅ **Cause principale** : 19 doublons |

**Mécanisme de la cause racine.** `get_or_create_team()` cherche d'abord dans `TeamSourceMapping (source_name, source_ref)` et, si trouvé, renvoie l'id **sans reconsulter le YAML**. Sinon seulement, il applique le YAML, crée l'équipe et enregistre le mapping.

1. Premier run de `football_data.py` : l'entrée YAML manquait (ex. `Ath Bilbao`, commentaire « à confirmer ») → fallback sur le nom brut → équipe créée avec ce nom brut → mapping enregistré **définitivement**.
2. Le YAML est corrigé ensuite, mais relancer `football_data.py` ne change rien : le mapping existant est trouvé en premier.
3. `understat.py`, sans mapping préexistant, applique son YAML correct → crée une **seconde** équipe sous le nom canonique.
4. Les deux id ne se recoupent jamais → tous les matchs du club échouent à la résolution cross-source.

**19 doublons** (nom brut = 34-38 matchs, nom canonique = 0) :

| Championnat | Clubs concernés |
|---|---|
| La Liga (7) | Atletico Madrid, Athletic Club, Celta Vigo, Rayo Vallecano, Real Betis, Real Sociedad, Real Valladolid |
| Bundesliga (9) | Bayer Leverkusen, Borussia Dortmund, Borussia Monchengladbach, Eintracht Frankfurt, FSV Mainz 05, VfB Stuttgart, 1899 Hoffenheim, VfL Bochum, VfL Wolfsburg |
| Serie A (2) | Parma Calcio 1913, Hellas Verona |
| Ligue 1 (1) | Stade Brestois 29 |
| Premier League | Aucun (mapping correct dès le premier run) |

**Correction** : script de fusion (`fusion.py`, dry-run par défaut) qui identifie l'id portant les données (`keep_id`) et l'id vide (`drop_id`), reroute les `TeamSourceMapping`, supprime l'équipe vide et renomme l'équipe conservée. Garde-fou : si les **deux** côtés ont des données, il logue un conflit et **ne fusionne pas**. Résultat : **19 fusions appliquées, aucun conflit**.

**Reste : 2 décalages de date de ±1 jour** (probable écart UTC / heure locale) :

| Match | Date Understat | Date en staging |
|---|---|---|
| St. Pauli - Holstein Kiel | 2024-11-30 | 2024-11-29 |
| Genoa - Atalanta | 2025-05-18 | 2025-05-17 |

**Fix** : dans `resolve_match_cross_source()`, la comparaison stricte de date est remplacée par une tolérance de ±1 jour (`.between(date_min, date_max)`).

⚠️ **Vigilance** : cette tolérance poserait problème si une même paire d'équipes se rencontrait deux fois à moins de 2 jours (championnat + coupe nationale la même semaine). Non problématique aujourd'hui (championnats uniquement), à surveiller si les coupes sont ajoutées.

**Fichiers modifiés** : `common.py` (normalisation underscore, tolérance ±1 jour), `understat.py` (normalisation, instrumentation diagnostic temporaire), `understat_player.py` (même normalisation, partage `get_or_create_team`).

**Scripts one-off conservés** (`scripts/one_off/`) : `check_raw.py` (valeurs brutes réellement stockées vs YAML), `check_duplicates.py` (détection des paires brut / canonique avec comptage de références), `fusion.py`.

---

## 10. Prochaine étape : clustering de style + MVS (Performance)

**Statut** : le code du module `market_value/` est écrit et committé sur `dev`, mais **non exécuté sur de vraies données** (bloqué par l'absence de `player_match_stats`, donc par l'abonnement API-Football).

### 10.1 Périmètre

- **Joueurs de champ uniquement** : filtrer `position_bucket != 'Goalkeeper'` dès le départ.
- **3 clusterings indépendants** : `Defender`, `Midfielder`, `Attacker`. Jamais de comparaison entre groupes.
- Les sous-styles (ailier créateur vs finisseur…) sont **détectés par le clustering**, pas étiquetés en amont.

### 10.2 Fenêtre et anti-fuite

- Fenêtre des **50 derniers matchs joués** par le joueur.
- Ancrage à une `as_of_date` : on n'utilise que les lignes de `player_match_stats` dont `match.match_date < as_of_date` (jointure avec `staging.match`). Jamais de match futur.
- **Garde-fou** : sous ~10-15 matchs disponibles, le clustering / percentile est bruité. Prévoir un seuil minimum (pas de score avant N matchs) ou une pondération réduite documentée.

### 10.3 Pipeline de calcul

**Étape 1 : extraction par 90 minutes.** `valeur × 90 / minutes`, en excluant les lignes à minutes très faibles (ex. `minutes >= 20` par match).

Variables du vecteur de style :
```
goals_per90, assists_per90, shots_per90, shots_on_target_per90
key_passes_per90, xg_per90, xa_per90, npxg_per90
tackles_per90, interceptions_per90
duels_won_pct (= duels_won / duels_total, déjà un ratio)
dribbles_success_per90, dribbled_past_per90
fouls_drawn_per90, fouls_committed_per90
pass_accuracy_pct (déjà un pourcentage)
```

À **ne pas** inclure : âge, minutes jouées, nombre de matchs (le clustering porte sur le style, pas le volume). Non disponibles (stats Opta / StatsBomb, à remplacer par un proxy si besoin) : touches in box, progressive carries, progressive passes received.

**Étape 2 : normalisation.** `StandardScaler` appliqué indépendamment par groupe de poste.

**Étape 3 : clustering.** Un clustering par groupe. Algorithme préféré : **HDBSCAN** (gère le bruit sans forcer chaque joueur dans un cluster). Alternatives : GMM ou KMeans si HDBSCAN est instable, à trancher empiriquement selon le volume réel. Prévoir un seuil minimum d'échantillon avant de faire confiance aux clusters (5 championnats, sous-ensemble de la saison en cours : volume possiblement insuffisant au démarrage).

**Étape 4 : nommage des clusters.** Manuel, après observation des statistiques moyennes de chaque cluster.

**Étape 5 : percentiles.** Chaque statistique du joueur est comparée aux joueurs du **même groupe de poste ET du même cluster**, sur la même fenêtre → percentile 0-100.

**Étape 6 : pondération par cluster.** Pondérations manuelles par cluster (ex. xA/90 plus fort pour un « créateur » que pour un « finisseur »). À définir **après** observation des clusters réels, ne pas les figer avant.

**Étape 7 : score Performance.** `Performance = Σ (percentile × poids)`, résultat entre 0 et 100, stocké dans `features.player_market_value_score.performance_score`.

### 10.4 Architecture de code proposée

```
src/foot_predictor/market_value/
├── data/           load_player_match_stats.py    -- requête + jointure match_date, filtre as_of_date
├── preprocessing/  per90.py, normalize.py
├── clustering/     build_clusters.py, assign_cluster.py
├── performance/    percentiles.py, weights.py, performance_score.py
└── tests/
```

Un module `components/` (Potentiel, Réputation, Niveau championnat, Disponibilité, Expérience) sera ajouté dans une étape ultérieure.

### 10.5 À trancher au démarrage

- Seuil minimum de matchs avant de calculer un score.
- Seuil minimum de minutes par match pour le calcul per-90.
- Choix définitif de l'algorithme de clustering (dépend du volume réel).
- Pondérations précises par cluster (dépendent des clusters observés).

---

## 11. Points ouverts et backlog

**Bloquant**

- [ ] **Abonnement API-Football** : le plan gratuit ne couvre que les 2 derniers jours (aucun match des championnats suivis). Bloque `lineup`, `player_match_stats`, `squad_avg_age`, `squad_stability_score_season` et tout `market_value/`.

**Conception**

- [ ] Définir comment le MVS remplace `squad_valuation_eur` au niveau équipe (agrégation par équipe, ou autre). Non tranché dans les récaps précédents.
- [ ] Choix du modèle statistique final pour le score exact (Poisson / Dixon-Coles à confirmer).
- [x] Potentiel et Réputation implémentées (`market_value/components/potential.py` et `reputation.py`, à dire d'expert -- ne dépendent que de `staging.player.birth_date` et `features.team_match_features.standing_position`, déjà peuplées).
- [ ] Spécifier les 3 composantes du MVS restantes (bloquées par le backfill API-Football, cf. item bloquant ci-dessus) :
  - **Niveau championnat** : à dériver du niveau/de la division de la compétition du joueur (ex. classement UEFA du championnat, ou simple hiérarchie manuelle Ligue 1 > Ligue 2 > ...) une fois `staging.lineup` peuplé pour savoir dans quelle compétition le joueur évolue réellement sur la fenêtre.
  - **Disponibilité** : à dériver de `staging.player_injury` (jours d'indisponibilité / blessures sur la fenêtre glissante) -- nécessite l'ingestion de `raw.api_football_injuries` en staging (cf. item ci-dessous).
  - **Expérience** : à dériver de `staging.player_match_stats` (minutes / matchs cumulés sur carrière ou fenêtre longue), une fois la table peuplée par le backfill API-Football.
- [ ] MVS des gardiens (V2).
- [ ] Version « all-time » de la stabilité d'effectif (`squad_stability_score_alltime`).

**Ingestion et opérations**

- [ ] Consommer `raw.api_football_injuries` (capturée, jamais ingérée en staging).
- [ ] Stratégie de scraping planifié (cron / fréquence, gestion des échecs, respect des CGU).
- [ ] Enrichir les mappings d'équipes au fil des équipes rencontrées ; vérifier `api_football_teams.yaml` dès le premier run API-Football.
- [ ] Décider si l'instrumentation diagnostic de `understat.py` est gardée derrière un flag ou retirée.

**Qualité**

- [x] Suite de tests automatisés de base (`pytest`, branche `feature/setup-pytest-tests`) : couvre la réconciliation cross-source (`ingestion/common.py`), le fuzzy matching des noms d'équipe, l'anti-leakage et les fenêtres glissantes de `features/`, le calcul per-90 et la normalisation de `market_value/preprocessing/`. Fixture `db_session` (rollback systématique) pour les tests nécessitant Postgres, marqués `db`. Voir `README.md` section Tests.
- [ ] Étendre la couverture aux scrapers (`ingestion/*_scraper.py`) : nécessite de mocker les appels réseau (football-data, Understat, API-Football), pas fait dans cette première itération.
- [ ] Couvrir `market_value/clustering/` et `market_value/performance/` (non testés faute de données réelles disponibles pour l'instant, cf. section 10).
- [ ] CI/CD (GitHub Actions ou équivalent) pour lancer `pytest -m "not db"` automatiquement sur chaque push/PR : pas mis en place dans cette itération, à faire une fois la suite jugée stable.
- [ ] Bug latent découvert en écrivant les tests : `market_value/preprocessing/per90.py::build_player_vectors` lève un `KeyError` (au lieu de renvoyer un DataFrame vide) si aucune ligne de l'entrée n'atteint `MIN_MINUTES_PER_MATCH` (cf. `tests/market_value/test_per90.py::test_input_with_no_eligible_rows_currently_raises_keyerror`). Non corrigé dans cette branche (hors périmètre), à corriger avant l'exécution du pipeline `market_value/` sur de vraies données.

**Hygiène de projet (à vérifier)**

- [ ] Désactiver le service Windows PostgreSQL natif (port 5432).
- [ ] Mettre à jour `.env.example` (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_SSLMODE`).
- [ ] Commit + push de l'état courant.

---

## 12. Leçons apprises

1. **Corriger un YAML de mapping ne suffit jamais à réparer une entité déjà créée.** `get_or_create_*` priorise le `*_source_mapping` déjà enregistré. Toute correction de mapping doit s'accompagner d'une vérification (voire d'une fusion façon `fusion.py`) des entités déjà résolues. À garder en tête pour `api_football_teams.yaml` et `football_data_competitions.yaml`.
2. **Vérifier la légalité d'une source avant de construire dessus.** L'abandon de Transfermarkt a coûté un remaniement de schéma (migration 0003) ; les wrappers, datasets Kaggle et offres payantes qui le contournent reposent tous sur le même scraping.
3. **Diagnostiquer un conflit de port par élimination** : arrêter le conteneur cible, puis lire le type d'erreur (Postgres vs `connection refused`).
4. **Tester contre un vrai Postgres** révèle des bugs qu'un test unitaire ne verrait pas (enums dupliqués, longueur d'id Alembic, layout `src/`).
5. **Ne pas figer les paramètres avant d'avoir vu les données** (pondérations par cluster, seuils, choix de l'algorithme de clustering).
6. **Un taux d'erreur élevé mérite un diagnostic avant d'avancer** : les 32 % de lignes ignorées auraient dégradé silencieusement les features xG, puis le MVS et la prédiction.
7. **Des fichiers `.env` sous Windows peuvent contenir un BOM** invisible qui corrompt la première variable.
8. **Toujours créer le `.gitignore` avant les fichiers de secrets.**

---

*Document consolidé à partir des récaps successifs. À mettre à jour au fil des décisions, en gardant la section 1 (décisions révisées) et la section 11 (backlog) synchronisées.*
