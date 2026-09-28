# Foot Predictor — Récap du pipeline d'ingestion

> Document généré à partir de la lecture des fichiers d'ingestion existants
> (`common.py`, `api_football.py` + `api_football_scraper.py`, `football_data.py`
> + `football_data_scraper.py`, `understat.py` + `understat_scraper.py` +
> `understat_player.py` + `understat_player_scraper.py`). Il consolide en un
> seul endroit ce qui est déjà en place, pour éviter d'avoir à ressortir
> chaque fichier pour se rappeler une décision.

## 1. Principe général : raw → staging

Le pipeline suit une séparation stricte en deux couches :

- **`raw.*`** : copie brute des payloads récupérés (JSON quasi verbatim pour
  API-Football et Understat, CSV parsé ligne à ligne pour football-data).
  Aucune transformation métier à ce stade. Une ligne `SourceIngestionLog`
  trace chaque exécution (source, référence du payload, statut
  `pending`/`success`/`failed`).
- **`staging.*`** : entités reconciliées et exploitables (`Team`, `Match`,
  `TeamMatch`, `Player`, `PlayerMatchStats`, `Lineup`, `Competition`,
  `Season`). C'est cette couche qui alimentera le modèle.

Chaque source a donc deux scripts : un **scraper** (téléchargement →
`raw.*`) et un **ingest** (`raw.*` → `staging.*`).

## 2. Les trois sources et leur rôle

| Source | Rôle | Crée des matchs ? | Fichiers |
|---|---|---|---|
| **football-data.co.uk** | Source de référence : calendrier, équipes, scores | ✅ Oui — c'est la source qui crée `Match` et `TeamMatch` | `football_data_scraper.py`, `football_data.py` |
| **API-Football** | Compositions (lineups) + stats détaillées par joueur | ❌ Non — complète un match déjà résolu via `resolve_match_cross_source` | `api_football_scraper.py`, `api_football.py` |
| **Understat** | xG / xA / npxG au niveau équipe et joueur | ❌ Non — complète uniquement des lignes `TeamMatch` / `PlayerMatchStats` déjà créées | `understat_scraper.py`, `understat.py`, `understat_player_scraper.py`, `understat_player.py` |

Ce découpage est volontaire : football-data est gratuite, fiable et légère
(CSV publics), donc elle sert de socle. Les deux autres sources ne font que
**compléter** des lignes déjà existantes ; si le match/team_match/player_match
correspondant n'existe pas encore côté staging, la ligne raw est simplement
ignorée (comptée dans `skipped`) en attendant qu'un run ultérieur de
football-data (ou d'API-Football pour les joueurs) crée la ligne à compléter.

### 2.1 football-data.co.uk

- Téléchargement direct de CSV publics (`https://www.football-data.co.uk/mmz4281/{season}/{div}.csv`),
  pas de scraping HTML, données prévues explicitement par le site pour de la
  prédiction de matchs.
- Championnats couverts en V1 : `E0` (Premier League), `SP1` (Liga), `D1`
  (Bundesliga), `I1` (Serie A), `F1` (Ligue 1).
- Upsert en raw sur la clé naturelle `(div, date, home_team, away_team)` car
  le CSV redonne toute la saison à chaque téléchargement.
- Idempotent en staging : `get_or_create_match` **met à jour** le match
  existant (score, statut) plutôt que de l'ignorer, pour gérer le passage
  `scheduled` → `played`.

### 2.2 API-Football

- Un seul endpoint utilisé : `/fixtures?id={id}`, qui renvoie en un seul appel
  compositions + stats joueurs + événements (a remplacé une ancienne version
  qui faisait des appels séparés — coût quota divisé par ~2).
- Deux étapes : `fetch_fixtures(league, season, date_from, date_to)` pour
  lister les fixtures et leurs id, puis `fetch_fixture_detail(fixture_id)`
  pour le détail (seulement si le match est terminé, statut `FT`).
- Upsert en raw sur `fixture_id` (identifiant fiable, contrairement à une clé
  naturelle date+équipes).
- **Limitation connue** : l'endpoint ne fournit pas la date de naissance des
  joueurs (seulement id, nom, photo) → résolution des joueurs par nom seul,
  risque d'homonymes un peu plus élevé qu'avec une source qui donnerait la
  date de naissance.
- Deux extracteurs indépendants côté staging, lisant la même table raw :
  `ingest_api_football_lineups` (→ `staging.lineup`) et
  `ingest_api_football_player_stats` (→ `staging.player_match_stats`).

**Quota / plan** :
- Plan gratuit : 100 requêtes/jour, historique limité (~2 derniers jours
  seulement — testé en conditions réelles).
- Plan Pro (19€/mois) : 7 500 requêtes/jour, historique complet débloqué.
- **Backfill multi-saisons reprenable** : `_fixture_already_ingested()` vérifie
  qu'un fixture n'est pas déjà en raw avant de dépenser une requête dessus.
  Indispensable pour étaler un backfill de plusieurs saisons sur plusieurs
  jours sans regaspiller le quota sur des matchs déjà récupérés.
- `__main__` boucle sur `SEASON_START_YEARS` (actuellement `range(2015, 2025)`,
  soit 10 saisons) × tous les championnats de `api_football_competitions.yaml`,
  avec une plage de dates été-à-été (`season_date_range()`) par saison.

### 2.3 Understat

- Deux granularités, deux scrapers/ingests distincts :
  - **Équipe** (`understat_scraper.py` / `understat.py`) : `league.get_match_data(season)`,
    **un seul appel par championnat/saison** → très peu coûteux en requêtes.
    Ne garde que les matchs joués (`isResult=True`) avec un xG renseigné.
  - **Joueur** (`understat_player_scraper.py` / `understat_player.py`) :
    `league.get_player_data(season)` (1 appel) puis `player.get_match_data()`
    **par joueur** (1 appel/joueur) → le plus coûteux des deux, d'où un délai
    entre appels (`REQUEST_DELAY_SECONDS`).
- Upsert en raw sur clé naturelle `(match_date, home_team, away_team[, player_name])`.
- Résolution du joueur par nom seul (`Player.full_name`) : si le joueur n'est
  pas encore connu (pas encore vu par API-Football), la ligne est ignorée.
- **Correctif appliqué** : le `time.sleep()` du scraper équipe a été retiré —
  il ne throttlait aucun appel réseau (un seul appel par ligue/saison), il
  ralentissait juste le script inutilement. Le sleep reste pertinent et en
  place côté scraper joueur, où il y a bien un appel réseau par joueur.

## 3. `common.py` — logique de réconciliation partagée

Principe appliqué à toutes les entités (équipe, compétition, joueur, match) :

1. Chercher d'abord dans la table `<entity>_source_mapping` (`source_name`,
   `source_ref`) → déjà résolu par le passé, renvoie l'id directement.
