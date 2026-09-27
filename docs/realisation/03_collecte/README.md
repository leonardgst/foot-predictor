# Étape 03 : collecte API-FOOTBALL (collecteur v2)

Mode d'emploi du collecteur décrit par l'ADR-0004. Décisions liées : ADR-0002 (périmètre par paliers), ADR-0003 (format du brut), ADR-0005 (calendrier), ADR-0006 (sauvegarde), ADR-0007 (emplacement du code).

## En bref

Le collecteur interroge API-FOOTBALL et n'écrit **que** dans `data/raw/`, un dossier ignoré par Git. Il ne dépend ni de Docker ni de Postgres.

- **Lots de 20 matchs** avec `/fixtures?ids=` : environ 20 fois moins de requêtes que l'ancien script.
- **Reprise** : une file SQLite garde l'état de chaque requête. Relancer ne rejoue que ce qui reste `pending`.
- **Sécurité du quota** : au plus 2 requêtes par seconde. Le champ `errors` et les en-têtes de quota sont lus à chaque réponse. Le collecteur s'arrête proprement sous la réserve (500 requêtes par jour).
- **Brut intact et jamais écrasé** : une recollecte crée une nouvelle version horodatée. Chaque requête est tracée dans un journal.

Code : `src/foot_predictor/rawstore/` (fichiers, journal, sauvegarde) et `src/foot_predictor/collect/api_football/` (client, file, plan, runner, commandes). Périmètre : `config/collecte_api_football.yaml`.

## Prérequis

- `API_FOOTBALL_KEY=...` dans `.env.dev`. `APP_ENV` vaut `dev` par défaut. La clé n'est jamais affichée.
- `uv sync --all-groups`.
- Lancer les commandes depuis la racine du dépôt : les chemins par défaut (`data/raw`, `config/...`) sont relatifs.

## Commandes

Toutes s'écrivent `uv run python -m foot_predictor.collect.api_football <commande>`. Ajoute `--help` pour le détail.

