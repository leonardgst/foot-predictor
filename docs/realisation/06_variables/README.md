# Étape 06 : variables du MVP et jeu de données versionné (jalon J4)

Mode d'emploi de la construction du jeu de données, de son contrôle, du registre des variables et du scellé. Décisions : ADR-0028 (scellé technique), ADR-0029 (tirs de football-data), ADR-0030 (jeu de données), ADR-0031 (Elo), ADR-0032 (glissants et `xg_proxy`), ADR-0033 (calendrier et huis clos). Catalogue détaillé : [`catalogue.md`](catalogue.md), généré depuis le registre.

## En bref

- Une ligne par (match, équipe) : matchs de **saison régulière** des 10 championnats (top 5 et D2), de 2000-01 à 2024-25, terminés, non exclus. 68 colonnes, dont 54 variables G0 à G3, toutes à l'horizon **H1** (avant composition).
- Les variables sont des **fonctions pures** (`features/elo.py`, `rolling.py`, `rest.py`, `huis_clos.py`, `dataset.build_frame`) : historique des matchs → valeurs, sans accès à la base. La partie 5 les réutilisera telles quelles pour l'inférence.
- **Règle temporelle** : la variable d'un match du jour J n'utilise que des matchs terminés **avant le jour J**. Les tests le vérifient (modifier le match m ne change pas sa ligne ; invariance à la date de coupe ; matchs du même jour).
- Le jeu est un **instantané Parquet** dans `data/datasets/<version>/` (ignoré par Git), avec son manifeste ; la base n'en garde que la trace (`features.dataset_version`).

## Commandes

```bash
uv run python -m foot_predictor.features build              # construit une version (≈ 5 s) et la trace en base
uv run python -m foot_predictor.features check --invariance # rapport reports/variables/dataset_<version>.md
uv run python -m foot_predictor.features catalogue          # régénère catalogue.md après un changement du registre

uv run python -m foot_predictor.features.elo_tuning          # réglage de l'Elo (≈ 4 min), réécrit params/elo.json
uv run python -m foot_predictor.features.xg_proxy_estimation # estimation de l'xg_proxy, réécrit params/xg_proxy.json
```

| Option | Commande | Rôle |
|---|---|---|
| `--output-root` | `build`, `check` | dossier des versions (défaut : `data/datasets`) |
| `--no-db` | `build` | n'écrit pas la ligne de `features.dataset_version` (essais) |
| `--version` | `check` | version à contrôler (défaut : la plus récente) |
| `--invariance` | `check` | contrôle anti-fuite n° 2 sur les données réelles, aux dates de coupe du 2019-01-01 et du 2023-03-01 ; code d'erreur en cas d'écart |

`build` lit `staging` (base de `APP_ENV`, défaut `dev`) : lancer `load` avant si le brut a changé, jamais pendant une tâche planifiée de collecte (voir `CLAUDE.md`).

## Versions et manifeste