2. Sinon, regarder le mapping manuel (fichier YAML dans `mappings/`) pour
   trouver le nom canonique associé à ce `source_ref`.
3. Chercher/créer l'entité par son nom canonique dans `staging`.
4. Créer la ligne de mapping `(source_name, source_ref) → entity_id`, pour
   que l'étape 1 fonctionne directement la prochaine fois (idempotence).

Fonctions clés :

- `get_or_create_competition`, `get_or_create_team` : mapping manuel YAML
  obligatoire (lève une erreur explicite si le `source_ref` est inconnu, pour
  forcer à compléter le mapping plutôt que de créer des doublons silencieux).
- `get_or_create_match` : crée un match la première fois, mais **met à jour**
  scores/statut sur les runs suivants (cas `scheduled` → `played`).
- `resolve_match_cross_source` : pour une source qui ne crée jamais de match
  elle-même (API-Football, Understat). Cherche le mapping existant, sinon
  cherche par clé naturelle (équipes + date, à la journée près) et enregistre
  le mapping pour la prochaine fois. Renvoie `None` si le match n'existe pas
  encore côté staging.
- `get_or_create_player` : pas de mapping manuel (volume trop important) →
  résolution par nom complet (+ date de naissance si disponible).
- `upsert_team_match_xg` : ne crée jamais de `TeamMatch`, renvoie `None` si la
  ligne n'existe pas encore (signale que football-data n'a pas encore ingéré
  ce match).

## 4. Ordre d'exécution recommandé

1. **football-data** (scraper puis ingest) — crée le socle `Match`/`TeamMatch`.
2. **Understat équipe** (scraper puis ingest) — un seul appel/championnat,
   très peu coûteux, à lancer tôt.
3. **API-Football** (scraper puis ingest) — lineups + stats joueurs détaillées,
   nécessite un plan payant pour l'historique complet, backfill reprenable
   sur plusieurs jours.
4. **Understat joueur** (scraper puis ingest) — nécessite que les `Player`
   existent déjà (créés par API-Football) et que `PlayerMatchStats` existe
   déjà pour ce (match, joueur) ; sinon la ligne est ignorée.

## 5. Limitations connues / points de vigilance

- Résolution des joueurs par nom seul pour API-Football et Understat →
  risque d'homonymes (aucune date de naissance disponible sur ces endpoints).
- Understat nécessite qu'API-Football (ou une autre source) ait déjà créé le
  `Player` et la ligne `PlayerMatchStats` — sinon ses données de xG/xA/npxG
  sont perdues silencieusement (comptées en `skipped`, pas d'erreur).
- Mapping manuel YAML obligatoire pour équipes/compétitions : toute nouvelle
  équipe/compétition rencontrée dans une source doit être ajoutée à la main
  dans `mappings/<source>_teams.yaml` ou `mappings/<source>_competitions.yaml`,
  sinon `get_or_create_team`/`get_or_create_competition` lève une exception.
- Quota API-Football : le plan gratuit ne permet pas de backfill historique
  (limité aux ~2 derniers jours en pratique) → un plan payant (Pro, 19€/mois,
  7 500 req/jour) est nécessaire pour les 10 dernières saisons. Le script est
  conçu pour être relancé sur plusieurs jours sans gaspiller le quota
  (`_fixture_already_ingested`).

## 6. Fichiers du projet (état actuel)

```
foot_predictor/ingestion/
├── common.py                          # réconciliation partagée (mappings, get_or_create_*)
├── football_data_scraper.py           # CSV football-data.co.uk -> raw.football_data_match
├── football_data.py                   # raw.football_data_match -> staging (Match, TeamMatch)
├── api_football_scraper.py            # /fixtures?id= -> raw.api_football_fixture_detail
├── api_football.py                    # raw -> staging (Lineup, PlayerMatchStats)
├── understat_scraper.py               # xG équipe -> raw.understat_match_stats
├── understat.py                       # raw -> staging (TeamMatch.xg_for/xg_against)
├── understat_player_scraper.py        # xG/xA/npxG joueur -> raw.understat_player_match
└── understat_player.py                # raw -> staging (PlayerMatchStats.xg/xa/npxg)
```
