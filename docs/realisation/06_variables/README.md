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

## Partie 6 : horizon H2 (ADR-0047)

### 6.1 — Porte des compositions et registre H2 (2026-10-31)

- **Lectures** (`features/sources.py`), même filtre du scellé en SQL que `load_matches`, mêmes paramètres (`competition_ids`, `kinds`, `until`, `sealed_test`). Pas d'ouverture à l'inférence : H2 n'a pas de live.
  - `load_lineups` : une ligne par joueur inscrit (titulaire ou remplaçant), avec ses statistiques du match (minutes, note, poste) et sa date de naissance, vides s'il n'en a pas. `api_player_id` est l'identifiant stable d'un chargement à l'autre (E-058).
  - `load_team_sheets` : une ligne par (match, équipe), avec l'entraîneur (`api_coach_id`, vide en 2015-16), la formation, les titulaires sans identifiant et les collisions exclues (ADR-0020).
  - Le journal du scellé compte des **matchs** (une date par match), pas des lignes de joueurs.
- **Volume réel** (avant le scellé, tous championnats) : 3,3 millions de lignes, 31 s et 439 Mo pour `load_lineups(kinds=["league"])` ; 263 514 feuilles en 2 s. Les étapes suivantes filtrent par compétition (top 5 et D2 : environ 2 millions de lignes).
- **Registre** : groupes G4 (entraîneur), G5 (qualité du XI) et G6 (stabilité), tous de l'horizon H2 ; G0 à G3 restent H1. Une fiche dont l'horizon ne suit pas son groupe est refusée.
- **Garde H1** (ADR-0010) : `registry.check_model_horizon(colonnes, horizon)` refuse un modèle qui lit une variable d'un horizon plus tardif que le sien, ou une colonne hors du registre. `modeling/model_card.build_card` l'appelle : une carte H1 ne peut pas décrire un modèle qui lit une variable H2.
- **Architecture** : aucun module de `features/` autre que la porte ne lit `staging.lineup`, `staging.player_match_stats`, `staging.player`, `staging.team_match` ou `staging.coach`, ni n'importe leurs modèles (test d'architecture) ; chaque requête de la porte porte le filtre de date.
- **H1 inchangé** : `registry.yaml` et `build_frame` ne changent pas (jeu identique). Les 4 modèles de rejeu H1, réentraînés à neuf par `build_card` (donc par la garde), ont des coefficients et des hyperparamètres identiques aux modèles enregistrés. `inference check --only replay` : écart nul sur 7 156 matchs (`reports/inference/rejeu_2026-10-31.md`).

### 6.2 — Variables de stabilité du onze, G6 (2026-11-01)

`features/lineup_stability.py` : `compute_lineup_stability(matches, lineups, team_sheets)`, fonction pure (rapport H.3 et H.7, ADR-0047). Une ligne par (match, équipe) de championnat des échelles ; historique = matchs de **championnat terminés, d'un jour strictement antérieur, au onze complet**, limité au club, sans remise à zéro par saison. Le match évalué n'y figure jamais (H.2).

| Colonne | Définition |
|---|---|
| `xi_overlap_prev` | titulaires communs (0 à 11) avec le dernier match de l'historique |
| `xi_cohesion_ewm_h3`, `_h5`, `_h10`, `_h20`, `_hinf` | moyenne de s(s − 1) / 110 sur l'historique, poids 0,5^((rang − 1) / h) par rang de match (rang 1 = match précédent) ; `hinf` : poids égaux |
| `xi_new_starters` | titulaires de moins de 3 titularisations de championnat dans le club sur les 365 jours précédents |

