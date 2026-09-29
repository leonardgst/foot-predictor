# Étape 06 : variables du MVP et jeu de données versionné (jalon J4)

Mode d'emploi de la construction du jeu de données, de son contrôle, du registre des variables et du scellé. Décisions : ADR-0028 (scellé technique), ADR-0029 (tirs de football-data), ADR-0030 (jeu de données), ADR-0031 (Elo), ADR-0032 (glissants et `xg_proxy`), ADR-0033 (calendrier et huis clos). Catalogue détaillé : [`catalogue.md`](catalogue.md), généré depuis le registre.

## En bref

- Une ligne par (match, équipe) : matchs de **saison régulière** des 10 championnats (top 5 et D2), de 2000-01 à 2024-25, terminés, non exclus. 66 colonnes, dont 54 variables G0 à G3, toutes à l'horizon **H1** (avant composition).
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
- Premier jeu : `ds-2026-09-29-83d28f3b` (196 098 lignes).

## Registre des variables

- `src/foot_predictor/features/registry.yaml` : une fiche par variable (groupe, définition, source, horizon, disponibilité en live, paramètres, historique minimal, traitement du manquant, risque de fuite et parade).
- Une fiche peut décrire la colonne de l'adversaire (`opp_…`, via `portee`) et une variable distincte par demi-vie (`{h}` dans le nom).
- Tests : chaque colonne du jeu figure au registre, et inversement ; aucune variable sans horizon ; catalogue à jour.
- Ajouter une variable : sa fiche au registre, sa fonction pure et ses tests, puis `catalogue`, puis `build`.

## Scellé (ADR-0012, ADR-0028)

- Tout match joué à partir du **1er juillet 2025** est sous scellés. La seule porte de lecture des matchs (`features/sources.py` : `load_matches`, `load_dataset`) les filtre dans la requête SQL et vérifie le résultat.
- Les lire exige `sealed_test=True` et le fichier d'expérience ; chaque usage ajoute une ligne à `reports/sealed_tests.md`, aujourd'hui vide. Réservé au test scellé de la partie 4, une fois par version.
- Une requête écrite à la main (`psql`) n'est pas couverte : filtre `match_date < '2025-07-01'` explicite pour toute valeur ; après cette date, décomptes de présence seulement.

## Limites connues

- Rupture de série des tirs de football-data en Serie A, de 2018-19 à 2020-21 : `xg_proxy` surestimé d'environ 0,27 par équipe et par match (ADR-0029, ADR-0032). Décision de l'utilisateur en attente.
- Quatre D2 sans tirs avant 2017-18 : `xg_proxy` vide sur cette période.
- Repos fiable seulement depuis 2015-16 (2016-17 pour l'Italie, 2018-19 pour l'Espagne) ; G3 indisponible en live.
- Quelques matchs de D2 absents de l'API ne sont pas appariés (Ligue 2 2010-11 : 10 ; 2. Bundesliga 2012-13 : 4).
