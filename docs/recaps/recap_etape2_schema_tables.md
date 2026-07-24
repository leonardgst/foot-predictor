
# Récap — Étape 2 : conception du schéma de tables (raw / staging / features)
 
Ce document complète `recap_etape1_infra_finalisee.md`. Il documente la conception complète du schéma de données pour les 3 couches (`raw`, `staging`, `features`), décidée sur le papier avant toute écriture de migration Alembic.
 
**Statut à ce stade : conception uniquement — aucun code/migration écrit.** Prochaine étape : traduire ce schéma en migrations Alembic (une ou plusieurs révisions, dans la continuité de `0001_create_schemas`).
 
---
 
## 1. Branche de travail
 
```bash
git checkout dev
git pull origin dev
git checkout -b feature/schema-tables
```
 
---
 
## 2. Schéma `staging` — référentiel stable et réconcilié
 
### Granularité retenue
 
- Une ligne par **(match, équipe)** dans `team_match`, avec un booléen `is_home` — dénormalisé depuis `match.home_team_id`/`away_team_id` mais généré uniquement par le pipeline (jamais saisi à la main), donc pas de risque de désync. Utile car `team_match` est la table de base des agrégations glissantes (forme, buts, xG séparés domicile/extérieur).
### Réconciliation multi-sources
 
- Table de **mapping dédiée par entité** (pas de table générique polymorphe, pour garder de vraies FK) : `team_source_mapping`, `player_source_mapping`, `competition_source_mapping`, `match_source_mapping`.
- Chacune : `UNIQUE(source_name, source_ref)` + FK vers l'entité interne.
### Compositions
 