- **Pourquoi pas de matrice** : la somme de la matrice cumulée restreinte au onze vaut Σ s_k(s_k − 1) (H.3). Un test construit la vraie matrice sur des compositions aléatoires et vérifie l'égalité.
- **Valeur vide** (jamais remplacée) : onze incomplet (moins de 11 titulaires identifiés, entrée sans identifiant ou exclue pour collision), match non joué, aucun match antérieur. Un match au onze incomplet sort aussi de l'historique des suivants. Rien n'est rempli.
- **Cinq demi-vies, une colonne chacune** : le choix par validation interne du pli (D2) se fera en 6.7, comme celui de la demi-vie de G2. Le groupe garde donc 3 variables par équipe, avec une demi-vie retenue.
- **Pas de fiche au registre ici** : `build_frame` et les contrôles exigent que les colonnes du jeu soient exactement celles de `registry.yaml` (`dataset.py`, `check.py`). Ajouter les fiches G6 maintenant casserait le jeu H1, qui doit rester identique. Les fiches (horizon H2, `{h}`) arrivent en 6.5, avec le branchement dans le jeu.
- **Catalogue** : le texte d'en-tête se déduit du registre (groupes et horizons présents), et G4 à G6 ont leur titre. Sortie actuelle inchangée.

Contrôles sur les données réelles (lecture seule, avant le scellé, `load_*` filtrés par compétition : 2,0 millions de lignes de composition, lecture 25 s, calcul 10 s) :

| Contrôle | Résultat |
|---|---|
| Lignes | 197 002 (match, équipe) ; top 5 des plis 2021-22 à 2024-25 : 14 342 lignes, **0 % de valeurs vides** |
| Valeurs vides, top 5 | au plus 0,57 % par saison de 2014-15 à 2020-21 (onzes incomplets) |
| Invariance à la troncature | 0 écart sur toutes les colonnes aux coupes du 2019-01-01 (146 316 lignes) et du 2023-03-01 (179 020 lignes) |
| Plis (2021-24, top 5) | recouvrement moyen 8,3 sur 11 ; nouveaux titulaires 0,82 en moyenne |
| Corrélation avec `xi_overlap_prev` | 0,71 (h3), 0,61 (h5), 0,48 (h10), 0,38 (h20), 0,15 (hinf) : la cohésion longue apporte autre chose que le recouvrement |
| Garde H1 | aucun fichier de `modeling/`, ni `registry.yaml`, ni `dataset.py` touché ; `inference check --only replay` : rejeu reproduit (`reports/inference/rejeu_2026-11-01.md`) |

Le rapport H.3 annonçait plus de 0,9 de corrélation entre paires et recouvrement : ce n'est vrai que pour la version « remise à zéro » (poids égaux sur une saison) ; ici, sans remise à zéro, ce n'est pas le cas pour les longues demi-vies. À regarder en 6.6.

### 6.3 — Variables de qualité du onze, G5 (2026-11-01)

`features/xi_quality.py` : `compute_xi_quality(matches, lineups, team_sheets)`, fonction pure (ADR-0013 décision 3 et règles 3 et 4, ADR-0047 D3 et D9). Une ligne par (match, équipe) de championnat des échelles ; mêmes onzes complets et mêmes jours « strictement antérieurs » que G6.

