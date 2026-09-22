# foot-predictor

Projet de data science end-to-end : **prédire le score d'un match de football avant qu'il soit joué**, à partir de données historiques, contextuelles et dynamiques sur les grands championnats européens.

C'est avant tout un **projet pédagogique** : l'objectif réel est de parcourir tout le cycle de vie d'un projet data (cadrage, ingestion, modèle de données, feature engineering, modélisation, évaluation, mise en production), pas seulement de produire un modèle.

---

## Documentation

Toute la documentation du projet tient en 3 fichiers, plus l'historique détaillé des récaps :

| Document | Contenu |
|---|---|
| **`README.md`** (ce fichier) | Vue d'ensemble, état d'avancement, démarrage rapide |
| **`docs/OBJECTIFS.md`** | Cadrage initial : objectif fonctionnel, objectifs pédagogiques, étapes clés d'un projet data |
| **`docs/RECAP_PROJET.md`** | 👉 Mémoire complète du projet : décisions, stack, infra, schéma de tables, pipeline d'ingestion, incidents résolus, prochaine étape (clustering + MVS), points ouverts |
| **`docs/recaps/`** | Récaps historiques par étape (voir `docs/recaps/README.md`) |

**Pour reprendre le projet dans une nouvelle conversation** : joindre `docs/RECAP_PROJET.md` (et `docs/OBJECTIFS.md` si besoin de recontextualiser le « pourquoi »).

---

## Produit visé

Une application qui liste les prochains matchs, avec un bouton **« Prédire »** :

- grisé tant que la **composition officielle** n'est pas publiée (~1h avant le coup d'envoi) ;
- dégrisé ensuite, avec affichage d'un tableau de variables de prédiction.

**Sortie du modèle** : score exact (buts équipe A / buts équipe B), dont on dérive le résultat 1N2 et des probabilités précises.
**Périmètre** : 5 grands championnats européens (Premier League, La Liga, Bundesliga, Serie A, Ligue 1).

---

## Architecture en un coup d'œil

Architecture en 3 couches (bronze / silver / gold), chacune dans un schéma PostgreSQL dédié :

| Schéma | Rôle | Tables |
|---|---|---|
| `raw` | Copie fidèle des données sources (jsonb), rejouable | 6 |
| `staging` | Référentiel réconcilié, typé, clés uniques par entité | 13 |
| `features` | Variables calculées, seule couche consommée par le modèle | 3 |

Sources de données actuelles (toutes légales, gratuites ou plan gratuit) :

- **football-data.co.uk** : résultats historiques et cotes
- **Understat** : xG (équipe et joueur)
- **API-Football** : compositions et statistiques par joueur et par match

> Transfermarkt a été abandonné (CGU et robots.txt interdisent le scraping) — voir `docs/RECAP_PROJET.md`, section 4.

### Stack

| Aspect | Choix |
|---|---|
| Base de données | PostgreSQL |
| Environnements | 3 bases : **dev** (Docker, port 5440), **test** (Docker, port 5433), **prod** (Neon, cloud) |
| Migrations | SQLAlchemy + Alembic |
| Python | `uv`, `pydantic-settings` (bascule via `APP_ENV`) |
| Éditeur | VSCode + SQLTools |
| Versioning | Git — `main` ↔ prod, `dev` ↔ test, `feature/*` ↔ développement |

---

## Démarrage rapide

Prérequis : Docker, `uv`, fichiers `.env.dev` / `.env.test` / `.env.prod` (non commités, modèle dans `.env.example`, encodage **UTF-8 sans BOM**).

```bash
# 1. Démarrer les bases dev et test
docker compose up -d

# 2. Appliquer les migrations (schémas + tables)
APP_ENV=dev  uv run alembic upgrade head
APP_ENV=test uv run alembic upgrade head
APP_ENV=prod uv run alembic upgrade head   # Neon

# 3. Lancer un script d'ingestion (exemple)
APP_ENV=dev uv run python -m foot_predictor.ingestion.understat
```

Ordre du pipeline d'ingestion complet : voir `docs/RECAP_PROJET.md`, section 7.

---

## Tests

