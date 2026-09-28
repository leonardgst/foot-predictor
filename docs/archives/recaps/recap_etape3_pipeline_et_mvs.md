# Récap — Étape 3 : pipeline d'ingestion complet + conception du Market Value Score

Ce document complète `recap_etape2_schema_tables.md`. Il couvre tout ce qui a été
décidé et construit depuis : les migrations Alembic réelles, le pipeline
d'ingestion `raw → staging` pour les 3 sources retenues, l'abandon de
Transfermarkt, et la conception du Market Value Score (MVS) qui remplace la
valeur marchande.

**Statut à ce stade** : schéma de base de données posé et testé (migrations
0001-0003 appliquées avec succès sur dev/test/prod), pipeline d'ingestion
`raw → staging` écrit et testé pour football-data.co.uk, API-Football et
Understat (niveau équipe et niveau joueur). **Le calcul du MVS lui-même
(clustering, percentiles, score) reste à construire** — objet du document
`prochaine_etape_clustering_mvs.md`.

---

## 1. Décision majeure : abandon de Transfermarkt

### Constat
Transfermarkt interdit explicitement le scraping automatisé, à deux niveaux :
- **CGU** : interdiction explicite du scraping.
- **robots.txt** : confirmé en direct — un outil de récupération web a refusé
  d'accéder au site pour cette raison précise.

### Options écartées
- Scraper quand même (`requests` + BeautifulSoup) : abandonné, risque assumé
  refusé après discussion sur la légalité réelle (droit sui generis des bases
  de données en UE, distinct du simple risque de blocage IP).
- Wrappers tiers "API Transfermarkt" (ex. `felipeall/transfermarkt-api`,
  offres payantes Zyla/Apify/Parse.bot) : **tous** font le même scraping en
  coulisses, avec ou sans facturation. Vérifié noir sur blanc dans le code
  source et la documentation de plusieurs de ces projets. Aucun n'est une
  alternative légale.
- Dataset Kaggle statique (`transfermarkt-datasets` et similaires) : même
  provenance (scraping fait par un tiers, republié), en plus d'être figé
  dans le temps.
- CIES Football Observatory : seule source réellement indépendante trouvée
  (modèle de régression sur ~2400 transferts réels, pas de scraping
  Transfermarkt). Mais pas d'API self-service, tarif non public, probable
  pricing B2B — non retenu par manque d'accessibilité pour un projet perso.

### Conséquence sur le schéma
- `staging.player_valuation`, `raw.transfermarkt_valuation`,
  `raw.transfermarkt_lineup`, `features.team_match_features.squad_valuation_eur`
  → supprimés (migration `0003_market_value_score`).
- Compositions (lineups) : migrées vers **API-Football** (voir section 3).

---

## 2. Décision : construire notre propre Market Value Score (MVS)

Plutôt que d'abandonner purement et simplement la notion de "valeur d'un
joueur", décision de construire un **score composite 0-100 calculé nous-mêmes**,
à partir de statistiques sportives légales (API-Football + Understat) —
même principe que la méthodologie publique du CIES, mais avec nos propres
variables et pondérations.

Point important tranché en discussion : **on ne peut pas non plus s'appuyer
sur un dataset de transferts réels pour calibrer/entraîner ce score**, car
tous les datasets de transferts trouvés remontent eux aussi à un scraping
Transfermarkt. Le MVS reste donc un **score à dire d'expert** (pondérations
manuelles, façon CIES), pas un modèle supervisé calibré sur des prix réels.

Décisions de cadrage actées :
- **Fenêtre temporelle** : glissante sur les **50 derniers matchs** joués par
  le joueur (pas un cumul saison comme l'indicateur de stabilité d'effectif).
- **Gardiens** : hors périmètre en V1 (vecteur de style trop différent des
  joueurs de champ). Traités séparément en V2.
- **Granularité de poste** : simplifiée par rapport à la conception initiale
  (qui prévoyait 8 groupes manuels). API-Football ne donne que 4 catégories
  brutes (`Goalkeeper`/`Defender`/`Midfielder`/`Attacker`) — décision de
  partir de ces 4 groupes et de laisser le **clustering lui-même** détecter
  les sous-styles (ailier créateur vs finisseur, etc.) à l'intérieur de
  chaque groupe, plutôt que de présupposer des sous-catégories qu'on ne peut
  pas obtenir en amont.
- **Anti-fuite temporelle** : chaque calcul de percentile/cluster doit être
  ancré à une date (`as_of_date`) et n'utiliser que des matchs strictement
  antérieurs — cohérent avec la règle déjà actée pour le reste du projet
  (recap_decisions_projet.md, section 6).

Le détail complet de la conception du clustering est dans le document séparé
`prochaine_etape_clustering_mvs.md` (à charger dans la prochaine conversation).

---

## 3. Remplacement des compositions : Transfermarkt → API-Football

- **Source retenue** : API-Football (`v3.football.api-sports.io`), plan
  gratuit (100 requêtes/jour, reset 00:00 UTC), authentification par header
  `x-apisports-key`.
- **Optimisation trouvée en cours de route** : l'endpoint `/fixtures?id={id}`
  renvoie en **un seul appel** compositions + statistiques par joueur +
  événements, plutôt que des appels séparés — division par ~2 du coût en
  quota par rapport à la première version du scraper.