| Commande | Rôle | Requêtes API |
|---|---|---|
| `coverage` | `/status` et `/leagues`, puis `docs/realisation/03_collecte/couverture.md` (identifiants et couverture par saison) | 2 |
| `plan --palier P1` | crée les tâches du palier dans la file ; peut être relancé sans créer de doublon | 0 |
| `run --dry-run` | affiche les requêtes en attente, par palier et par type | 0 |
| `run [--max-requests N]` | exécute la file ; N plafonne les appels HTTP du lancement (`/status` et nouvelles tentatives compris) | selon la file |
| `status` | quota du jour (d'après le journal), files, échecs, progression par palier, matchs non terminaux | 0 |
| `requeue --status failed\|suspect [--type T]` | remet des tâches en `pending`, après examen | 0 |
| `backup --dest <dossier>` | copie `data/raw/` vers un dossier vide et vérifie chaque sha256 | 0 |
| `rebuild-manifest` | reconstruit le journal depuis les fichiers, dans un **nouveau** fichier | 0 |
| `refresh --season S [--palier P] [--dry-run] [--yes]` | remet en file les listes de matchs, équipes et blessures d'une saison en cours ; affiche le coût du prochain `run` et demande confirmation | 0 (le `run` suivant : quelques dizaines) |

Option commune : `--raw-dir <dossier>` pour travailler sur un autre dossier que `data/raw` (test de restauration, par exemple).

## Fichiers produits

```
data/raw/
  api_football/
    status/status__<horodatage>.json.gz
    leagues/all__<horodatage>.json.gz                          (commande coverage)
    fixtures_list/league=39/season=2023__<horodatage>.json.gz
    fixtures_detail/league=39/season=2023/<hash12>__<horodatage>.json.gz   (lot de 20 au plus)
    teams/league=39/season=2023__<horodatage>.json.gz
    injuries/league=39/season=2023__<horodatage>.json.gz
    players/league=39/season=2023/page=01__<horodatage>.json.gz
    coachs/team=33__<horodatage>.json.gz
    transfers/team=33__<horodatage>.json.gz
  _manifest/api_football.jsonl     une ligne par réponse stockée
  _queue/api_football.sqlite       file de travail
```

- **Enveloppe** de chaque fichier : `{request, fetched_at, http_status, headers_quota, body}`, où `body` est la réponse de l'API intacte.
- **Journal** : horodatage, endpoint, paramètres, statut HTTP, `errors`, `results`, quota restant du jour et de la minute, durée, fichier, sha256. Pour un lot de détails, il contient aussi `fixture_ids`, les matchs réellement reçus : c'est ce champ qui évite de redemander un match.

## Ce que fait `run`

1. Appelle `/status` pour connaître le quota restant.
2. Traite la file par groupes, dans l'ordre : listes de matchs, équipes, **détails**, blessures, entraîneurs, transferts, joueurs. Avant chaque groupe, il relance le plan, ce qui crée automatiquement :
   - les lots de détails dès que les listes de matchs sont arrivées ;
   - les tâches entraîneurs et transferts à partir des listes d'équipes ;
   - les pages 2 à N des joueurs dès que la page 1 donne `paging.total`.
3. S'arrête quand il n'y a plus rien à faire, sous la réserve, sur le quota du jour épuisé, ou à `--max-requests`.

| Réponse | Statut de la tâche |
|---|---|
| normale | `done` |
| `errors` non vide (plan, paramètre...) | `failed`, sans nouvelle tentative ; réponse stockée pour examen |
| `results = 0` alors que des données sont attendues, ou lot de détails incomplet | `suspect` ; à examiner |
| HTTP 429 ou `errors.rateLimit` | pause de 60 s, puis nouvelle tentative |
| HTTP 5xx, délai dépassé | 3 tentatives (attentes de 2 puis 4 s). Ensuite, la tâche reste `pending` jusqu'au lancement suivant, et passe `failed` au 3e lancement en échec |
| quota du jour épuisé, réserve atteinte, clé refusée | arrêt propre, tâche en cours laissée `pending` |

Règles des lots de détails :
- seuls les matchs terminés (FT, AET, PEN, AWD, WO) sont mis en lot. Les autres (à venir, reportés...) sont listés à part : voir `status` ;
- un match déjà reçu ou déjà mis en lot n'est jamais redemandé ;
- dans les coupes, seuls les matchs impliquant une équipe d'un championnat du palier P1 (top 5 et D2), la même saison, sont demandés.

## Ordre des paliers et calendrier (ADR-0002, ADR-0005)

On ne commence un palier que lorsque le précédent est collecté **et contrôlé** (rapport G.9). `plan` affiche un avertissement si un palier précédent a encore des tâches en attente.

| Dates | Étape |
|---|---|
| 28 sept. → 1er oct. | Collecteur relu et fusionné ; `coverage` ; premier essai limité (20 requêtes) |
| 2 → 8 oct. | **P1** : top 5 et D2 (2015-2026), coupes d'Europe et nationales, équipes, blessures, joueurs, entraîneurs, transferts ; contrôles de qualité |
| 9 → 16 oct. | **P2** (top 5 et D2 avant 2015, seulement les saisons avec compositions), **P3** (11 autres championnats avec joueurs), **P4** (à définir) |
| 17 → 18 oct. | Fin de la collecte, rattrapages (`requeue`), contrôles finaux |
| **19 oct.** | **Gel** : `DATA_FREEZE.md`, `backup` vers le disque externe, test de restauration, tag `data-freeze-2026-10` |
| 20 → 21 oct. | Marge de recollecte |
| 22 oct. 09:56 (Paris) | Fin de l'abonnement |

Le quota (7 500 requêtes) repart à zéro à 00:00 UTC, soit 02:00 à Paris jusqu'au 25 octobre. Une fois la réserve atteinte, relancer `run` le lendemain.

**Ordre de grandeur pour P1**, à confirmer avec `run --dry-run` après `coverage` :
- ~230 listes de matchs, ~120 listes d'équipes, ≤ 120 requêtes de blessures ;
- ~4 000 pages de joueurs ;
- ~500 requêtes d'entraîneurs et de transferts ;
- ~2 500 à 3 000 lots de détails.

Au total, de l'ordre de 8 000 requêtes, soit un peu plus d'une journée de quota.

## Première utilisation : séquence exacte

Dans PowerShell, à la racine du dépôt. Seules les étapes 1 et 4 consomment du quota.

```powershell
# 1. Inventaire de couverture (2 requêtes : /status et /leagues)
uv run python -m foot_predictor.collect.api_football coverage
#    Relire docs/realisation/03_collecte/couverture.md : chaque identifiant configuré doit
#    correspondre à la bonne compétition (nom, pays). Corriger le YAML si besoin, AVANT plan.

# 2. Plan du palier P1 (aucune requête)
uv run python -m foot_predictor.collect.api_football plan --palier P1

# 3. Simulation (aucune requête)
uv run python -m foot_predictor.collect.api_football run --dry-run

# 4. Premier essai limité : /status puis 19 listes de matchs
uv run python -m foot_predictor.collect.api_football run --max-requests 20

# 5. Vérifications (aucune requête)
uv run python -m foot_predictor.collect.api_football status
Get-Content data\raw\_manifest\api_football.jsonl -Tail 3
uv run python -m foot_predictor.collect.api_football backup --dest "$env:TEMP\fp_verif_backup"
```

À vérifier après l'étape 4 :
- `status` indique 19 `fixtures_list` `done`, 0 `failed`, 0 `suspect`, et un quota du jour cohérent avec le tableau de bord ;
- le journal montre `"errors": []`, un `results` d'environ 380 (Premier League) et `quota_remaining_day` renseigné ;
- `backup` se termine par « Sauvegarde vérifiée. ». Supprimer ensuite le dossier temporaire `$env:TEMP\fp_verif_backup` (une copie, **pas** `data/raw/`).

Lance `coverage` **avant** `plan`. Sans couverture connue, le plan ne peut pas écarter les saisons inexistantes (par exemple la Conférence, 848, avant 2021) : leurs listes reviendraient vides et seraient marquées `suspect`. Relancer `plan` ensuite ne retire pas les tâches déjà créées.

## Collecte courante

```powershell
uv run python -m foot_predictor.collect.api_football run        # chaque jour, jusqu'à la réserve
uv run python -m foot_predictor.collect.api_football status     # suivi
```

Examiner les échecs et les suspects. `status` donne pour chacun le fichier stocké et la raison. Après examen :

```powershell
uv run python -m foot_predictor.collect.api_football requeue --status suspect --type fixtures_detail
```

## Saison en cours : `refresh`

La liste des matchs d'une compétition-saison n'est demandée qu'une fois. Pour la saison en cours (2026, soit 2026-27), les matchs joués après cette date restent « non terminaux » dans la liste stockée : sans rafraîchissement, ils n'auraient jamais de lot de détails.

```powershell
uv run python -m foot_predictor.collect.api_football refresh --season 2026 --palier P1 --dry-run   # coût, sans rien modifier
uv run python -m foot_predictor.collect.api_football refresh --season 2026 --palier P1             # confirmation demandée
uv run python -m foot_predictor.collect.api_football run
```

- **Ce que fait `refresh`** : il remet en `pending` les tâches `fixtures_list`, `teams` et `injuries` de la saison, pour les blocs des paliers déjà planifiés (tous par défaut). Les règles de `plan` s'appliquent : bornes des blocs, saisons et couverture de `/leagues`. La commande elle-même n'envoie **aucune requête**.
- **Coût affiché avant confirmation** : une requête par liste, équipe ou blessures, plus au plus un lot de détails par tranche de 20 matchs non terminaux dont la date est passée, plus `/status`. C'est une estimation haute : un match reporté reste non terminal, et dans les coupes seuls les matchs d'une équipe suivie sont demandés. Pour P1 et la saison 2026, compter une soixantaine de requêtes.
- **Au `run` suivant** : chaque réponse devient une **nouvelle version** horodatée du fichier. L'ancienne reste sur le disque et dans le journal. La relance automatique du plan lit la liste la plus récente et ne crée des lots que pour les matchs **devenus terminaux et jamais reçus**.
- **Un `run` déjà en cours** prend les tâches remises en file à son prochain groupe. Inutile de l'arrêter.
- **Tâches `failed`** : elles ne sont pas reprises. Les examiner, puis `requeue --status failed`.
- **Réponse attendue** : `o` ou `oui` pour confirmer. Toute autre réponse, ou une entrée fermée (tâche planifiée Windows), annule. Pour une tâche planifiée, ajouter `--yes`.

**Quand le lancer** : après les journées de championnat, pour que les matchs du week-end soient terminés dans la nouvelle liste.
- une fois vers le **10 octobre** ;
- une dernière fois après le dernier week-end avant le gel (17-18 octobre), c'est-à-dire le **19 octobre au matin**, avant `backup`.

Une liste demandée le 17 octobre ne contiendrait pas les matchs de ce week-end. Au coût d'une soixantaine de requêtes, un rafraîchissement supplémentaire ne pose aucun problème de quota.

## Sauvegarde et test de restauration, le jour du gel (ADR-0006)

N'arrêter aucune collecte en cours de route : lancer ces commandes quand `run` est terminé.

```powershell
# Copie vers le disque externe (dossier absent ou vide), avec vérification des sha256
uv run python -m foot_predictor.collect.api_football backup --dest E:\foot-predictor\data-freeze-2026-10\raw

# Test de restauration : recopie depuis le disque externe vers un dossier vide, puis vérification
uv run python -m foot_predictor.collect.api_football --raw-dir E:\foot-predictor\data-freeze-2026-10\raw backup --dest C:\fp_restauration\raw
```

Un fichier « hors journal » est un avertissement : il peut apparaître après un plantage entre l'écriture du fichier et celle de sa ligne de journal. `rebuild-manifest` permet alors de comparer.

## Limites connues (à traiter plus tard)

- **Saison en cours, hors `refresh`** : les entraîneurs et transferts (une tâche par équipe) et les profils joueurs (`players`) de la saison ne sont pas rafraîchis. Un changement d'entraîneur survenu après leur collecte ne sera pas vu.
- **P4** : `standings` est planifiable dès qu'un bloc est ajouté au YAML ; `sidelined` attend la définition de la liste de joueurs.
- **Anciens scripts** : `ingestion/api_football_scraper.py` et `injuries_scraper.py` sont obsolètes. Ne plus les lancer ; ils seront supprimés dans une PR de nettoyage.
- `ingestion/api_football.py` (raw vers staging) ne lit pas ce nouveau format et **ne doit pas être exécuté** (rapport B.4, D1 et D3).