- Table normalisée `lineup` (une ligne par joueur par match par équipe), plus facile à exploiter que du JSON pour calculer l'indicateur de stabilité (besoin de paires de joueurs).
- `lineup.position` en **texte libre** (pas d'enum) : les sources n'utilisent pas la même granularité de position (Transfermarkt vs FBref), un enum figerait trop tôt. Une position normalisée pourra être dérivée plus tard, en `features`, sans toucher au staging.
### Tables
 
```
staging.competition
├── id                 bigint PK
├── name               text
├── country            text
└── created_at         timestamptz
 
staging.competition_source_mapping
├── id                 bigint PK
├── competition_id     bigint FK → competition.id
├── source_name        text
└── source_ref         text
    UNIQUE(source_name, source_ref)
 
staging.season
├── id                 bigint PK
├── competition_id     bigint FK → competition.id
├── label              text        -- ex '2024-2025'
├── start_date         date
└── end_date           date
 
staging.team
├── id                 bigint PK
├── name               text
├── country            text
└── created_at         timestamptz
 
staging.team_source_mapping
├── id                 bigint PK
├── team_id            bigint FK → team.id
├── source_name        text
└── source_ref         text
    UNIQUE(source_name, source_ref)
 
staging.player
├── id                 bigint PK
├── full_name          text
├── birth_date         date
├── nationality        text
└── created_at         timestamptz
 
staging.player_source_mapping
├── id                 bigint PK
├── player_id          bigint FK → player.id
├── source_name        text
└── source_ref         text
    UNIQUE(source_name, source_ref)
 
staging.match
├── id                 bigint PK
├── competition_id     bigint FK → competition.id
├── season_id          bigint FK → season.id
├── match_date         timestamptz
├── home_team_id       bigint FK → team.id
├── away_team_id       bigint FK → team.id
├── home_goals         smallint  NULL   -- NULL tant que pas joué
├── away_goals         smallint  NULL
├── status             enum      -- 'scheduled' | 'played' | 'postponed' | 'cancelled'
└── created_at         timestamptz
 
staging.match_source_mapping
├── id                 bigint PK
├── match_id           bigint FK → match.id
├── source_name        text
└── source_ref         text
    UNIQUE(source_name, source_ref)
 
staging.team_match          -- une ligne par (match, équipe)
├── id                 bigint PK
├── match_id           bigint FK → match.id
├── team_id            bigint FK → team.id
├── is_home            boolean       -- dénormalisé, généré par le pipeline uniquement
├── goals_for          smallint  NULL
├── goals_against      smallint  NULL
├── xg_for             numeric(4,2) NULL
├── xg_against         numeric(4,2) NULL
└── created_at         timestamptz
    UNIQUE(match_id, team_id)
 
staging.lineup               -- composition normalisée
├── id                 bigint PK
├── match_id           bigint FK → match.id
├── team_id            bigint FK → team.id
├── player_id          bigint FK → player.id
├── started            boolean       -- titulaire ou remplaçant
├── position           text NULL     -- texte libre, pas d'enum
└── created_at         timestamptz
    UNIQUE(match_id, team_id, player_id)
 
staging.player_valuation        -- valeur marchande, mise à jour périodique
├── id                 bigint PK
├── player_id          bigint FK → player.id
├── value_date         date          -- date du snapshot Transfermarkt
├── value_eur          bigint
└── created_at         timestamptz
    UNIQUE(player_id, value_date)
```
 
### Décisions écartées / non retenues en staging
 
- **`staging.standing`** (classement) : **retiré**. Décision : le classement est **calculé automatiquement** à partir de `team_match` plutôt que scrapé — moins de travail global (pas de scraping dédié, pas de mapping supplémentaire) et plus fiable. Déplacé en `features.team_match_features` (voir section 4).
- **`staging.player_team_season`** (effectif par équipe/saison) : **non créée**. Pas nécessaire : les indicateurs (stabilité, xG, forme) se calculent entièrement à partir de `lineup` + `team_match`. Pourra être ajoutée plus tard si un besoin apparaît (ex. profondeur de banc).
---
 
## 3. Schéma `raw` — copie fidèle par source
 
Principe : copie brute sans transformation, pour pouvoir rejouer le pipeline si la logique de nettoyage change. Pas de FK vers d'autres tables raw, pas de typage strict — payload en `jsonb` pour rester résilient aux changements de format des sources (c'est le rôle de `staging` d'imposer une structure stricte, pas de `raw`).
 
```
raw.source_ingestion_log          -- traçabilité de chaque run d'ingestion
├── id                 bigint PK
├── source_name        text        -- 'football-data' | 'transfermarkt' | 'understat'
├── ingested_at        timestamptz
├── payload_ref        text        -- ex. nom de fichier / URL scrapée
└── status             text        -- 'success' | 'failed'
 
raw.football_data_match           -- résultats + cotes
├── id                 bigint PK
├── ingestion_id       bigint FK → source_ingestion_log.id
├── raw_payload        jsonb
└── ingested_at        timestamptz
 
raw.transfermarkt_lineup          -- compo scrapée
├── id                 bigint PK
├── ingestion_id       bigint FK → source_ingestion_log.id
├── raw_payload        jsonb
└── ingested_at        timestamptz
 
raw.transfermarkt_valuation       -- valeurs marchandes scrapées (page distincte de lineup)
├── id                 bigint PK
├── ingestion_id       bigint FK → source_ingestion_log.id
├── raw_payload        jsonb
└── ingested_at        timestamptz
 
raw.understat_match_stats         -- xG scrapé
├── id                 bigint PK
├── ingestion_id       bigint FK → source_ingestion_log.id
├── raw_payload        jsonb
└── ingested_at        timestamptz
```
 
---
 
## 4. Schéma `features` — variables prêtes pour le modèle
 
### Choix structurel
 
**Option retenue : une seule table large `team_match_features`** (une ligne par team_match, toutes les variables en colonnes), plutôt qu'une table par famille de feature. Plus simple pour construire le dataset d'entraînement (un seul `SELECT`), au prix d'une table qui s'élargira au fil des futures features.
 
### Règles de calcul actées
 
- **Forme récente / buts** : moyenne glissante sur les **10 derniers matchs**, filtrés sur le **même contexte domicile/extérieur** que le match à prédire (si l'équipe joue à domicile, on prend ses 10 derniers matchs à domicile, toutes compétitions confondues — idem à l'extérieur). Motivation : les grands championnats n'ont pas toujours assez de matchs domicile/extérieur si on restreint à une seule compétition.
- **xG** : même logique de contexte domicile/extérieur, mais sur une fenêtre plus courte de **5 derniers matchs** (le xG est plus volatile, une fenêtre plus longue serait moins réactive). Comptage dédié séparé de celui de la forme/buts, car la fenêtre diffère (5 vs 10).
- **Classement (`standing`)** : calculé à partir de `staging.team_match`, snapshot **strictement avant la date du match** concerné (pas de data leakage — cohérent avec le point de vigilance transversal du récap projet, section 6).
- **Valeur marchande d'équipe** : dernière valeur connue par joueur **avant la date du match** (issue de `staging.player_valuation`), sommée sur l'effectif — logique appliquée au moment du calcul en `features`, pas stockée telle quelle en staging.
- **Indicateur de stabilité d'effectif** : méthodologie du mémoire de stage (matrice cumulée de co-apparitions par paires de joueurs, cumulative depuis le 1er match de la saison, remise à zéro chaque saison) — **conservée telle quelle pour la V1**.
  - ⚠️ Évolution prévue mais **pas en V1** : une version alternative sur le **nombre total de relations entre joueurs sans reset annuel** (cumul all-time). Le nom de colonne `squad_stability_score_season` est choisi dès maintenant pour laisser la place à une future colonne `squad_stability_score_alltime` (ou équivalent) sans renommage à prévoir.
### Table
 
```
features.team_match_features
├── id                             bigint PK
├── team_match_id                  bigint FK → staging.team_match.id  UNIQUE
├── match_id                       bigint FK → staging.match.id       -- dénormalisé (filtrage/jointures)
├── team_id                        bigint FK → staging.team.id        -- dénormalisé
├── computed_at                    timestamptz
 
-- Forme récente (10 derniers matchs, même contexte domicile/extérieur, toutes compétitions)
├── form_points_last10             smallint
├── form_matches_count             smallint     -- nb de matchs réellement dispo (<10 en début de saison)
 
-- Buts (même fenêtre/contexte que la forme)
├── goals_for_last10               numeric(4,2)
├── goals_against_last10           numeric(4,2)
 
-- xG (5 derniers matchs, même contexte domicile/extérieur, toutes compétitions)
├── xg_for_last5                   numeric(4,2)
├── xg_against_last5               numeric(4,2)
├── xg_matches_count_last5         smallint     -- comptage dédié, fenêtre différente de form/goals
 
-- Classement (snapshot avant match, dans la compétition du match concerné)
├── standing_position              smallint
├── standing_points                smallint
├── standing_goal_diff             smallint
 
-- Effectif
├── squad_valuation_eur            bigint
├── squad_avg_age                  numeric(4,2)
├── squad_stability_score_season   numeric(5,4)   -- score 0-1, méthodologie mémoire, reset par saison
 
└── UNIQUE(team_match_id)
```
 
---
 
## 5. Vue d'ensemble des 3 schémas
 
| Schéma | Rôle | Nb tables |
|---|---|---|
| `raw` | Copie fidèle par source, jsonb, non transformée | 5 |
| `staging` | Référentiel réconcilié, typé, clé unique par entité | 12 |
| `features` | Variables calculées, prêtes pour le modèle | 1 (large) |
 
---
 
## 6. Prochaines étapes
 
- [ ] Traduire ce schéma en migrations Alembic (probablement : une révision par schéma, ou une révision globale — à trancher)
- [ ] Écrire les scripts d'ingestion `raw → staging` par source (réconciliation des IDs via les tables `*_source_mapping`)
- [ ] Écrire les requêtes/scripts de calcul `staging → features` (rolling averages, standing, stability, valuation)
- [ ] Détail encore ouvert : stratégie précise de scraping par source (fréquence, gestion des échecs, respect des CDU) — repris de la section 8 du récap projet principal
- [ ] Détail encore ouvert : choix du modèle statistique final pour le score exact (Poisson / Dixon-Coles à confirmer)
- [ ] Stratégie de test automatisé (fixtures, reset de la base `test`)
---
 
*Document généré à partir de l'échange avec Claude — à intégrer à la suite de `recap_etape1_infra_finalisee.md`.*
 
