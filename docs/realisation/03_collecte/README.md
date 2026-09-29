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
| `backup --dest <dossier>` | copie `data/raw/` (sauf `_lock/`) vers un dossier vide et vérifie chaque sha256 ; refusé si une commande tient le verrou | 0 |
| `freeze --dest D --restore-to R` | gel : verrou, `raw_check` de tous les paliers, sauvegarde, test de restauration, brouillon de `docs/DATA_FREEZE.md` (voir [`gel.md`](gel.md)) | 0 |
| `rebuild-manifest` | reconstruit le journal depuis les fichiers, dans un **nouveau** fichier | 0 |
| `refresh --season S [--palier P] [--dry-run] [--yes]` | remet en file les listes de matchs, équipes et blessures d'une saison en cours ; affiche le coût du prochain `run` et demande confirmation | 0 (le `run` suivant : quelques dizaines) |
| `plan-profiles [--palier P] [--limit N] [--dry-run]` | met en file le profil (`/players/profiles`) des titulaires sans date de naissance dans le brut (ADR-0008) | 0 (le `run` suivant : 1 par joueur) |
| `t60 --date J --max-requests N [--dry-run]` | journal T-60 : compositions annoncées avant le coup d'envoi des matchs du top 5 du jour (ADR-0010) | de 15 à 75 selon le jour |
| `t60-report` | bilan du journal T-60 : part des titulaires annoncés présents dans le détail d'après-match (lecture seule) | 0 |
| `lock-status` | état du verrou du dossier brut ; code 0 : libre, 1 : une commande tourne | 0 |

Options communes, à placer **avant** la commande :

- `--raw-dir <dossier>` pour travailler sur un autre dossier que `data/raw` (test de restauration, par exemple) ;
- `--wait-lock <minutes>` pour attendre la fin d'une autre commande au lieu d'échouer (tâches planifiées).

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
    player_profiles/player=276__<horodatage>.json.gz               (commande plan-profiles, puis run)
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

Le tableau ci-dessous est le calendrier **prévisionnel** de l'ADR-0005. La collecte a pris de l'avance : P1 les 27 et 28 septembre, P2 le 28, P3 lancé le 28. L'avancement réel est suivi dans `docs/ETAT_PROJET.md`.

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
- les lundis **5 et 12 octobre** ;
- une dernière fois après le dernier week-end avant le gel (17-18 octobre), c'est-à-dire le **19 octobre au matin**, avant `backup`.

Une liste demandée le 17 octobre ne contiendrait pas les matchs de ce week-end. Au coût d'une soixantaine de requêtes, un rafraîchissement supplémentaire ne pose aucun problème de quota.

## Verrou de collecte et `git pull`

**Une seule commande écrit dans un dossier brut à la fois.** Les commandes qui écrivent prennent un verrou, `data/raw/_lock/collecte.lock` : `coverage`, `plan`, `run`, `refresh`, `plan-profiles`, `requeue`, `rebuild-manifest` et `t60`. Les `--dry-run`, `status`, `backup`, `t60-report` et `lock-status` s'en passent.