- Clé API à fournir via la variable d'environnement `API_FOOTBALL_KEY` (hors
  du schéma `pydantic-settings` existant, lue directement via `os.environ`).
- **Point de vigilance quota** : `/players?league=&season=` (stats saison
  paginées) coûterait à lui seul ~125 appels pour les 5 championnats — d'où
  la bascule vers une collecte **par match** (`/fixtures?id=`) qui sert à la
  fois les compositions et `player_match_stats`.

---

## 4. Schéma de base de données — état final (22 tables)

### `raw` (6 tables)
```
source_ingestion_log
football_data_match               (jsonb, résultats + cotes)
understat_match_stats             (jsonb, xG équipe par match)
api_football_fixture_detail       (jsonb, compositions + stats joueurs par match — capture quasi verbatim)
understat_player_match            (jsonb, xG/xA par joueur et par match)
api_football_injuries             (jsonb, blessures — pas encore consommée en staging)
```

### `staging` (13 tables)
Inchangées depuis l'étape 2 : `competition`, `competition_source_mapping`,
`season`, `team`, `team_source_mapping`, `player`, `player_source_mapping`,
`match`, `match_source_mapping`, `team_match`, `lineup`.

Nouvelles pour le MVS :
```
player_match_stats   -- une ligne par (match, joueur) : minutes, rating, position_bucket,
                      -- buts, passes clés, tacles, duels, dribbles, fautes, cartons, xg/xa/npxg
                      -- (xg/xa/npxg remplis a posteriori par l'ingestion Understat)
player_injury         -- périodes d'indisponibilité (composante Disponibilité du MVS)
```

### `features` (3 tables)
```
team_match_features            -- inchangée, sauf squad_valuation_eur supprimée
player_style_profile            -- (nouveau) cluster de style par joueur et par as_of_date
player_market_value_score       -- (nouveau) score composite 0-100 par joueur et par as_of_date
```

---

## 5. Pipeline d'ingestion — état final, tout testé contre un vrai Postgres

| Ordre | Script | Rôle |
|---|---|---|
| 1 | `football_data_scraper.py` | Télécharge les CSV football-data.co.uk → `raw.football_data_match` |
| 2 | `football_data.py` | `raw → staging` : crée `match`, `team_match`, `competition`, `season`, `team` |
| 3 | `api_football_scraper.py` | Télécharge `/fixtures?id=` → `raw.api_football_fixture_detail` |
| 4 | `api_football.py` | `raw → staging` : `lineup` + `player_match_stats` (2 fonctions distinctes) |
| 5 | `understat_scraper.py` | Télécharge xG équipe par match → `raw.understat_match_stats` |
| 6 | `understat.py` | `raw → staging` : met à jour `team_match.xg_for/xg_against` |
| 7 | `understat_player_scraper.py` | Télécharge xG/xA par joueur et par match → `raw.understat_player_match` |
| 8 | `understat_player.py` | `raw → staging` : complète `player_match_stats.xg/xa/npxg` |

Principes communs à tous les scripts (dans `ingestion/common.py`) :
- **Réconciliation d'équipe** : mapping manuel par source (`mappings/*_teams.yaml`), une entité "nouvelle" pour une source est reliée à l'entité canonique existante par nom.
- **Réconciliation de joueur** : par `(nom complet, date de naissance)` quand disponible ; par nom seul sinon (API-Football et Understat ne fournissent pas la date de naissance à ce niveau — risque d'homonymes assumé, documenté dans chaque script concerné).
- **Réconciliation de match cross-source** : la première source qui voit un match le crée ; les suivantes le retrouvent soit via mapping déjà enregistré, soit par clé naturelle (équipes + date), jamais de doublon.
- **Idempotence systématique** : tous les scripts peuvent être relancés autant de fois que nécessaire sans dupliquer ni perdre de données (upsert avec comparaison de contenu).

---

## 6. Bugs réels trouvés et corrigés en testant contre un vrai Postgres

- Type enum Postgres créé deux fois (une fois explicitement, une fois automatiquement par `create_table`) → corrigé en retirant la création explicite.
- Revision id Alembic trop long (`varchar(32)` dépassé) → raccourci.
- `pyproject.toml` généré par `uv init` ne déclarait pas le layout `src/` → ajout de `[tool.hatch.build.targets.wheel] packages = ["src/foot_predictor"]`.
- Dépendance `pyyaml` manquante dans `pyproject.toml`.

---

## 7. Prochaines étapes

Voir `prochaine_etape_clustering_mvs.md` pour la suite immédiate (clustering +
calcul du score). Après ça, restent en attente (section 8 du récap projet
principal, jamais retraitées depuis) :
- [ ] Stratégie précise de scraping par source (fréquence, gestion des échecs — partiellement couvert par les scripts actuels, à formaliser en tâche planifiée/cron)
- [ ] Réconciliation des identifiants équipes/joueurs : mapping manuel en place pour les équipes, à enrichir au fil des équipes réellement rencontrées
- [ ] Choix du modèle statistique final pour le score exact (Poisson / Dixon-Coles)
- [ ] Stratégie de test automatisé (fixtures, reset de la base test) — les tests réalisés jusqu'ici sont des scripts ad hoc, pas une suite pytest formelle
- [ ] Consommation de `raw.api_football_injuries` (capturée mais pas encore ingérée en staging)

---

*Document généré à partir de l'échange avec Claude — à intégrer à la suite de `recap_etape2_schema_tables.md`.*
