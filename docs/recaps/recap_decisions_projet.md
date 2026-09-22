# Récapitulatif des décisions — Projet prédiction football

Ce document récapitule toutes les décisions prises jusqu'ici. Il sert de mémoire de référence pour repartir sur des conversations ciblées sans perdre le fil.

---

## 1. Cadrage du projet

- **Objectif fonctionnel** : prédire le résultat d'un match de football avant qu'il soit joué.
- **Objectif réel** : projet pédagogique end-to-end de data science, couvrant tout le cycle de vie (cadrage, données, feature engineering, modélisation, évaluation, mise en production).
- **Produit visé** : une appli qui liste les prochains matchs, avec un bouton **"Prédire"** à côté de chaque match.
  - Le bouton est **grisé** tant que les données nécessaires ne sont pas disponibles.
  - Le bouton se **dégrise** une fois toutes les données dispo, et affiche un tableau de variables de prédiction.

## 2. Périmètre et type de prédiction

- **Compétitions couvertes** : quelques grands championnats européens (pas un seul championnat, pas non plus tous les championnats du monde).
- **Sortie du modèle** : score exact (nombre de buts équipe A / nombre de buts équipe B), dont on dérive le résultat 1N2 et des probabilités précises.
- **Budget données** : sources gratuites en priorité, scraping léger accepté si nécessaire (pas de budget pour API payantes).

## 3. Décision UX critique : disponibilité de la prédiction

- Les compositions officielles ne sont connues que ~1h avant le coup d'envoi.
- **Décision** : le bouton "Prédire" reste grisé tant que la composition officielle n'est pas publiée. Pas de mode "estimation avec composition probable" en V1.
- Conséquence : le statut de disponibilité est un booléen simple (compo officielle publiée = oui/non), pas une logique à plusieurs niveaux de confiance.

## 4. Données brutes retenues pour la V1