- **Mécanisme** : un fichier créé de façon atomique (le système refuse de le créer s'il existe déjà). Il contient le PID, la commande, l'heure et la machine. Il est supprimé à la fin de la commande, même après une erreur.
- **Seconde commande** : elle échoue aussitôt (code de retour 3), avec le nom de la commande en cours. Avec `--wait-lock 120`, elle attend jusqu'à 2 heures ; les tâches planifiées l'utilisent.
- **Verrou périmé** : le processus qui le tenait n'existe plus (plantage, portable éteint), ou le verrou a plus de 18 heures. Il est remplacé par la commande suivante, avec un avertissement. `lock-status` ne supprime jamais rien.

**Avant tout `git pull` dans `C:/foot-predictor`** :

```bash
uv run python -m foot_predictor.collect.api_football lock-status   # code 0 : libre ; 1 : ne pas faire de git pull
git pull --ff-only
```

Pourquoi : un `git pull` change le code pendant qu'il s'exécute, et une tâche planifiée peut tourner sans que l'on y pense (voir « Tâches planifiées »).

## Journal T-60 : `t60` et `t60-report` (ADR-0010)

But unique : vérifier que le onze du détail de match, collecté après coup, est celui annoncé avant le coup d'envoi. C'est l'hypothèse de l'évaluation H2 en rejeu. Critère de l'ADR-0010 : plus de 2 % de titulaires différents.

**Documentation v3**, `/fixtures/lineups` : « Lineups are available between 20 and 40 minutes before the fixture when the competition covers this feature. » `/fixtures` accepte `date` (AAAA-MM-JJ) avec `timezone`, et `ids` (« Maximum of 20 fixtures ids »). Même source que pour les profils ciblés.

Déroulé de `t60 --date J` :

1. `/fixtures?date=J&timezone=UTC` : tous les matchs du jour avec leur heure **réelle**, en 1 requête. On garde ceux du top 5 non commencés ;
2. à partir de 40 minutes avant chaque coup d'envoi, `/fixtures?ids=` par lots de 20, toutes les 5 minutes, jusqu'à obtenir deux compositions de 11 titulaires ou jusqu'au coup d'envoi ;
3. entre deux fenêtres, la commande dort. Elle s'arrête après le dernier coup d'envoi du jour.

- **Fichiers** : `api_football/daily/<J>/fixtures/day__<horodatage>.json.gz` et `api_football/daily/<J>/lineups/<hash12>__<horodatage>.json.gz`, avec le journal habituel.
- **Ce ne sont pas des détails de match** : le planificateur ignore `daily/`. Le détail d'après-match est demandé normalement, après le `refresh` suivant.
- **Coût** : `--dry-run` simule le pire cas d'après les listes du brut. Les heures peuvent y être périmées ; la vraie commande relit la liste du jour. Journées du 9 au 18 octobre : 15 le vendredi, 20 le lundi, 71 à 73 le samedi et le dimanche. `--max-requests` est obligatoire.
- **Bilan** : `t60-report`, à la session de gel, après le dernier `refresh`. Pour chaque match annoncé dont le détail est dans le brut, il compare les titulaires, équipe par équipe. Il n'affiche que des nombres, et ne lit **ni score ni buts** (scellé, ADR-0012).

```bash
uv run python -m foot_predictor.collect.api_football t60 --date 2026-10-10 --max-requests 80 --dry-run
uv run python -m foot_predictor.collect.api_football --wait-lock 120 t60 --date 2026-10-10 --max-requests 80
uv run python -m foot_predictor.collect.api_football t60-report
```

## Tâches planifiées (du 5 au 18 octobre 2026)

Les `refresh` et le journal T-60 tournent seuls, par des tâches planifiées Windows. Elles lancent des scripts versionnés, avec leurs plafonds de requêtes.

| Tâche | Quand (heure de Paris) | Script | Plafond |
|---|---|---|---|
| `FootPredictor_refresh_2026-10-05` | lundi 5 oct., 08:00 | `refresh_run.cmd 2026-10-05` | 250 |
| `FootPredictor_t60_2026-10-09` | vendredi 9 oct., 16:00 | `t60.cmd 2026-10-09` | 80 |
| `FootPredictor_t60_2026-10-10` | samedi 10 oct., 09:30 | `t60.cmd 2026-10-10` | 80 |
| `FootPredictor_t60_2026-10-11` | dimanche 11 oct., 09:30 | `t60.cmd 2026-10-11` | 80 |
| `FootPredictor_refresh_2026-10-12` | lundi 12 oct., 08:00 | `refresh_run.cmd 2026-10-12` | 250 |
| `FootPredictor_t60_2026-10-12` | lundi 12 oct., 16:00 | `t60.cmd 2026-10-12` | 80 |
| `FootPredictor_t60_2026-10-16` | vendredi 16 oct., 16:00 | `t60.cmd 2026-10-16` | 80 |
| `FootPredictor_t60_2026-10-17` | samedi 17 oct., 09:30 | `t60.cmd 2026-10-17` | 80 |
| `FootPredictor_t60_2026-10-18` | dimanche 18 oct., 09:30 | `t60.cmd 2026-10-18` | 80 |

**Scripts** (`scripts/taches_planifiees/`) :

- `refresh_run.cmd` : `refresh --season 2026 --yes` (paliers P1 et P3, déjà planifiés), puis `run --max-requests 250`, puis `status` ;
- `t60.cmd` : `t60 --date <jour> --max-requests 80`. La commande tourne jusqu'au dernier coup d'envoi du jour et empêche la mise en veille automatique.

Les deux scripts passent par le verrou avec `--wait-lock`. Leur journal d'exécution va dans `data/logs/refresh_<jour>.log` ou `data/logs/t60_<jour>.log`, un dossier ignoré par Git. Un second argument `--dry-run` fait une simulation sans requête.

**Conditions** : le portable doit être **allumé, branché, capot ouvert, session ouverte** (verrouillée, cela suffit). Aucun mot de passe n'est stocké. Une tâche manquée (portable éteint) démarre dès que possible le jour même, jamais le lendemain. Une fenêtre noire s'ouvre pendant la tâche : **ne pas la fermer**, cela arrêterait la collecte.

**Pourquoi le 5 octobre** : aucun match du top 5 n'a lieu entre le 21 septembre et le 8 octobre (trêve internationale). Ce `refresh` récupère quand même les matchs de Segunda, de FA Cup et de Copa del Rey joués depuis le 25 septembre, ainsi que ceux de P3 (Brésil, Argentine, MLS...). Le 12 octobre suit la journée des 10 et 11 octobre. Les matchs du lundi 12 au soir et les coupes d'Europe des 13 à 15 octobre seront pris par le `refresh` du 19.

Commandes utiles, dans Git Bash : les options commencent par `//`, sinon Git Bash les convertit en chemins.

```bash
# Voir les tâches
schtasks //Query //FO TABLE | grep FootPredictor
schtasks //Query //TN FootPredictor_t60_2026-10-10 //V //FO LIST
# Lancer une tâche tout de suite (consomme du quota !)
schtasks //Run //TN FootPredictor_refresh_2026-10-05
# Tester un script à blanc, sans requête (journal dans data/logs/)
cmd //c "scripts	aches_planifiees	60.cmd 2026-10-10 --dry-run"
# Créer (ou recréer) toutes les tâches, puis les supprimer toutes
uv run python scripts/taches_planifiees/creer_taches.py            # simulation
uv run python scripts/taches_planifiees/creer_taches.py --apply
uv run python scripts/taches_planifiees/creer_taches.py --delete
# Supprimer une seule tâche
schtasks //Delete //TN FootPredictor_t60_2026-10-09 //F
```

Les tâches, déjà passées le 19 octobre, sont supprimées pendant la session de gel (`creer_taches.py --delete`).

## Profils ciblés : `plan-profiles` (ADR-0008)

Les pages `/players?league&season` ne contiennent pas tous les joueurs : des titulaires n'y ont pas de profil, et donc pas de date de naissance. Tant que l'abonnement est actif, on demande leur profil un par un.

**Point d'accès, vérifié le 2026-09-29** dans la documentation v3 (<https://www.api-football.com/documentation-v3>, section *Players > Profiles*). Ce site refuse les lecteurs automatiques (HTTP 403) : le texte a été lu dans la copie de la spécification OpenAPI officielle publiée par la bibliothèque `fabricatorsltd/api-sports` (`api-specs/football/openapi.yaml`).

- `GET /players/profiles` : « Returns the list of all available players. » Paramètres : `player` (« The id of the player »), `search` (nom, 3 caractères au moins) et `page`.
- « Pagination : 250 results per page. » Avec `player`, la réponse tient en une page : **1 requête par joueur**. Le point d'accès n'accepte pas plusieurs identifiants.
- Réponse : `player.birth.date`, et aussi le nom, la nationalité, la taille et le poste. Mise à jour « several times a week ».
- Alternative écartée : `/players?id=&season=` demande la saison du joueur, ce qui coûterait une requête par saison.

**Règle de sélection** :

- les titulaires (`startXI`) des blocs de championnat qui collectent les profils, dans l'ordre du YAML : P1 top 5, P1 D2, puis P3 ;
- dans les saisons de chaque bloc ; le dossier d'un championnat du top 5 contient aussi les saisons de P2, sans profils ;
- seulement ceux sans date de naissance dans **aucun** profil du brut, tous paliers et toutes saisons confondus ;
- identifiants nuls ou égaux à `0` (joueur inconnu de l'API) écartés.

Un joueur est rattaché au premier bloc où il est titulaire, et la tâche porte ce palier.

```powershell
uv run python -m foot_predictor.collect.api_football plan-profiles --dry-run   # décompte par bloc, file inchangée
uv run python -m foot_predictor.collect.api_football plan-profiles             # ajoute les tâches (déjà présentes : ignorées)
uv run python -m foot_predictor.collect.api_football run --dry-run
uv run python -m foot_predictor.collect.api_football run --max-requests 5      # essai, puis lire une réponse
uv run python -m foot_predictor.collect.api_football run --max-requests <budget>
```

- Une réponse vide (`results = 0`, identifiant inconnu de ce point d'accès) met la tâche en `suspect`.
- Les tâches `player_profile` passent après tous les autres types du même palier.
- `raw_check` lit ces profils et compte les « titulaires sans date de naissance, tous profils confondus ».

## Sauvegarde et test de restauration, le jour du gel (ADR-0006)

**Procédure complète du 19 octobre : [`gel.md`](gel.md).** La commande `freeze` enchaîne, dans l'ordre :

1. la prise du verrou ;
2. `raw_check` sur tous les paliers ;
3. la sauvegarde vers le disque externe, avec vérification des sha256 ;
4. le test de restauration dans un dossier vide ;
5. le brouillon de `docs/DATA_FREEZE.md`.

Elle s'arrête à la première étape en échec.

```bash
uv run python -m foot_predictor.collect.api_football --raw-dir C:/foot-predictor/data/raw freeze     --dest D:/foot-predictor/data-freeze-2026-10/raw --restore-to C:/fp_restauration/raw
```

`backup` reste disponible seul, par exemple pour refaire une restauration. Il refuse de copier pendant qu'une commande tient le verrou, et ne copie jamais le dossier `_lock/`.

```bash
uv run python -m foot_predictor.collect.api_football --raw-dir D:/foot-predictor/data-freeze-2026-10/raw backup --dest C:/fp_restauration/raw
```

Un fichier « hors journal » est un avertissement : il peut apparaître après un plantage entre l'écriture du fichier et celle de sa ligne de journal. `rebuild-manifest` permet alors de comparer.

## Limites connues (à traiter plus tard)

- **Saison en cours, hors `refresh`** : les entraîneurs et transferts (une tâche par équipe) et les profils joueurs (`players`) de la saison ne sont pas rafraîchis. Un changement d'entraîneur survenu après leur collecte ne sera pas vu.
- **P4** : `standings` est planifiable dès qu'un bloc est ajouté au YAML ; `sidelined` attend la définition de la liste de joueurs.
- **Anciens scripts** : `ingestion/api_football_scraper.py` et `injuries_scraper.py` sont obsolètes. Ne plus les lancer ; ils seront supprimés dans une PR de nettoyage.
- `ingestion/api_football.py` (raw vers staging) ne lit pas ce nouveau format et **ne doit pas être exécuté** : il sera remplacé par le nouveau chargeur (ADR-0008).