| Colonne | Définition |
|---|---|
| `xi_quality` | moyenne des 11 titulaires de `(M·r̄ + k·μ) / (M + k)` : r̄ = note moyenne du joueur pondérée par les minutes, M = ses minutes notées antérieures, μ = note moyenne (minutes) du poste avant le jour du match, k = 772,6 minutes. Sans note antérieure : μ |
| `xi_regulars_missing` | part des « habituels » du club (au moins 5 débuts sur les 10 derniers matchs de l'historique) absents du onze ; vide avec moins de 10 matchs d'historique |
| `xi_mean_age` | âge moyen des titulaires en années au jour du match ; vide si une date de naissance manque |

- **Rétrécissement bayésien empirique** (`xi_quality_estimation.py`, une seule fois, 20 s) : note d'une apparition de w minutes = θ_joueur + bruit de variance σ²/w ; θ de variance τ² par poste ; **k = σ² / τ²**. Méthode des moments sur **2015-16 à 2019-20 seulement** (dans l'apprentissage des quatre plis, aucune note de validation) : σ² = 20,6, τ² = 0,0267, **k = 772,6 minutes** (environ 8,6 matchs complets), 9 001 joueurs, 446 381 apparitions. Figé dans `features/params/xi_quality.json`, chiffres dans `reports/variables/xi_quality.md`. Un joueur à M = k minutes est rétréci pour moitié.
- **Poste** : celui de la composition annoncée de m (connu à T-60) ; à défaut, le dernier poste connu du joueur dans le passé. Une apparition passée prend le poste de la composition, à défaut celui des statistiques du match. Le poste ne vient donc jamais des statistiques du match évalué (l'ADR-0013 dit « le poste vient des statistiques joueurs » : écart voulu, ces statistiques sont postérieures à T-60).
- **Nettoyage** : note hors de 3 à 10 ou minutes hors de 1 à 130 → apparition inutilisable pour la note (elle compte encore pour le poste et le onze).
- **Règle entre championnats (D9 a)** : une recrue sans note dans les échelles reçoit μ, sans correction par championnat. Les notes de la D2 et du top 5 sont mélangées pour les joueurs qui ont joué dans les deux ; μ est commun à toutes les ligues. Décomptes ci-dessous.
- **Limites** : la note API est calculée après le match par le fournisseur (rapport I.8). `xi_regulars_missing` compte un départ comme une absence tant que le joueur est dans la fenêtre (blessé et parti ne se distinguent pas).
- **Pas de fiche au registre ici** (raison de 6.2) : les fiches G5 et G6 arrivent en 6.5 avec le branchement dans le jeu.

Contrôles sur les données réelles (lecture seule, avant le scellé, mêmes lectures filtrées par compétition que pour 6.2 ; calcul 7 s) :

| Contrôle | Résultat |
|---|---|
| Lignes | 197 002 (match, équipe) |
| Plis 2021-24, top 5 (14 342 lignes) | `xi_quality` vide pour 0,15 % (21 lignes), les deux autres colonnes pour 0 % |
| Rodage 2015-16, top 5 | vides : 1,04 % (`xi_quality`), 0,82 % (habituels), 1,10 % (âge) ; **4,07 % des titulaires sans note antérieure** (0,27 à 0,34 % sur les plis). Avant 2015-16 : notes absentes (2014-15 : 86 % de `xi_quality` vide, avant : 100 %) |
| Titulaires sans note antérieure (D9) | 0,3 % sur les plis ; moins de 450 minutes notées : 3,3 %. Très loin du seuil de 10 % : la variante corrigée par championnat (D9 b) n'est pas déclenchée |
| Invariance à la troncature | 0 écart sur les 3 colonnes aux coupes du 2019-01-01 (146 316 lignes) et du 2023-03-01 (179 020 lignes) |
| Calcul indépendant | 60 lignes des plis recalculées titulaire par titulaire avec un filtre pandas naïf : écart nul |
| Plis, valeurs | `xi_quality` 6,95 en moyenne (écart type 0,08) ; habituels absents 0,32 ; âge moyen 27,0 ans |
| Corrélations entre elles (plis) | `xi_quality` / habituels : −0,08 ; `xi_quality` / âge : 0,14 ; habituels / âge : −0,07 |
| Corrélation avec G6 (plis) | `xi_regulars_missing` : −0,85 avec `xi_cohesion_ewm_h5`, −0,83 avec h3, −0,80 avec h10, −0,46 avec `xi_overlap_prev` ; `xi_quality` : au plus 0,24 en valeur absolue (h∞) |
| Garde H1 | aucun fichier de `modeling/`, ni `registry.yaml`, ni `dataset.py` touché ; `inference check --only replay` : rejeu reproduit, écart nul |

À regarder en 6.6 : **les habituels absents recouvrent largement la cohésion de G6** (corrélation de −0,85). Ce n'est pas une raison de changer une définition fixée avant les plis ; l'ablation de 6.7 (G5 ajouté après G6, D1) dira si le groupe apporte quelque chose de plus.

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