| Catégorie | Détail | Fréquence de dispo | Fenêtre de calcul |
|---|---|---|---|
| Calendrier | Matchs passés + à venir | À l'avance / après match | — |
| Compositions | Onze de départ (historique complet + officiel à venir) | Immédiat (historique) / ~1h avant (futur) | — |
| **Indicateur de stabilité de l'effectif** | Score de cohésion du onze de départ, basé sur une matrice cumulée de co-apparitions par paires de joueurs (méthodologie reprise du mémoire de stage joint) | Par match | Cumulatif depuis le 1er match de la saison, remis à zéro chaque saison |
| Effectif | Liste des joueurs par équipe et par saison | Saison + mutations | — |
| Valeur marchande | Valeur marchande de chaque joueur (proxy de la masse salariale — **pas** le vrai salaire, qui n'est pas public), somme sur l'effectif | Mise à jour périodique | Snapshot à date de match |
| Âge | Date de naissance des joueurs | Statique | Calculé à la date du match |
| Classement | Position, écart de points | À date | Snapshot à date de match |
| Forme récente | Points pris | Équipe | **10 derniers matchs glissants** |
| Buts marqués/encaissés | Séparés domicile/extérieur | Équipe | **10 derniers matchs glissants** |
| xG (expected goals) | Marqués/encaissés | Équipe | **10 derniers matchs glissants** |

### Sources envisagées
- **football-data.co.uk** : résultats historiques, cotes (CSV propres, plusieurs saisons, grands championnats)
- **Transfermarkt** : compositions par match (scraping), valeurs marchandes, effectifs
- **Understat / FBref** : xG et stats avancées (scraping)

### Précisions importantes
- La **masse salariale** utilisée est la **valeur marchande Transfermarkt**, pas le salaire réel (non public).
- L'**indicateur de stabilité** est repris intégralement de la méthodologie du mémoire joint (voir section 5) : c'est un score de cohésion par paires de joueurs, pas juste "le XI exact a-t-il déjà joué ensemble".
- Les **blessures/suspensions** ne sont **pas incluses en V1**.

## 5. Indicateur de stabilité de l'effectif — méthodologie (source : mémoire de stage)

- Pour chaque équipe, sur une saison donnée (reset à chaque nouveau championnat) :
  1. Matrice symétrique joueur × joueur : `1` si les deux joueurs ont débuté ensemble sur un match, `0` sinon (diagonale à 0).
  2. Cette matrice est **cumulée match après match** (calcul stateful, séquentiel, dans l'ordre chronologique).
  3. Pour un match donné, on restreint la matrice cumulée aux 11 titulaires de ce match, on somme, et on normalise par le score maximum théorique (`110 × nombre de matchs joués`).
  4. Résultat : un score entre 0 et 1 par équipe et par match.
- Dans le mémoire, cet indicateur combiné à la différence de masse salariale et d'âge (modèle de régression logistique, victoire binaire) donnait un odds ratio de 5.32 pour la stabilité — signal jugé solide.
- **Pour la V1 du projet actuel** : le modèle sera reconstruit de zéro (le modèle du mémoire n'était qu'un exemple de méthodologie à réutiliser pour l'indicateur, pas le modèle final).

## 6. Architecture du système d'information (SI)

Architecture en couches (type bronze/silver/gold), pour séparer les étapes de transformation :

1. **Brut (raw)** : copie fidèle des données scrapées/récupérées, sans transformation. Permet de rejouer le pipeline si la logique de nettoyage change.
2. **Nettoyé (staging)** : réconciliation des IDs entre sources, référentiels stables (équipes, joueurs, compétitions), typage, gestion des valeurs manquantes.
3. **Features (gold)** : variables calculées prêtes pour le modèle (stabilité, moyennes glissantes, différences domicile/extérieur). Le modèle ne consomme **que** cette couche, jamais le brut directement (évite le training-serving skew).

Point de vigilance transversal : **gestion stricte de la temporalité** — chaque ligne de la couche Features doit refléter l'état des données disponibles strictement avant le match concerné (pas de data leakage).

## 7. Stack technique retenue

| Aspect | Choix | Justification |
|---|---|---|
| Base de données | PostgreSQL | Relationnel, adapté aux données structurées liées (matchs/joueurs/équipes) |
| Environnements | 3 bases distinctes : **dev**, **test**, **prod** | Isolation complète, permet de faire évoluer le schéma sans casser la prod |
| Hébergement dev/test | Local, via **Docker Compose** | Rapide, gratuit, reset facile |
| Hébergement prod | **Neon** (Postgres serverless, cloud, tier gratuit) | Fonctionnalité de branching de base très adaptée pour tester des migrations avant de les appliquer réellement |
| Schémas Postgres (par base) | `raw`, `staging`, `features` | Reflète les 3 couches du SI |
| Migrations | **SQLAlchemy + Alembic** | Historique versionné du schéma, rejouable dans le même ordre sur dev → test → prod |
| Gestion d'environnement Python | **uv** | Gestion rapide des dépendances et de l'environnement virtuel |
| Config par environnement | Fichiers `.env.dev` / `.env.test` / `.env.prod` (non commités) + `pydantic-settings` | Bascule via variable `APP_ENV` |
| Éditeur | **VSCode** | Extensions Python + Pylance, extension PostgreSQL/SQLTools pour explorer les 3 bases |
| Versioning | **Git** | Branches `main` (↔ prod), `dev` (↔ test), `feature/*` (développement) |

### Structure de projet proposée
```
foot-predictor/
├── .env.dev / .env.test / .env.prod   (non commités)
├── .env.example                        (commité)
├── .gitignore
├── pyproject.toml
├── uv.lock
├── docker-compose.yml
├── alembic.ini
├── migrations/versions/                (commité — historique de schéma)
├── src/foot_predictor/
│   ├── config.py
│   ├── db/ (models.py, session.py)
│   ├── ingestion/
│   └── features/
└── tests/
```

### Workflow de migration type
```bash
APP_ENV=dev uv run alembic revision --autogenerate -m "message"
APP_ENV=dev uv run alembic upgrade head      # test en local
APP_ENV=test uv run alembic upgrade head     # validation
APP_ENV=prod uv run alembic upgrade head     # déploiement réel (Neon)
```

---

## 8. Points encore à trancher (prochaines étapes)

- [ ] Détail des tables par schéma (`raw`, `staging`, `features`) : colonnes, types, clés primaires/étrangères
- [ ] Choix du modèle statistique final pour le score exact (ex. Poisson / Dixon-Coles envisageable, à confirmer)
- [ ] Stratégie précise de scraping par source (fréquence, gestion des échecs, respect des CDU)
- [ ] Réconciliation des identifiants équipes/joueurs entre les différentes sources (football-data.co.uk, Transfermarkt, Understat/FBref)
- [ ] Mise en place concrète du pipeline (orchestration : simple script/cron pour commencer, ou outil dédié plus tard)
- [ ] Stratégie de test automatisé (fixtures, reset de la base `test`)

---

*Document généré à partir de l'échange avec Claude — à mettre à jour au fil des décisions futures.*