- Nom : `ds-<AAAA-MM-JJ>-<8 premiers caractères du sha256 du manifeste>`. Même contenu, même version : deux `build` de suite donnent les mêmes sha256.
- `manifest.json` : révision Alembic, `ops.load_run.id` lu, commit Git et `git_dirty` (vrai si du code suivi n'était pas committé : à reconstruire), sha256 du registre, paramètres figés (Elo, `xg_proxy`, glissants, empreinte du YAML de huis clos, date du scellé), périmètre, décomptes, sha256 de chaque fichier.
- Premier jeu : `ds-2026-09-29-83d28f3b` (196 098 lignes). Jeu en vigueur : **`ds-2026-09-30-ba2b91f7`** (tirs d'API-FOOTBALL depuis 2015-16, ADR-0035 ; mêmes lignes, 68 colonnes).
- Sur le brut définitif (3.11) : `ds-2026-10-22-bf786ef1`, **même contenu** que `ba2b91f7`, avec les identifiants internes du `staging` actuel (chargement n° 7). Les expériences gardent `ba2b91f7` (voir « Phase B »).

## Registre des variables

- `src/foot_predictor/features/registry.yaml` : une fiche par variable (groupe, définition, source, horizon, disponibilité en live, paramètres, historique minimal, traitement du manquant, risque de fuite et parade).
- Une fiche peut décrire la colonne de l'adversaire (`opp_…`, via `portee`) et une variable distincte par demi-vie (`{h}` dans le nom).
- Tests : chaque colonne du jeu figure au registre, et inversement ; aucune variable sans horizon ; catalogue à jour.
- Ajouter une variable : sa fiche au registre, sa fonction pure et ses tests, puis `catalogue`, puis `build`.

## Scellé (ADR-0012, ADR-0028)

- Tout match joué à partir du **1er juillet 2025** est sous scellés. La seule porte de lecture des matchs (`features/sources.py` : `load_matches`, `load_dataset`) les filtre dans la requête SQL et vérifie le résultat.
- Les lire exige `sealed_test=True` et le fichier d'expérience ; chaque usage ajoute une ligne à `reports/sealed_tests.md`, aujourd'hui vide. Réservé au test scellé de la partie 4, une fois par version.
- Une requête écrite à la main (`psql`) n'est pas couverte : filtre `match_date < '2025-07-01'` explicite pour toute valeur ; après cette date, décomptes de présence seulement.

## Phase B : jeu sur le brut définitif (3.11)

Après le gel et la partie 2 (`staging` = chargement n° 7, tag `v0.3.0`), le jeu est reconstruit puis comparé au jeu en vigueur. Les identifiants internes de `staging` ont changé au chargement n° 6 (E-058) : les lignes se rapprochent par **identifiants API**, jamais par `match_id` ni `team_id`.

```bash
uv run python -m foot_predictor.features build               # ds-2026-10-22-bf786ef1, 8 s
uv run python -m foot_predictor.features check --invariance  # reports/variables/dataset_ds-2026-10-22-bf786ef1.md
```

Méthode de la comparaison (script ponctuel, lecture seule, non versionné comme la photo de 2.10) :

- une ligne est identifiée par (match, équipe) en identifiants API ; pour un match ou une équipe « hors_api », par ses libellés et sa date (origine, championnat, date, équipes) ;
- la correspondance entre identifiant interne et clé vient de deux photos de `staging` :
  - pour l'ancien jeu, la photo prise avant le chargement n° 6. Elle vaut pour le n° 4, celui de `ba2b91f7` : les n° 4 et 5 ont lu les mêmes journaux du brut et donnent les mêmes empreintes de tables, hors `match_odds`, créée par la migration 0007 ;
  - pour le nouveau jeu, la photo du chargement n° 7 ;
- les 65 autres colonnes et la clé de l'adversaire sont comparées à l'identique (une valeur vide est égale à une valeur vide) ;
- témoin : une copie du nouveau jeu où trois valeurs sont modifiées (dont un écart de 1e-9) donne bien trois écarts.

### Résultats de 3.11 (2026-10-22)

| Contrôle | Résultat |
|---|---|
| `build` | `ds-2026-10-22-bf786ef1` : 196 098 lignes, 98 049 matchs, du 2000-07-28 au 2025-06-01 ; commit `e34ea61` sans modification locale ; chargement n° 7 |
| `check --invariance` | registre OK ; 0 match scellé ; invariance au bit près aux coupes du 2019-01-01 et du 2023-03-01 ; rapport identique à celui de `ba2b91f7`, hors titre et ligne du manifeste |
| Manifeste contre `ba2b91f7` | décomptes, paramètres et périmètre identiques. Diffèrent : révision Alembic (0006 → 0008), chargement (4 → 7), commit, sha256 du Parquet, et sha256 du registre (définition de `phase` complétée par « scelle », commit `3c92fc8` : texte seul) |
| Lignes rapprochées | 196 098 sur 196 098, aucune en plus ni en moins ; même ordre |
| Valeurs | **0 écart** sur les 65 colonnes et l'adversaire |
| Identifiants internes | `match_id` changé sur 91 364 lignes (matchs « hors_api », +104) ; `team_id` et `opp_team_id` sur 11 904 lignes ; **aucun changement dans le top 5 depuis 2015-16** (phases apprentissage et validation) |

- **Conclusion** : le jalon J4 tient sur le brut définitif. Les 104 matchs ajoutés depuis le 29/09 sont tous joués après le 1er juillet 2025 et ne changent aucune ligne. `ba2b91f7` reste le jeu des expériences (`experiments/`, figé par `pre-scelle-h1`) ; le test scellé construira sa propre version (`--sealed-test`).
- **Usages de `ba2b91f7` dans `inference/`** (E-058) :
  - aucun module de `modeling/` n'utilise `team_id`, et les cotes se rapprochent par `match_id`, inchangé dans le top 5 depuis 2015-16 : modèles de rejeu, cotes et étude des tirs (`shots_check`) ne sont pas touchés ;
  - `inference check --only rows` compare le jeu au `staging` actuel par (`match_id`, `team_id`) : 1 jour sur 17 (2020-12-15, 2 lignes de D2) n'aurait plus les mêmes clés. Mesuré sur ce jour : écart de clés avec `ba2b91f7`, aucune colonne en écart ; identique au bit près avec `bf786ef1`. À pointer sur un jeu du `staging` courant en partie 5, avant de relancer ce contrôle.

## Limites connues

- Source des tirs (ADR-0035) : API-FOOTBALL pour un match joué depuis 2015-16 quand elle a les quatre valeurs, sinon football-data ; cela corrige la rupture de série de la Serie A (2018-19 à 2020-21). **Après le gel**, seuls les tirs de football-data existeront : écart d'`xg_proxy` de +0,02 en moyenne (+0,08 en Serie A), à contrôler en partie 5.
- D2 sans tirs avant 2015-16, et en partie en 2015-16 et 2016-17 : `xg_proxy` vide sur ces périodes.
- Repos fiable seulement depuis 2015-16 (2016-17 pour l'Italie, 2018-19 pour l'Espagne) ; G3 indisponible en live.
- Quelques matchs de D2 absents de l'API ne sont pas appariés (Ligue 2 2010-11 : 10 ; 2. Bundesliga 2012-13 : 4).