```bash
# Suite complète (nécessite la base de test, cf. étape 1 ci-dessus)
uv run pytest

# Uniquement les tests sans dépendance base de données (rapide, marche sans Docker)
uv run pytest -m "not db"

# Avec couverture
uv run pytest --cov=src/foot_predictor --cov-report=term-missing
```

Les tests marqués `db` (réconciliation cross-source, fenêtres glissantes des features) ouvrent une transaction sur la base de test (`APP_ENV=test`, port 5433) et l'annulent (`rollback`) après chaque test — aucune donnée n'est laissée en base. Si la base de test est injoignable, ces tests sont automatiquement `skip` plutôt que d'échouer.

Structure en miroir de `src/foot_predictor/` : `tests/ingestion/`, `tests/features/`, `tests/mapping_builder/`, `tests/market_value/`, fixtures communes dans `tests/conftest.py`.

---

## Structure du dépôt

```
foot-predictor/
├── .env.dev / .env.test / .env.prod    (non commités)
├── .env.example                         (commité)
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml / uv.lock
├── docs/                                (OBJECTIFS.md, RECAP_PROJET.md, recaps/)
├── migrations/versions/                 (historique de schéma)
├── scripts/one_off/                     (diagnostic et fusion ponctuels, dont check_merged_teams_xg.sql)
├── src/foot_predictor/
│   ├── config.py
│   ├── db/                              (models.py, session.py)
│   ├── ingestion/                       (scrapers + raw → staging + common.py)
│   ├── features/
│   └── market_value/                    (clustering, per90, percentiles — non exécuté)
└── tests/                               (miroir de src/foot_predictor/ : ingestion/, features/, mapping_builder/, market_value/)
```

---

## État d'avancement

**Fait**

- ✅ Infra (Docker dev/test, Neon prod, Alembic) opérationnelle sur les 3 environnements
- ✅ Schéma `raw` / `staging` / `features` conçu et migré (22 tables, migrations 0001 à 0003)
- ✅ Pipeline d'ingestion football-data.co.uk + Understat (équipe) fonctionnel et testé ; bug de réconciliation corrigé (568 → 0 ligne ignorée)
- ✅ Code du module `market_value/` (clustering, per90, percentiles, persistence) écrit — committé sur `dev`, **pas encore exécuté sur de vraies données**
- ✅ Suite de tests automatisés (`pytest`) ciblée sur les zones à risque silencieux : réconciliation cross-source (`ingestion/common.py`), fuzzy matching des noms d'équipe, anti-leakage des fenêtres glissantes (`features/`), calcul per-90 (`market_value/preprocessing/`)

**Bloqué**

- 🚧 **Abonnement API-Football à prendre** (le plan gratuit ne couvre que les 2 derniers jours, aucun match des championnats suivis). Conséquences :
  - `staging.lineup` et `staging.player_match_stats` restent vides ;
  - `squad_avg_age` et `squad_stability_score_season` ne sont pas calculables ;
  - tout le pipeline `market_value/` (MVS) est bloqué faute de données.

**À faire**

- ⬜ Choix du modèle statistique pour le score exact (Poisson / Dixon-Coles)
- ⬜ Consommation de `raw.api_football_injuries` (capturée, jamais ingérée)
- ⬜ Scraping planifié (cron / fréquence)
- ⬜ Définir comment le MVS remplace `squad_valuation_eur` au niveau équipe

Liste complète des points ouverts : `docs/RECAP_PROJET.md`, section 11.

---

## ⚠️ Point de vigilance transversal

Corriger un fichier de mapping YAML (`*_teams.yaml`) après coup **ne suffit jamais à lui seul** à réparer une entité déjà créée en base : la logique `get_or_create_*` de `common.py` priorise le `*_source_mapping` déjà enregistré sur le contenu du YAML. Toute correction de mapping doit s'accompagner d'une vérification des entités déjà résolues, en particulier pour `api_football_teams.yaml` une fois l'ingestion API-Football lancée.

---

*À maintenir à jour : mettre à jour la section « État d'avancement » à chaque étape terminée, et ajouter les nouvelles décisions dans `docs/RECAP_PROJET.md`.*
