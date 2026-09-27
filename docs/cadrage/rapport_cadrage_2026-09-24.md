> **Instantané du 24/09/2026.** Ce rapport n'est plus modifié. En cas de désaccord, les décisions de `docs/decisions/` (ADR) font foi.

# Rapport de cadrage — foot-predictor

**Projet** : prédiction du nombre de buts d'un match de football, projet d'apprentissage individuel
**Date** : 24 septembre 2026
**Dépôt analysé** : `github.com/leonardgst/foot-predictor`, branche `main`, commit `8b9e9b3` (la branche `dev` est identique à `main`)
**Statut** : document de cadrage à discuter. Aucun fichier du dépôt n'a été modifié.

**Méthode d'analyse.** Lecture complète des 139 fichiers suivis (code, migrations, configuration, tests, 16 documents). Exécution de la suite de tests sans base de données : **112 tests passent**, 66 tests marqués `db` n'ont pas pu être lancés, faute de Postgres dans mon environnement. Les faits sur API-FOOTBALL et les sources externes ont été vérifiés en ligne quand c'était possible ; les points non vérifiables sont marqués **« à vérifier »**.

**Limites.** Je n'ai accès ni à ta base locale ni à l'état réel du backfill API-FOOTBALL lancé le 22 septembre. Plusieurs recommandations de la partie G en dépendent : l'annexe 1 donne les requêtes SQL, en lecture seule, qui permettent de les vérifier.

---

## Synthèse en une page

**Le dépôt est plus avancé et mieux pensé que la moyenne d'un projet d'apprentissage.** On y trouve :

- une architecture en couches `raw` / `staging` / `features` ;
- une discipline anti-fuite explicite, avec des tests ;
- une infrastructure Docker, Alembic et CI ;
- un modèle de Poisson qui fonctionne, et un service d'inférence ;
- une documentation abondante des décisions et des incidents.

Il n'y a pas lieu de repartir de zéro.

**En revanche, le cœur « données » repose sur des choix qui vont bloquer la suite si on ne les corrige pas maintenant, c'est-à-dire avant la fin de l'abonnement :**

1. **Les joueurs sont identifiés par leur nom, pas par leur identifiant API-FOOTBALL** (`ingestion/api_football.py` l. 93, 97, 194 ; `ingestion/common.py::get_or_create_player`). Deux joueurs homonymes, par exemple deux « Danilo », seraient fusionnés. Or l'indicateur de stabilité, l'âge et tout indicateur de qualité des joueurs reposent sur cette identité.
2. **L'ingestion staging des statistiques joueurs va très probablement planter.** L'API renvoie les postes sous la forme `"G"`, `"D"`, `"M"`, `"F"`, alors que l'enum Postgres attend `Goalkeeper`, `Defender`, etc. (`api_football.py` l. 137 ; `db/models.py`). Aucun test ne couvre ce module. Ce point est à vérifier sur un payload réel, mais c'est très probable.
3. **La collecte consomme environ 20 fois plus de requêtes que nécessaire.** Le paramètre `fixtures?ids=` accepte jusqu'à 20 matchs par appel, avec compositions, événements, statistiques et joueurs. De plus, elle ignore le champ `errors` de l'API et vérifie les doublons par un parcours complet du JSONB, qui ralentit à mesure que la table grossit (`api_football_scraper.py` l. 70-86).
4. **Le brut n'est pas brut.** football-data ne conserve que 7 champs sur plus de 100 colonnes : **les cotes annoncées dans le README sont jetées**, alors que c'est le meilleur point de comparaison pour un modèle de buts. Understat et le brut joueurs perdent de même les identifiants sources. Et le brut ne vit que dans un volume Docker : aucune copie fichier.
5. **Les saisons 2025-2026 (terminée) et 2026-2027 (en cours) ne sont collectées nulle part** (`range(2015, 2025)` dans 4 scripts).
6. **Après l'abonnement, le plan gratuit d'API-FOOTBALL ne donne accès qu'aux saisons 2022 à 2024.** Le guide `docs/API_FOOTBALL_ABONNEMENT.md` (§5, point 7) suppose que les mises à jour quotidiennes tiendront dans le plan gratuit, point qu'il marque lui-même « à vérifier » : ce n'est pas le cas pour la saison en cours. L'application « prochains matchs avec composition » ne pourra donc pas tourner en continu gratuitement : il faut le prévoir dès maintenant dans l'architecture.
7. **Il n'existe pas de modèle de référence naïf.** Le log-loss de 2,933 du modèle A n'est comparé qu'au modèle B, et les métriques portent sur le 1N2 et le score exact, pas sur le nombre de buts.
8. **La valeur marchande maison (le MVS, `market_value/`) est très arbitraire.** Les pondérations sont fixées à la main, la composante « réputation » duplique le classement déjà présent dans les variables, et le calcul par date de référence est lourd. Je recommande de la mettre en pause.
9. **L'indicateur de stabilité n'est pas implémenté**, seulement spécifié (`docs/RECAP_PROJET.md` §8). Mathématiquement, il se ramène à une moyenne du recouvrement entre le onze du jour et les onze passés (démonstration en H). La remise à zéro par saison le rend indéfini au premier match, bruité au début et figé en fin de saison.
10. **Trois bases (dev / test / prod Neon)**, des corrections faites à la main uniquement en dev, et une branche `dev` : c'est trop lourd pour une personne seule, et cela a déjà produit des divergences.

**Recommandation générale : une refonte ciblée du cœur de données, pas une réécriture.** On garde l'infrastructure, la modélisation, les tests et la discipline anti-fuite. On reconstruit la collecte (fichiers bruts et lots de 20) et le référentiel (identifiants sources) pendant l'abonnement. On reporte le MVS. On ajoute une référence naïve, une validation glissante et des métriques centrées sur les buts.

**Les 20 jours d'abonnement doivent servir en priorité à sécuriser des données impossibles à récupérer gratuitement plus tard**, et non à développer. Avec la collecte par lots, le quota n'est plus la contrainte : tout le périmètre utile tient en 2 à 3 jours de quota. Les vraies contraintes sont la justesse du code de collecte, la sauvegarde et ton temps.

---

## A. Reformulation du projet

### A.1 Le besoin

Construire, seul et à des fins d'apprentissage, un système complet capable d'estimer **combien de buts seront marqués** dans un match de championnat. Il doit pouvoir **mesurer honnêtement** ce qu'apporte chaque famille de variables : force des équipes, avantage du terrain, championnat, entraîneur, stabilité du onze, masse salariale ou son substitut. La prédiction elle-même compte moins que la **démarche** : données disponibles avant le match, absence de fuite, comparaison équitable, incertitude explicite.

### A.2 Le produit final

Une application locale qui :

- liste les prochains matchs, filtrables par championnat ;
- indique pour chaque match si les données nécessaires sont disponibles ;
- active ou désactive un bouton « Prédiction » en conséquence ;
- affiche le nombre de buts attendu **et sa distribution** : probabilité de 0, 1, 2… buts, intervalle, probabilité de plus de 2,5 buts ;
- explique la prédiction : variables utilisées et leurs valeurs, variables manquantes, date de récupération des données, version du modèle, raison pour laquelle une prédiction est possible ou impossible.

Derrière l'interface, les briques sont séparées : collecte, stockage, transformation, indicateurs, entraînement, évaluation, inférence, API, interface.

### A.3 Les objectifs pédagogiques

Git, architecture réseau, structuration d'un projet Python, statistiques inférentielles, apprentissage supervisé et non supervisé, modélisation, pipelines entre applications, ingestion et stockage, tests, API (exposer et consommer), présentation des résultats, documentation technique et fonctionnelle.

La règle du jeu : **chaque technologie doit répondre à un besoin concret**, être gratuite, compréhensible, documentée, et tourner sur un portable de 3-4 ans.

### A.4 Les contraintes

- **Temps** : environ 10 h par semaine, seul.
- **Argent** : aucun serveur ni service payant. L'abonnement API-FOOTBALL Pro (7 500 requêtes par jour) est déjà payé et expire dans environ 20 jours.
- **Matériel** : portable HP classique sous Windows, d'après les récaps (incidents « services.msc », BOM, console). Il peut rester allumé la nuit.
- **Juridique** : n'utiliser que des sources dont les conditions le permettent. Le dépôt a déjà écarté Transfermarkt pour cette raison.

### A.5 La méthode de travail

Une session Claude liée au projet sert à préparer la tâche. Claude Code fait les modifications, avec `CLAUDE.md` et le fichier d'état comme mémoire entre sessions. Tu vérifies, lances les tests, relis la différence et fais les opérations Git. La documentation de suivi est mise à jour à chaque session.

---

## B. Analyse de l'existant

### B.1 Vue d'ensemble chiffrée

| Élément | État constaté |
|---|---|
| Code Python | 5 395 lignes dans `src/foot_predictor/` (6 sous-paquets) |
| Tests | 178 tests (`tests/`, organisés comme `src/`) : 112 sans base, qui passent ; 66 marqués `db` |
| Base de données | PostgreSQL 16, 22 tables sur 3 schémas, migrations Alembic 0001 à 0003 |
| Données (selon les docs) | 18 011 matchs 2015-16 → 2024-25, 5 championnats ; xG équipe à 99,98 % ; compositions en cours de collecte depuis le 22/09 |
| Modélisation | Modèle A (Poisson GLM) retenu, modèle B (Dixon-Coles hybride) écarté, recalibration non adoptée |
| Inférence | Service Python (`modeling/predict_service.py`), sans API ni interface |
| Documentation | 16 fichiers Markdown dans `docs/` (environ 3 600 lignes), dont 11 dans `docs/recaps/` |
| Historique Git | 38 commits, dont 27 le 22/09 ; branches `main` et `dev` identiques ; 4 PR fusionnées ; aucun tag |

### B.2 Architecture actuelle

```
football-data.co.uk (CSV) ─┐
Understat (understatapi) ──┼─► *_scraper.py ─► raw.* (jsonb, Postgres) ─► ingestion/*.py ─► staging.* ─► features/*.py ─► features.team_match_features
API-FOOTBALL (/fixtures?id)┘                                                                                                       │
                                                                                            modeling/dataset.py ◄──────────────────┘
                                                                                                   │
                                                              run_comparison.py / train_and_persist.py ─► models/*.joblib ─► predict_service.py
market_value/ (MVS, clustering HDBSCAN) : écrit, jamais exécuté sur des données réelles
```

Environnements : `dev` (Docker, port 5440), `test` (Docker, port 5433), `prod` (Neon, cloud gratuit), sélectionnés par `APP_ENV` (`config.py`). Workflow Git : `feature/*` → `dev` → `main`.

### B.3 Points positifs

| Constat | Où |
|---|---|
| Séparation `raw` / `staging` / `features`, avec la règle « le modèle ne lit que `features` » | `docs/RECAP_PROJET.md` §5, `db/models.py` |
| Discipline anti-fuite réelle : `match_date < before_date` partout, jointure sur le bon `match_id`, test dédié | `features/rolling_*.py`, `features/standing.py`, `modeling/dataset.py`, `tests/modeling/test_dataset.py` |
| Découpage chronologique, jamais aléatoire, et hyperparamètre ξ choisi sur une validation interne au jeu d'entraînement | `modeling/split.py`, `modeling/run_comparison.py::_select_xi` |
| Même code pour les variables d'entraînement et d'inférence (pas d'écart entre les deux) | `modeling/live_features.py` réutilise les fonctions de `features/` |
| Refus explicite de prédire sans historique suffisant plutôt qu'une valeur inventée | `predict_service.InsufficientFeatureHistoryError` |
| Collecte relançable sans doublon, journal d'ingestion | `raw.source_ingestion_log`, fonctions `_upsert_*` |
| Tests bien ciblés sur les zones à risque silencieux : réconciliation, fenêtres glissantes, calcul par 90 minutes, Dixon-Coles | `tests/` ; exécution sans base qui passe en 6 s |
| CI GitHub Actions avec `uv` | `.github/workflows/tests.yml` |
| Secrets hors Git (`.gitignore` créé avant les `.env`), clé API en variable d'environnement | `.gitignore`, `API_FOOTBALL_ABONNEMENT.md` §5 |
| Honnêteté des résultats : modèle B moins bon et recalibration inutile, documentés plutôt que masqués | `docs/RESULTATS_MODELE.md` |
| Incidents et leçons documentés | `docs/RECAP_PROJET.md` §9 et §12 |
| Dépendances raisonnables et gérées par `uv` (lockfile commité) | `pyproject.toml`, `uv.lock` |

### B.4 Faiblesses, incohérences et risques

La gravité se lit ainsi : **Critique** = bloque la suite ou corrompt les données ; **Haute** = fausse les résultats ou fait perdre la fenêtre d'abonnement ; **Moyenne** = dette technique qui ralentit ; **Faible** = hygiène.

**Données et collecte**

| # | Constat | Fichier | Gravité |
|---|---|---|---|
| D1 | Joueurs résolus par **nom** et non par identifiant source (`source_ref = p["name"]`, recherche par `full_name`). Les homonymes sont fusionnés, et les noms abrégés de l'API (du type « K. Mbappé ») ne correspondront vraisemblablement pas aux noms complets d'Understat. | `ingestion/api_football.py` l. 93, 97, 194 ; `ingestion/common.py` l. 281-316 ; `ingestion/injuries.py` ; `ingestion/understat_player.py` l. 51 | **Critique** |
| D2 | Équipes API-FOOTBALL résolues par **nom** (et non par `team.id`). Exemple concret : `api_football_teams.yaml` l. 9 contient encore `Ajaccio: GFC Ajaccio`, alors que la correction documentée (`recap_backfill_10_saisons_et_bug_xg.md` §3.1) l'a faite dans les deux autres YAML. Les matchs d'AC Ajaccio 2022-23 ne seront pas rattachés. | `ingestion/api_football.py` l. 38-39 ; `mappings/api_football_teams.yaml` | Haute |
| D3 | `position_bucket = games.position` : l'API renvoie `G`/`D`/`M`/`F`, l'enum attend `Goalkeeper`/`Defender`/… Plantage probable dès la première ligne (à vérifier avec la requête de l'annexe 1). | `ingestion/api_football.py` l. 137 ; `db/models.py` (`position_bucket_enum`) | **Critique** |
| D4 | Un appel par match (`/fixtures?id=`) alors que `/fixtures?ids=` accepte 20 identifiants et renvoie compositions, événements, statistiques et joueurs. Environ 18 000 requêtes au lieu d'environ 950. | `ingestion/api_football_scraper.py` l. 60-67 | Haute |
| D5 | Le champ `errors` de la réponse API n'est jamais lu, et les en-têtes de quota ne sont pas surveillés. Une restriction de plan ou un paramètre invalide renvoie une liste vide, journalisée « success ». Seuls les `RequestException` sont gérés : tout autre plantage annule les données de la saison en cours de traitement. | `api_football_scraper.py` l. 55, 65, 136-142 ; `injuries_scraper.py` | Haute |
| D6 | Vérification des doublons par `raw_payload['fixture']['id']` **sans index**. Chaque vérification relit tous les JSON déjà stockés : le coût total de la collecte croît comme le carré du nombre de matchs. Aucune migration ne crée d'index en dehors des clés primaires et des contraintes d'unicité (pas d'index sur les clés étrangères). | `api_football_scraper.py` l. 70-86 ; `migrations/versions/*` | Moyenne |
| D7 | Le « brut » est transformé. football-data : 7 champs conservés sur plus de 100 (cotes, heure, tirs, arbitre perdus), alors que le README annonce « résultats et cotes ». Understat joueur : l'identifiant de joueur est perdu. | `football_data_scraper.py` l. 71-80 ; `understat_player_scraper.py` `_build_payload` | Haute |
| D8 | Le brut n'existe que dans Postgres (volume Docker). Un `docker compose down -v`, la commande de reset documentée, efface des données payantes impossibles à recollecter après l'abonnement. | `docker-compose.yml`, `RECAP_PROJET.md` §5 | **Critique** |
| D9 | Saisons 2025-26 et 2026-27 absentes : `range(2015, 2025)` en dur à 4 endroits. | `football_data_scraper.py` l. 156 ; `api_football_scraper.py` l. 162 ; `injuries_scraper.py` l. 102 ; `understat_scraper.py` l. 117 | Haute |
| D10 | Aucune date de naissance n'est alimentée par aucune source : `squad_avg_age` et la composante « Potentiel » du MVS sont donc incalculables, contrairement à ce qu'indique le README. | `common.py::get_or_create_player` (appelé sans `birth_date`) | Moyenne |
| D11 | Corrections faites à la main uniquement en base dev : 19 fusions, renommages Ajaccio, `TeamSourceMapping` repointé. Le référentiel n'est pas reproductible depuis le code. | `RECAP_PROJET.md` §9.3 ; `recap_backfill_…md` §5 ; `scripts/one_off/fusion.py` | Haute |
| D12 | Seuls les championnats sont collectés : pas de coupes, pas de deuxièmes divisions. Les fenêtres glissantes d'une équipe promue reprennent ses matchs d'il y a plusieurs années, faute de limite d'ancienneté. Les jours de repos et la rotation liée aux coupes d'Europe sont invisibles. | `features/rolling_form.py`, `rolling_xg.py` | Moyenne |
| D13 | Statut juridique d'Understat non documenté, alors que le dépôt applique un critère strict à Transfermarkt. Mon outil de lecture web a été refusé par le `robots.txt` d'Understat : il faut vérifier si cela vise tous les robots ou seulement certains agents. | `understat_scraper.py`, `OBJECTIFS.md` §3 | Moyenne (à vérifier) |

**Modélisation et évaluation**

| # | Constat | Fichier | Gravité |
|---|---|---|---|
| M1 | Aucun modèle de référence naïf ni référence de marché : impossible de dire si 2,933 de log-loss est « bon ». | `modeling/run_comparison.py`, `docs/RESULTATS_MODELE.md` | Haute |
| M2 | Métriques orientées 1N2 et score exact. Rien sur le **total de buts** : ni log-loss du total, ni RPS, ni Brier sur plus/moins de 2,5 buts, ni couverture d'intervalle. | `modeling/evaluation.py` | Haute (écart avec le besoin) |
| M3 | Une seule saison de test (2024-25), désormais « consommée » : les décisions A contre B et la recalibration ont été prises en la regardant. | `run_comparison.py` (`CUTOFF_DATE`) | Moyenne |
| M4 | `predict_lambda` complète silencieusement les colonnes manquantes par 0 (`fill_value=0.0`). Une variable absente à l'inférence produit une prédiction fausse sans erreur. | `modeling/poisson_model.py` l. 25 | Moyenne |
| M5 | Le classement est calculé par saison : il est donc indéfini pour **toute la 1re journée** de chaque saison, et très bruité ensuite. Ces lignes sont écartées (`dropna`, 1 226 lignes, soit essentiellement les 1res journées et certains promus). Cela biaise l'évaluation vers les situations faciles, et l'application refusera de prédire **tous les matchs de la 1re journée**. | `modeling/dataset.py`, `live_features.py` | Moyenne |
| M6 | Le MVS repose sur des pondérations à dire d'expert (`weights.py` vide, repli uniforme). La « Réputation » est une fonction linéaire du classement, déjà en variable. HDBSCAN est ré-entraîné par date de référence : coûteux et invérifiable faute de vérité terrain. | `market_value/**` | Moyenne (à reporter) |
| M7 | Les deux lignes d'un même match sont traitées comme indépendantes dans le GLM : les erreurs standard sont légèrement optimistes (sans conséquence sur les prédictions). | `modeling/poisson_model.py` | Faible (point pédagogique) |
| M8 | Pas de traçabilité du modèle : ni hash des données, ni commit Git, ni métriques dans l'artefact `joblib` ; pas de table des prédictions. | `modeling/persistence.py` | Moyenne |

**Infrastructure, Git et documentation**

| # | Constat | Fichier | Gravité |
|---|---|---|---|
| I1 | Trois bases, dont une prod sur Neon (cloud). L'offre gratuite de Neon est limitée en stockage : le brut JSON de dizaines de milliers de matchs ne tiendra pas. Il n'y a de toute façon rien à « mettre en production » dans le cloud. | `README.md`, `.env.example`, `config.py` | Moyenne |
| I2 | Branche `dev` en plus de `main` : double fusion sans bénéfice seul. De plus, la protection de branche n'existe pas pour un dépôt **privé** sur GitHub Free. | Historique Git ; [GitHub Docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) | Faible |
| I3 | La CI ne lance que les tests sans base : les tests anti-fuite marqués `db` ne tournent jamais automatiquement. | `.github/workflows/tests.yml` | Moyenne |
| I4 | Pas d'analyseur de code, de formateur ni de hooks pre-commit ; `pyproject.toml` contient encore `description = "Add your description here"`. | `pyproject.toml` | Faible |
| I5 | Environnement Windows natif. Plusieurs incidents lui sont liés : BOM dans les `.env`, emojis et `PYTHONIOENCODING`, conflit avec un Postgres natif sur le port 5432. | `RECAP_PROJET.md` §9.1, `check_env.py` | Moyenne |
| I6 | La documentation dérive : `docs/recaps/README.md` dit encore « tests/ toujours vide » et « choix du modèle ⬜ », le README dit l'inverse ; §11 du RECAP : « Commit + push de l'état courant ⬜ ». Le même contenu est réparti sur `README`, `RECAP_PROJET` (594 lignes) et 11 récaps. | `docs/**` | Moyenne |
| I7 | Pas de `CLAUDE.md`, pas de fichier d'état concis, pas de journal d'erreurs dédié, pas de LaTeX. | Racine, `docs/` | Écart avec le besoin |
| I8 | Deux identités Git dans l'historique (`leonardgst <goussetleonard@…>` et `Léonard Gousset <…noreply…>`). | `git log` | Faible |
| I9 | `.env.example` ne mentionne ni `API_FOOTBALL_KEY` ni `APP_ENV`. Or une tâche planifiée n'hérite pas d'un `export` fait dans le terminal. | `.env.example`, `check_env.py` | Faible |
| I10 | La dépendance `hdbscan` (extension C, compilation délicate sous Windows) sert uniquement au MVS mis en pause ; `scikit-learn` fournit un `HDBSCAN` depuis la version 1.3. | `pyproject.toml` | Faible |

### B.5 Niveau d'avancement par brique

| Brique | Avancement | Commentaire |
|---|---|---|
| Infrastructure locale (Docker, Alembic, uv, CI) | ██████████ 90 % | À simplifier (bases, branches), pas à construire |
| Collecte football-data et Understat (équipe) | ███████░░░ 70 % | Fonctionne ; brut incomplet, saisons manquantes |
| Collecte API-FOOTBALL | ████░░░░░░ 40 % | Fonctionne mais inefficace et fragile ; périmètre trop étroit |
| Référentiel staging (identités) | ████░░░░░░ 40 % | Équipes réconciliées à la main ; joueurs mal identifiés |
| Variables (features) | █████░░░░░ 50 % | z1-z8 en place ; rien sur les compositions, l'Elo, le repos, l'entraîneur |
| Modélisation | ██████░░░░ 60 % | Poisson et Dixon-Coles corrects ; pas de référence, pas de métriques buts, pas de régression linéaire (point de départ demandé) |
| Évaluation | ████░░░░░░ 40 % | Un seul découpage ; métriques 1N2 et score exact |
| Inférence | █████░░░░░ 50 % | Service Python ; pas de disponibilité par variable ni de traçabilité |
| API | ░░░░░░░░░░ 0 % | — |
| Interface | ░░░░░░░░░░ 0 % | — |
| Documentation | ██████░░░░ 60 % | Riche mais redondante et dérivante ; structure demandée absente |

### B.6 Écarts avec le projet décrit dans ta mission

| Besoin exprimé | Situation dans le dépôt |
|---|---|
| Cible : nombre de buts, distribution | Cible : score exact et 1N2 (`MODELE_MATHEMATIQUE.md` §1.1). Le modèle par équipe convient, mais les métriques et la sortie produit sont à réorienter vers le total. |
| Progression pédagogique depuis ŷ = AX + B | Le document mathématique commence directement par le Poisson ; pas de régression linéaire dans le code. |
| Ensembles de variables progressifs (2, 4, 5, 7, 8…) | Liste fixe z1-z8 (`features_config.py`) ; pas de mécanique d'ablation. |
| Masse salariale ou substitut | Transfermarkt abandonné (à juste titre), remplacé par le MVS arbitraire. |
| Entraîneur | Absent (pourtant présent dans les compositions API-FOOTBALL déjà téléchargées). |
| Stabilité du onze | Spécifiée, non implémentée ; remise à zéro par saison figée « V1 ». |
| Application avec disponibilité, raisons, version du modèle, dates | Rien au-delà du service Python. |
| API et architecture réseau | Absentes. |
| `docs/cadrage`, `docs/realisation`, état, journal, `CLAUDE.md`, 2 LaTeX | Absents (la structure actuelle est « récaps »). |
| Local et gratuit | Une prod sur Neon (cloud). |
| Fin de l'abonnement anticipée | Le guide suppose une continuité via le plan gratuit (« à vérifier ») ; or ce plan ne couvre pas la saison en cours. |

### B.7 Verdict par élément

| Élément | Verdict | Détail |
|---|---|---|
| `pyproject.toml`, `uv.lock`, `.python-version` | **Conserver**, compléter | Description, ruff, pre-commit, groupes de dépendances. |
| `docker-compose.yml` | **Conserver**, compléter | Plus tard : services `api` et `ui`, healthchecks. |
| `.env.example`, `config.py` | **Corriger** | Ajouter `API_FOOTBALL_KEY` (en `SecretStr`), les chemins de données ; supprimer le cas Neon. |
| Base prod Neon | **Supprimer** (reporter si besoin réel) | Voir I1 et décision 14. |
| Branche `dev` | **Supprimer** | Voir J. |
| `db/models.py`, migrations 0001-0003 | **Conserver**, compléter | Nouvelle migration 0004 : colonnes d'identifiants sources, index, tables coach, fixture_team_stats, prédictions et métadonnées. Pas de réécriture des migrations passées. |
| `raw.*` (JSONB) | **Remplacer** progressivement | Les fichiers JSON compressés deviennent la source de vérité ; les tables `raw` deviennent un simple journal ou une copie facultative. |
| `ingestion/api_football_scraper.py` | **Remplacer** (urgent, pendant l'abonnement) | Lots de 20, lecture de `errors` et des en-têtes, fichiers, reprise, index. |
| `ingestion/api_football.py` | **Corriger** | Identifiants sources, postes, coach, formation, grille, minutes, statistiques d'équipe. |
| `ingestion/common.py` | **Corriger**, simplifier | Réconciliation par identifiant source ; noms seulement en secours. |
| `ingestion/football_data_scraper.py` | **Corriger** | Conserver toute la ligne CSV (dont cotes et heure) ; saisons paramétrables. |
| `ingestion/understat*.py` | **Conserver** sous réserve (décision 17) | Vérifier le statut juridique ; conserver l'identifiant joueur Understat. |
| `ingestion/injuries*.py` | **Compléter**, reporter l'usage | Identifiant joueur ; blessures hors modèle MVP. |
| `mapping_builder/`, `mappings/*.yaml` | **Simplifier** | Avec des identifiants sources, les YAML ne servent qu'au rapprochement football-data et Understat vers API-FOOTBALL, et doivent être versionnés comme des données. |
| `scripts/one_off/` | **Déplacer** (archives) | Les corrections deviennent des YAML versionnés, rejouables. |
| `features/*` | **Conserver** la logique, **compléter** | Limite d'ancienneté des fenêtres, Elo, repos, entraîneur, compositions, stabilité ; calcul vectorisé. |
| `modeling/dataset.py`, `split.py` | **Conserver**, compléter | Validation glissante multi-saisons ; groupes de variables. |
| `modeling/poisson_model.py` | **Corriger** | Échec explicite si une colonne manque au lieu du remplissage par 0. |
| `modeling/dixon_coles.py`, `calibration.py` | **Conserver** | Comme modèles candidats. |
| `modeling/evaluation.py` | **Compléter** | Métriques du total de buts, intervalles, calibration, bootstrap. |
| `modeling/predict_service.py`, `live_features.py`, `persistence.py` | **Conserver**, compléter | Disponibilité par variable, carte d'identité du modèle, écriture des prédictions. |
| `market_value/` | **Reporter** (geler) | Garder le code et les tests ; hors MVP ; possible module « non supervisé » plus tard. |
| `tests/` | **Conserver**, compléter | Tests d'ingestion API sur des payloads réels anonymisés, test d'équivalence de la stabilité, tests de bout en bout. |
| `.github/workflows/tests.yml` | **Compléter** | Service Postgres pour lancer les tests `db` ; ruff. |
| `check_env.py` | **Conserver**, déplacer | Vers une commande de la CLI (`fp doctor`). |
| `docs/*` | **Restructurer** | Voir K : les récaps passent dans `docs/archives/`, le contenu vivant dans cadrage, réalisation et décisions. |

### B.8 Faut-il une refonte ?

**Une refonte partielle et ciblée, oui ; une réécriture, non.** Voici pourquoi.

- **Ce qui doit être refait maintenant**, collecte et identités, est précisément ce qui conditionne des données **payantes et temporaires**. Chaque jour d'abonnement passé avec l'ancien collecteur est un jour de moins pour élargir le périmètre, et un risque de plus de données mal identifiées.
- **Ce qui est bien conçu**, couches, anti-fuite, tests, modèles, se réutilise tel quel. Le coût de le refaire serait élevé, pour un gain nul.
- **Reconstruire `staging` depuis des fichiers bruts** plutôt que corriger la base à la main supprime une dette qui s'accumule (19 fusions manuelles, corrections uniquement en dev). C'est aussi un excellent exercice : un pipeline reproductible de bout en bout.

Le reste (API, interface, documentation, LaTeX) est à **construire**, pas à refondre.

---

## C. Faisabilité

### C.1 Faisabilité technique : **élevée**

Toutes les briques nécessaires sont gratuites, locales et déjà partiellement en place : Python, Postgres, Docker, `statsmodels`, `scikit-learn`. L'API (FastAPI) et l'interface (Streamlit) sont des ajouts de taille modeste. Le seul point techniquement délicat est la **reconstruction du référentiel par identifiants sources**. C'est aussi le plus formateur.

### C.2 Faisabilité statistique : **bonne, à condition de fixer des attentes réalistes**

- **Volume** : environ 20 000 matchs de championnat « top 5 » sur 11 saisons. C'est largement suffisant pour des GLM à quelques dizaines de paramètres, et correct pour du gradient boosting régularisé.
- **Plafond intrinsèque.** Le nombre de buts est une variable très bruitée. Si T suit une loi de Poisson de paramètre λ, avec λ ≈ 2,8 buts par match, la variance *irréductible* est λ ≈ 2,8. La variance « expliquable », celle de λ d'un match à l'autre, n'est que de l'ordre de 0,3 à 0,5. Même un modèle parfait aurait donc un **R² d'environ 10 à 15 %** et une erreur quadratique moyenne d'environ 1,65 but, contre environ 1,75 pour une moyenne constante (ordres de grandeur, à mesurer sur tes données). Conséquence importante :
  - juger le projet sur l'erreur de la prédiction ponctuelle serait décourageant et trompeur ;
  - il faut le juger sur des **métriques probabilistes** (log-loss, RPS, calibration), où les gains, petits mais réels, se mesurent correctement.
- **Détectabilité des petites variables.** Stabilité, entraîneur, masse salariale : leur apport marginal sera probablement faible une fois la force des équipes (Elo, xG) prise en compte. Pour distinguer un gain d'environ 0,002 de log-loss par match, il faut quelques milliers de matchs de test. La validation glissante sur 4 saisons (environ 7 000 matchs) le permet ; une seule saison de test (1 700 matchs), comme aujourd'hui, non.
- **Changements de régime** : matchs à huis clos (fin 2019-20 et 2020-21), où l'avantage du terrain s'effondre ; passage de la Ligue 1 à 18 clubs en 2023-24. Il faut les traiter explicitement.

### C.3 Disponibilité des données

| Donnée | Historique | Avant le match ? | Après l'abonnement |
|---|---|---|---|
| Résultats, calendrier | football-data depuis 1993 ; API-FOOTBALL | Oui | ✅ football-data (gratuit, mis à jour 2 fois par semaine) |
| Cotes (1N2, plus/moins de 2,5 buts, handicap asiatique ; ouverture et clôture) | football-data depuis 2000 (clôture depuis 2005, ouverture et clôture depuis 2019) | Oui (ouverture) | ✅ football-data, **à condition de garder toutes les colonnes** |
| xG équipe | Understat depuis 2014 | Oui (matchs passés) | ⚠️ Understat (scraping, statut à vérifier) |
| Compositions officielles | API-FOOTBALL (couverture ancienne à vérifier via `/leagues`) | ~20-60 min avant le coup d'envoi | ❌ Plan gratuit limité aux saisons 2022-2024 ([source](https://github.com/nimeshjm/fantasy-football/issues/58)) |
| Statistiques joueurs par match (dont `rating`) | API-FOOTBALL | Oui (matchs passés) | ❌ |
| Entraîneur | Compositions API-FOOTBALL (par match) + `/coachs` (carrière) | Oui | ❌ (mais l'ancienneté se déduit de l'historique) |
| Blessures et suspensions | `/injuries` (couverture ancienne à vérifier) | Partiellement | ❌ |
| Dates de naissance | `/players` (par championnat et saison) | Oui | Statique une fois collectée |
| Transferts | `/transfers` | Oui | Statique une fois collectée |
| Masse salariale réelle | Non publique ; estimations payantes ou scrapées | — | ❌ |
| Valeur marchande | Transfermarkt : scraping interdit par les CGU | — | ❌ (écarté par le dépôt, et je confirme) |
| Elo | ClubElo : l'API CSV serait passée derrière une authentification, sans inscription ouverte pour l'instant (signalé le 23/09/2026, [source](https://github.com/probberechts/soccerdata/issues/977)) | — | ➜ **Elo calculé soi-même** depuis football-data |

### C.4 Faisabilité matérielle : **bonne**

Ordres de grandeur, à mesurer sur ta base avec la requête de taille de l'annexe 1 :

- brut API-FOOTBALL : environ 50 000 matchs à environ 60 Ko, soit **environ 3 Go en JSON, 0,3 à 0,5 Go compressé en gzip** ;
- tables staging : environ 2,5 millions de lignes de composition et de statistiques joueurs, **quelques centaines de Mo** avec index.

Un modèle GLM ou de boosting sur 40 000 lignes s'entraîne en quelques secondes à quelques minutes.

**Points d'attention** :

- la RAM, si Docker Desktop, WSL2, Postgres et pandas tournent ensemble : 8 Go est juste, 16 Go confortable ;
- l'espace disque libre, avec 10 Go de marge conseillés ;
- les écritures ligne à ligne de l'ORM, qui seront lentes sur 2,5 millions de lignes : il faudra des chargements par lots.

→ Décision 13 : **indique-moi la RAM, le disque libre et la version de Windows.**

### C.5 Faisabilité temporelle : **MVP en 5 à 6 mois à 10 h par semaine**

Le détail est en L. Le sprint de collecte (3 semaines) est prioritaire et en partie automatisable : les scripts tournent la nuit. Claude Code accélère l'écriture du code, mais **pas** la relecture, la compréhension et l'analyse. Or c'est là que se trouve l'objectif pédagogique : il faut prévoir environ 40 % du temps pour relire et comprendre.

### C.6 Risques liés à la fin de l'abonnement

| Risque | Probabilité | Impact | Parade |
|---|---|---|---|
| Brut perdu (volume Docker supprimé, disque) | Moyenne | **Critique** | Fichiers JSON compressés + manifeste + 2 copies (disque externe, cloud gratuit), dès cette semaine |
| Joueurs mal identifiés dans les données sauvegardées | Élevée (code actuel) | Haute | Les payloads bruts contiennent les identifiants : le brut est sain, seul `staging` est à reconstruire. **Ne rien jeter du brut.** |
| Périmètre trop étroit (saisons récentes, coupes, D2, profils joueurs, coachs) | Élevée (code actuel) | Haute | Plan G, avec la collecte par lots de 20 |
| Collecte silencieusement vide (erreur de plan, de paramètre ou de quota) | Moyenne | Haute | Lecture de `errors`, contrôles de complétude (G.9) |
| Application « live » impossible sans compositions | Certaine | Moyenne | Mode **rejeu** + mode live pré-composition via sources gratuites (décision 10) |
| Renouvellement automatique non voulu | À vérifier | Faible (19 $) | Vérifier le tableau de bord (décision 5) |
| Blocage pare-feu pour rafales de requêtes (l'API bloque les abus de la limite par minute) | Faible | Haute | ≤ 2 requêtes par seconde ; lecture de `X-RateLimit-Remaining` ([source](https://www.api-football.com/news/post/how-ratelimit-works)) |

---

## D. Décisions urgentes (classement)

Le détail de chaque décision (question, options, recommandation, conséquences) est dans la partie M. Ici, seulement le classement.

**Bloquantes, à trancher cette semaine, avant de dépenser plus de quota :**

| N° | Décision | Ma recommandation, en une ligne |
|---|---|---|
| 1 | Sort du backfill en cours | Constater son état (annexe 1), exporter le brut en fichiers, puis passer au collecteur v2 |
| 2 | Périmètre de collecte pendant l'abonnement | Top 5, de 2015-16 à aujourd'hui + D2 + coupes + joueurs + coachs + transferts + blessures |
| 3 | Format du brut | Fichiers JSON compressés + manifeste = source de vérité |
| 4 | Correctifs du collecteur avant la suite | Oui : branche courte, lots de 20, `errors`, en-têtes, fichiers, reprise |
| 5 | Date de fin et renouvellement de l'abonnement | Vérifier le tableau de bord ; couper le renouvellement automatique si non voulu |
| 6 | Sauvegarde | Disque externe + copie cloud chiffrée, après chaque journée de collecte |

**Bloquantes pour la phase suivante, à trancher avant la fin de l'abonnement :**

| N° | Décision | Recommandation |
|---|---|---|
| 7 | Référentiel maître des identifiants | Identifiants API-FOOTBALL ; `staging` reconstruit depuis le brut |
| 8 | Cible et métrique principale | Modèle par équipe → loi du total ; log-loss du total + RPS |
| 9 | Horizon de prédiction | MVP avant composition ; composition en version intermédiaire |
| 10 | Fonctionnement après l'abonnement | Mode rejeu (principal) + live partiel avant composition |
| 11 | Protocole de validation | Validation glissante 2021-22 → 2024-25 ; **2025-26 mise sous scellés** comme test final |
| 12 | Masse salariale et MVS | Abandon du salaire réel ; MVS en pause ; indicateur « qualité du XI » en version intermédiaire |

**Importantes mais non bloquantes** : 13 (environnement WSL2 et matériel), 14 (une seule base locale), 15 (workflow Git), 16 (variante de stabilité), 17 (sources complémentaires), 18 (rôle des cotes), 19 (restructuration de la documentation), 20 (conventions), 21 (API et interface), 22 (orchestration).

**Reportables** : 23 (MLflow), 24 (DuckDB), 25 (modèles avancés et non supervisé), 26 (compilation LaTeX), 27 (accès réseau distant), 28 (réabonnement ponctuel), 29 (données dérivées de Transfermarkt), 30 (blessures dans le modèle).

---

## E. Proposition de périmètre

### E.1 MVP : « une chaîne complète, honnête et reproductible »

| Axe | Contenu |
|---|---|
| **Fonctionnalités** | Choix d'une **date de référence** (mode rejeu) ou « aujourd'hui » (mode live avant composition) ; liste des matchs de cette date filtrable par championnat ; statut de disponibilité par variable, avec raison ; bouton Prédiction actif seulement si toutes les variables requises sont présentes ; affichage de E[total], P(total = k) pour k de 0 à 7+, intervalle à 80 %, P(> 2,5), λ domicile et λ extérieur ; variables utilisées et leurs valeurs ; version du modèle ; date des données ; en mode rejeu, le score réel pour comparer. |
| **Données** | Top 5 et D2, résultats 2000 → aujourd'hui (football-data, pour l'Elo) ; détails API-FOOTBALL 2015-16 → 2026-27 **sauvegardés** (utilisés en MVP seulement pour le référentiel et le calendrier) ; xG Understat ; cotes football-data (référence de comparaison seulement). |
| **Modèles** | Référence naïve B0 et B1 ; régression linéaire sur le total (pédagogique) ; Poisson sur le total ; **Poisson par équipe** (modèle A actuel, remis à plat) ; test de dispersion (binomiale négative si justifiée) ; Dixon-Coles comme candidat. Groupes de variables G0 → G2 (contexte, Elo, attaque et défense xG), plus G3 (repos) en rejeu seulement, tant qu'aucune source gratuite ne couvre les coupes en live (voir I.3). |
| **Technologies** | Python et uv, Postgres (Docker), SQLAlchemy et Alembic, pytest, pandas, statsmodels, scikit-learn, pyarrow (Parquet), FastAPI, Streamlit, ruff et pre-commit, GitHub Actions, LaTeX. |
| **Critères de réussite** | (1) Tout se reconstruit depuis le brut par des commandes documentées. (2) Le modèle retenu bat B1 en validation glissante, sur le log-loss du total, avec un intervalle de confiance à 95 % qui exclut 0. (3) La calibration de P(> 2,5) est à ±3 points par décile. (4) La couverture de l'intervalle à 80 % est entre 77 et 83 %. (5) Un test de bout en bout passe : base, API et interface démarrent par des commandes documentées, et une prédiction s'affiche. (6) Documentation de cadrage et de réalisation à jour ; chapitres LaTeX mathématiques des modèles utilisés rédigés. |
| **Volontairement exclu** | Variables de composition (stabilité, qualité du XI), entraîneur, blessures, MVS, masse salariale, gradient boosting, non supervisé, accès distant, planification automatique. |

### E.2 Version intermédiaire : « ce que la composition apporte vraiment »

| Axe | Contenu |
|---|---|
| **Fonctionnalités** | Second horizon « avec composition » (en rejeu ; en live seulement si réabonnement) ; comparaison côte à côte avant et après composition ; page « apport des variables » : courbe d'ablation avec intervalles de confiance ; historique des prédictions live et leur score réel. |
| **Données** | Compositions, minutes, notes et postes (staging v2 par identifiant) ; entraîneurs ; dates de naissance ; coupes (jours de repos, rotation). |
| **Modèles** | Groupes G4 → G7 (entraîneur, qualité du XI, stabilité en plusieurs variantes, joueurs habituels absents) ; Poisson régularisé (ridge ou lasso) ; boosting à perte de Poisson (`HistGradientBoostingRegressor`) ; Dixon-Coles dynamique. Expérience dédiée à la stabilité (H.8). |
| **Technologies** | + planification (cron sous WSL2) ; API et interface conteneurisées dans Compose ; suivi d'expériences sous forme de fichiers (ou MLflow, décision 23). |
| **Critères de réussite** | Chaque groupe de variables a un apport mesuré (gain et intervalle) publié dans `docs/` ; décision argumentée sur la stabilité (variante retenue ou abandon) ; prédictions live journalisées **avant** le coup d'envoi pendant au moins 8 journées. |
| **Exclu** | Blessures (sauf si la couverture est suffisante), MVS, non supervisé. |

### E.3 Version avancée : « aller plus loin, si le temps le permet »

| Axe | Contenu |
|---|---|
| **Fonctionnalités** | Accès depuis le téléphone sur le réseau local (proxy inverse) ; tableau de suivi du modèle (dérive, calibration glissante) ; réentraînement planifié. |
| **Données** | Blessures (2021+), autres championnats si besoin. |
| **Modèles** | Poisson bivarié ; modèles hiérarchiques ou à effets aléatoires (entraîneur, équipe) ; styles d'équipes par clustering (k-means ou GMM sur profils statistiques) utilisés comme variable ou interaction ; éventuellement le MVS relancé comme exercice non supervisé. |
| **Technologies** | Facultatives : DuckDB, MLflow, Caddy, LightGBM. |
| **Critères de réussite** | Chaque ajout justifié par un gain mesuré ou par un objectif pédagogique écrit **avant** de le faire. |

---

## F. Architecture recommandée

### F.1 Principes directeurs

1. **Le brut est immuable et se trouve sur disque.** Tout le reste (staging, variables, modèles, prédictions) se **reconstruit** par des commandes. Aucune correction manuelle en base : une correction est un fichier versionné (YAML de rapprochement) rejoué par le pipeline.
2. **Identifiants sources partout** : fixture, team, player, coach et league API-FOOTBALL, avec une table de rapprochement pour football-data et Understat.
3. **Une seule règle temporelle** : toute variable est calculée « à la date de référence *t* », à partir de données dont l'horodatage est **strictement antérieur à *t*** et effectivement disponibles à *t*. Chaque variable déclare son **horizon de disponibilité** (J-1, T-60 min).
4. **Contrats entre briques** : chaque étape lit un format défini (fichier, table, schéma d'API) et en écrit un autre. Pas d'import croisé de la logique d'une étape dans une autre.
5. **Commencer minimal, ajouter une technologie seulement quand un besoin apparaît.**

### F.2 Architecture des données (couches)

| Couche | Contenu | Stockage recommandé | Produit par | Lu par |
|---|---|---|---|---|
| **0. Brut** | Réponses sources telles quelles | `data/raw/<source>/<endpoint>/<saison>/<clé>.json.gz` + **manifeste** (une ligne par requête : paramètres, horodatage, statut HTTP, `errors`, quota restant, sha256, chemin) | Collecteurs | Chargeurs |
| **1. Staging (référentiel)** | Entités typées et réconciliées : competition, season, team, player, coach, fixture, lineup, player_match_stats, team_match_stats, events résumés, injuries, transfers | Postgres, schéma `core` (ou `staging`) | Chargeurs | Constructeurs de variables |
| **2. Variables** | Une ligne par (match, équipe, horizon), colonnes versionnées ; **registre des variables** (nom, définition, source, horizon, risque de fuite) | Postgres `features` + instantané Parquet `data/datasets/<version>.parquet` | Constructeurs | Entraînement, inférence |
| **3. Modèles** | Artefact + **carte d'identité** (version, variables, période d'entraînement, hash du jeu de données, commit Git, métriques) | `models/<version>/` (joblib + `model_card.json`) + table `ops.model_registry` | Entraînement | Inférence, API |
| **4. Prédictions** | Une ligne par (match, version du modèle, horizon, date de création) : λ, loi du total, variables utilisées, variables manquantes, statut | Postgres `ops.prediction` | Inférence | API, évaluation prospective |
| **5. Métadonnées** | Exécutions (collecte, construction, entraînement), fraîcheur par source | Postgres `ops.*` | Toutes les briques | API (« date des données ») |

**Comparaison des formats de stockage demandée :**

| Option | Intérêt | Limites | Coût de mise en œuvre | Valeur pédagogique | Adéquation (matériel et temps) |
|---|---|---|---|---|---|
| **JSON brut (fichiers .json.gz)** | Fidélité totale, immuable, rejouable, indépendant de toute base, facile à sauvegarder | Pas requêtable directement ; nombreux petits fichiers | Faible | Élevée (provenance, idempotence, reprise) | ✅ Excellente : **indispensable** |
| **CSV** | Universel, lisible | Pas de types, lent et volumineux, ambiguïtés (dates, séparateurs) | Faible | Faible | Pour les exports et l'entrée football-data seulement |
| **Parquet** | Colonnes typées, compressé, lecture pandas très rapide, instantanés de jeux de données | Non modifiable ligne à ligne ; pas de transactions | Faible (`pyarrow`) | Moyenne à élevée (format analytique, versionnement de datasets) | ✅ Pour les jeux d'entraînement figés |
| **SQLite** | Un fichier, zéro infrastructure, SQL | Concurrence limitée, types lâches, pas de schémas multiples, moins formateur pour une vraie base | Très faible | Moyenne | Alternative simple si Docker pose problème |
| **PostgreSQL via Docker** | Vrai SGBD : schémas, contraintes, index, fonctions de fenêtre, JSONB ; SQLAlchemy et Alembic ; **déjà en place** | Docker à maintenir ; RAM | Faible (existe) | **Élevée** (modélisation relationnelle, migrations, réseau Docker) | ✅ Recommandé comme cœur |
| **Combinaison (recommandée)** | Chaque format là où il excelle : fichiers pour le brut, Postgres pour le référentiel, les variables, les prédictions et les métadonnées, Parquet pour les instantanés | Plusieurs formats à documenter | Moyen | **Élevée** (architecture en couches réelle) | ✅ |

**Faut-il une architecture en plusieurs couches ?** Oui, mais seulement les couches du tableau ci-dessus (brut, référentiel, variables, puis modèles, prédictions et métadonnées), pas davantage. Une couche « nettoyée » distincte d'une couche « métier » ajouterait une table par entité sans bénéfice à cette échelle. Le nettoyage se fait au chargement dans le référentiel, les règles métier dans les variables.

### F.3 Architecture des traitements (pipelines)

```
            ┌───────────────── Sources externes ─────────────────┐
            │ API-FOOTBALL   football-data.co.uk   Understat      │
            └──────┬───────────────┬───────────────┬──────────────┘
      (HTTP, quota, reprise)       │               │
            ┌──────▼───────────────▼───────────────▼──────┐
  [1] fp collect <source> ──► data/raw/**.json.gz + manifeste       (couche 0)
            └──────────────────────┬──────────────────────┘
  [2] fp load        ──► Postgres core.*  (identifiants, rapprochements YAML)   (couche 1)
  [3] fp check-data  ──► rapport qualité (complétude, cohérence entre sources)
  [4] fp features --as-of/--all ──► features.* + data/datasets/vX.parquet       (couche 2)
  [5] fp evaluate --experiment exp.yaml ──► reports/experiments/<id>.json       (validation glissante)
  [6] fp train --final ──► models/<version>/ + ops.model_registry               (couche 3)
  [7] fp predict --date/--match ──► ops.prediction                              (couche 4)
  [8] API FastAPI (lit core, features, ops ; appelle [7]) ◄──HTTP── [9] UI Streamlit
```

- **CLI unique `fp`**, avec Typer ou simplement `python -m` au départ : un point d'entrée documenté par `--help`. Chaque commande est **idempotente** : la relancer ne crée pas de doublon.
- **Planification** (version intermédiaire) : une tâche quotidienne (`collect` + `load` + `features` + `predict` pour J et J+1) ; une tâche « jour de match » (compositions à T-60) seulement pendant un abonnement.

### F.4 Entraînement

- Les expériences sont décrites dans des fichiers `experiments/*.yaml` : modèle, groupe de variables, plis, hyperparamètres. Le script d'évaluation produit un rapport JSON horodaté (métriques par pli, intervalles bootstrap, calibration).
- Chaque pli est **ajusté uniquement sur son passé** : imputation et standardisation comprises, via un `Pipeline` scikit-learn ou l'équivalent.
- L'entraînement final se fait sur tout l'historique autorisé et produit `model_card.json`. **Ne jamais écraser un modèle** : chaque version a son dossier.

### F.5 Inférence

`predict(match, horizon, as_of)` :

1. charge le modèle actif et sa liste de variables requises ;
2. calcule les variables avec la **même fonction** que l'entraînement, à la date de référence ;
3. produit une **matrice de disponibilité** (variable : présente, manquante ou périmée, avec raison et date de la donnée source) ;
4. si une variable requise manque, renvoie un statut `unavailable` avec les raisons, **sans prédiction** ;
5. sinon, calcule λ domicile et λ extérieur, la loi jointe, la loi du total, E[T], l'intervalle et P(> 2,5) ;
6. écrit dans `ops.prediction` (traçabilité, et évaluation prospective plus tard).

### F.6 API (FastAPI)

Contrat indicatif (JSON, documenté automatiquement en OpenAPI) :

| Méthode et route | Rôle |
|---|---|
| `GET /health` | Vivacité, connexion base, modèle chargé |
| `GET /competitions` | Liste des championnats |
| `GET /matches?date=&competition=&mode=live\|replay` | Matchs de la date, avec statut de disponibilité résumé |
| `GET /matches/{id}/availability?horizon=` | Détail par variable : présente, manquante, raison, date de la donnée |
| `POST /matches/{id}/predictions?horizon=` | Calcule (ou renvoie si elle existe déjà) la prédiction ; 409 si indisponible, avec raisons |
| `GET /models/active` | Carte d'identité du modèle actif |
| `GET /data/freshness` | Dernière collecte réussie par source |

**Valeur pédagogique** : REST, codes HTTP, schémas Pydantic, sérialisation, tests d'API (`TestClient`), et consommation de l'API par l'interface via HTTP (`httpx`), jamais par import Python direct.

### F.7 Interface (Streamlit)

Trois écrans suffisent :

1. **Matchs** : date ou mode, filtre championnat, pastilles de disponibilité, bouton Prédiction.
2. **Détail d'une prédiction** : graphique en barres de P(total = k), E[T], intervalle, λ, tableau des variables utilisées et manquantes, version du modèle, dates.
3. **Modèle** : carte d'identité, métriques de validation, courbe d'ablation.

L'interface **n'accède jamais à la base** : elle ne parle qu'à l'API.

### F.8 Architecture réseau (objectif pédagogique explicite)

| Étape | Ce qu'on apprend |
|---|---|
| MVP | `docker compose` : service `db` ; API et interface lancées sur l'hôte (`localhost:8000`, `localhost:8501`). Ports, `localhost` contre `0.0.0.0`, variables d'environnement, client HTTP avec délais, tentatives et limitation de débit (collecteur). |
| Intermédiaire | `db`, `api` et `ui` dans Compose : **réseau Docker interne**, résolution par nom de service (`http://api:8000`), healthchecks, `depends_on`, seul l'`ui` exposé. |
| Avancée (facultatif) | Proxy inverse (Caddy) et accès depuis le téléphone sur le Wi-Fi local : pare-feu Windows, IP locale, HTTPS local. Tailscale seulement si l'accès hors de chez toi devient un besoin. |

### F.9 Architecture du dépôt

**Minimale recommandée au départ** (évolution de l'existant, pas de grand renommage) :

```
foot-predictor/
├── CLAUDE.md                     ← nouveau : consignes stables pour Claude Code
├── README.md                     ← vitrine courte : quoi, comment lancer, liens docs
├── pyproject.toml / uv.lock / .python-version
├── docker-compose.yml / .env.example / alembic.ini / .pre-commit-config.yaml
├── migrations/versions/          ← 0001-0003 conservées, 0004+ à venir
├── src/foot_predictor/
│   ├── config.py
│   ├── cli.py                    ← point d'entrée « fp »
│   ├── db/                       (models.py, session.py)
│   ├── rawstore/                 ← écriture et lecture du brut + manifeste
│   ├── ingestion/
│   │   ├── api_football/         (client.py, collect.py, load.py)
│   │   ├── football_data/        (collect.py, load.py)
│   │   ├── understat/            (collect.py, load.py)
│   │   ├── reconciliation.py     (ex-common.py, par identifiants)
│   │   └── mappings/             (YAML versionnés = « corrections rejouables »)
│   ├── quality/                  ← contrôles de données
│   ├── features/                 (registry.py, elo.py, rolling.py, rest.py, lineup.py, stability.py…)
│   ├── modeling/                 (dataset, split, models/, evaluation, experiments)
│   ├── inference/                ← predict_service, availability (déplacés depuis modeling/)
│   └── market_value/             ← gelé (hors MVP), conservé avec ses tests
├── api/  (ou src/foot_predictor/api/)   ← à l'étape API
├── ui/                           ← à l'étape interface
├── experiments/                  ← définitions YAML des expériences (versionnées)
├── notebooks/                    ← exploration uniquement, sorties nettoyées (nbstripout)
├── reports/                      ← résultats d'expériences JSON, figures (versionnés si petits)
├── data/                         ← IGNORÉ par Git : raw/, datasets/, exports/
├── models/                       ← IGNORÉ par Git
├── tests/  unit/ integration/ e2e/   (+ fixtures/ : payloads réels anonymisés)
├── scripts/archives/             ← ex-one_off, pour mémoire
└── docs/                         ← voir K
```

**Cible** : la même, avec `api/` et `ui/` conteneurisés (Dockerfiles), une tâche planifiée, et éventuellement `mlflow/`.

### F.10 Technologies : retenues, facultatives, écartées

| Technologie | Pourquoi (besoin concret) | Quand | Indispensable ? | Difficulté | Maintenance | Alternative plus simple | Ressources |
|---|---|---|---|---|---|---|---|
| Python 3.11+ | Langage du projet | Tout | Oui | — | Faible | — | Faibles |
| uv | Environnements et dépendances reproductibles (lockfile) | Tout | Oui (en place) | Faible | Faible | pip + venv | Faibles |
| Git + GitHub | Versionnement, PR, CI | Tout | Oui | Moyenne | Faible | — | — |
| GitHub Actions | Tests automatiques à chaque push et PR | Dès maintenant | Fortement conseillé | Faible | Faible | Lancer pytest à la main | 2 000 min/mois gratuites (dépôt privé) |
| Docker + Compose | Postgres reproductible ; plus tard réseau API/UI | Tout | Oui pour Postgres | Moyenne | Moyenne | SQLite sans Docker | 1-2 Go de RAM |
| WSL2 (Ubuntu) | Bash natif, cron, fin des problèmes BOM, encodage et port natif | Après le sprint de collecte | Conseillé | Faible-moyenne | Faible | Git Bash sous Windows | Quelques Go de disque |
| PostgreSQL 16 | Référentiel, variables, prédictions, métadonnées | Tout | Oui (en place) | Moyenne | Faible | SQLite | ~0,5 Go de RAM |
| SQLAlchemy 2 + Alembic | Modèle objet et migrations versionnées | Tout | Oui (en place) | Moyenne | Faible | SQL brut | — |
| pytest (+ cov, mock) | Tests | Tout | Oui (en place) | Faible | Faible | — | — |
| pandas + numpy + scipy | Transformation, variables | Tout | Oui (en place) | Moyenne | Faible | — | RAM selon volume |
| pyarrow (Parquet) | Instantanés de jeux de données rapides et typés | Étape variables | Conseillé | Faible | Faible | CSV | — |
| statsmodels | GLM avec inférence (erreurs standard, p-valeurs, déviance) | Modélisation | Oui (en place) | Moyenne | Faible | — | — |
| scikit-learn | Pipelines, régularisation, boosting (perte de Poisson), calibration, clustering | Modélisation | Oui (en place) | Moyenne | Faible | — | — |
| requests (+ `urllib3.Retry`) | Client HTTP avec tentatives et délais | Collecte | Oui (en place) | Faible | Faible | — | — |
| pydantic-settings | Configuration typée, secrets (`SecretStr`) | Tout | Oui (en place) | Faible | Faible | `os.environ` | — |
| ruff | Analyse et formatage (un seul outil, rapide) | Dès maintenant | Conseillé | Faible | Faible | Rien | — |
| pre-commit + gitleaks | Contrôles avant commit, **détection de secrets** | Dès maintenant | Conseillé | Faible | Faible | Vigilance manuelle | — |
| Typer | CLI `fp` documentée | Étape environnement | Facultatif | Faible | Faible | `python -m …` | — |
| Jupyter (+ nbstripout) | Exploration statistique | Exploration | Conseillé | Faible | Faible | Scripts + figures | — |
| matplotlib | Figures (rapport, LaTeX) | Exploration et rapport | Oui | Faible | Faible | — | — |
| FastAPI + uvicorn | Exposer les prédictions en HTTP, documentation OpenAPI | Étape API | Oui (objectif pédagogique) | Moyenne | Faible | Appel direct Python | Faibles |
| httpx | Interface ↔ API ; tests d'API | Étapes API et interface | Oui | Faible | Faible | requests | — |
| Streamlit | Interface en Python, rapide | Étape interface | Oui | Faible | Faible | Jinja + HTMX (plus formateur web, plus long) | Faibles |
| LaTeX (Overleaf gratuit, ou Tectonic en local) | Document mathématique et rapport | Continu | Oui (demandé) | Moyenne | Faible | Markdown + MathJax | — |
| cron (WSL2) ou Planificateur de tâches Windows | Tâches planifiées | Version intermédiaire | Facultatif | Faible | Faible | Lancement manuel | — |
| **Facultatifs, plus tard** : MLflow (suivi d'expériences), DuckDB (analyse SQL sur Parquet), LightGBM, pandera (validation de schémas), Caddy (proxy inverse), mypy | Seulement si un besoin apparaît | V2 / V3 | Non | — | — | Fichiers JSON / pandas / sklearn / rien | — |

**Écartées**, avec la raison :

- Neon et toute base hébergée : inutile en local, limite de stockage.
- Airflow, Prefect, Dagster : trop lourds pour quelques tâches.
- Spark, Kafka, Kubernetes : aucune justification à cette échelle.
- dbt : intéressant mais c'est une couche de plus ; à reconsidérer seulement si les transformations deviennent majoritairement SQL.
- Great Expectations : lourd ; pandera ou des contrôles SQL suffisent.
- DVC et Git LFS pour les données : licences des données, quota LFS gratuit de 1 Go ; manifestes et sauvegardes suffisent.
- Le paquet `hdbscan` : `sklearn.cluster.HDBSCAN` existe.
- Deep learning : aucun gain attendu sur 20 000 lignes tabulaires.
- Scraping de Transfermarkt et API payantes.

---

## G. Stratégie de données : plan pour les 20 jours d'abonnement

### G.1 Principes

1. **Sécuriser d'abord ce qui ne se récupère pas gratuitement ensuite** : compositions, statistiques joueurs, entraîneurs, profils, transferts, blessures, et **la saison en cours**. football-data et Understat restent accessibles après l'abonnement : ils attendent.
2. **Le quota n'est plus la contrainte.** Avec `fixtures?ids=` par lots de 20 ([source](https://www.api-football.com/news/post/how-to-get-all-fixtures-data-from-one-league)), le périmètre complet recommandé coûte **environ 12 000 à 15 000 requêtes**, soit 2 jours de quota sur les 150 000 disponibles. Les contraintes réelles sont :
   - la **justesse** du collecteur ;
   - la **complétude vérifiée** ;
   - la **sauvegarde**.
3. **Brut intégral, jamais transformé, jamais écrasé.** On ne jette aucun champ, et une nouvelle version d'une réponse s'ajoute à côté de l'ancienne.
4. **Tout est rejouable** : chaque requête est journalisée, et la collecte reprend là où elle s'est arrêtée.

### G.2 Premier jour : état des lieux, sans rien casser

1. Lancer les requêtes de l'**annexe 1**, en lecture seule : nombre de matchs déjà en `raw.api_football_fixture_detail`, taille de la table, format réel de `games.position`, présence de `statistics` et `expected_goals`, identifiants joueurs.
2. **Exporter immédiatement** le brut existant de Postgres vers des fichiers (`COPY … TO` ou un petit script d'export), puis faire une copie sur un disque externe.
3. Vérifier dans le tableau de bord API-FOOTBALL la **date exacte de fin** et le **renouvellement automatique**.
4. Si le script actuel tourne encore : le laisser finir la saison en cours de traitement, puis l'arrêter. On passe ensuite au collecteur v2 (décisions 1 et 4).

### G.3 Inventaire des endpoints utiles

Les coûts sont des estimations pour 12 saisons (2015-16 à 2026-27). Les paginations et couvertures sont **à vérifier** au premier appel.

| Priorité | Endpoint | Ce qu'il apporte au projet | Coût estimé |
|---|---|---|---|
| P0 | `/status` | Compte, quota consommé, date de fin (à vérifier si l'appel consomme du quota) | ~1 |
| P0 | `/leagues?id=` | **Couverture par saison** (`coverage` : lineups, events, statistics_fixtures, statistics_players, injuries, odds, predictions). Inventaire indispensable avant de collecter. | ~20 |
| P0 | `/fixtures?league=&season=` | Liste des matchs, statuts, dates UTC, scores, arbitre, stade | 1 par championnat-saison ≈ 250 |
| P0 | `/fixtures?ids=a-b-…` (≤ 20) | **Détail complet** : compositions (onze, remplaçants, **entraîneur**, formation, `grid`), événements (buts, cartons, remplacements minutés), statistiques d'équipe, statistiques joueurs (minutes, note, poste…) | Nombre de matchs / 20 ≈ 2 500 |
| P1 | `/players?league=&season=&page=` | **Date de naissance**, taille, nationalité + statistiques de saison agrégées | ~35 pages par championnat-saison ≈ 4 000 |
| P1 | `/coachs?team=` | Carrière des entraîneurs (équipe, début, fin) : ancienneté, changement récent | ~300 |
| P1 | `/transfers?team=` | Transferts (date, type, provenance) : arrivées et départs, « joueurs inconnus » | ~300 |
| P1 | `/injuries?league=&season=` | Absences signalées par match (couverture ancienne à vérifier) | ~120 |
| P1 | `/teams?league=&season=` | Équipes, stade (capacité, ville) | ~130 |
| P2 | `/fixtures?date=` + `/fixtures?ids=` à T-60 | **Journal quotidien** des matchs à venir avec compositions officielles : un échantillon « live » réel pour tester l'horizon avec composition | ~50-150 par jour |
| P2 | `/odds?fixture=` ou `?date=` | Cotes avant match (historique court côté API ; football-data couvre l'historique) | ~100 par jour, facultatif |
| P2 | `/predictions?fixture=` | Prédiction propre à l'API : référence tierce pour les matchs à venir | ~50 par semaine |
| P3 | `/sidelined?player=` | Historique des indisponibilités par joueur | Coûteux ; seulement s'il reste du temps |
| P3 | `/standings` | Contrôle croisé du classement que l'on calcule | ~130 |
| P3 | `/players/teams`, `/players/squads` | Carrière d'un joueur ; effectif actuel | À la demande |
| — | `/fixtures/headtohead`, `/teams/statistics`, `/trophies`, `/venues` | Dérivables ou inutiles pour la cible | 0 |

**Périmètre de compétitions recommandé** (décision 2) :

| Bloc | Pourquoi | Détails ≈ |
|---|---|---|
| Top 5, 2015-16 → 2026-27 (dont **2025-26 et la saison en cours**) | Cœur du modèle ; saisons récentes indispensables pour la validation et l'application | ~20 500 matchs |
| Deuxièmes divisions (Championship, Segunda, 2. Bundesliga, Serie B, Ligue 2) | Historique des **promus** (Elo, forme, compositions : un promu n'est plus « inconnu ») | ~22 000 matchs |
| Coupes d'Europe (C1, C3, C4 ; phases principales) + coupes nationales (matchs impliquant une équipe suivie) | **Jours de repos**, rotation, fatigue ; compositions pour la stabilité | ~8 000 à 10 000 matchs |
| Facultatif : Eredivisie, Primeira Liga, Belgique | Passé des joueurs recrutés depuis ces championnats | Seulement s'il reste du temps |

### G.4 Plan jour par jour

Les jours sont numérotés depuis le début du plan ; la date exacte de fin est à confirmer (décision 5).

| Jours | Actions | Ton temps | Quota |
|---|---|---|---|
| **J1** (24-25 sept.) | État des lieux (G.2) ; export et sauvegarde du brut existant ; décisions 1 à 6 | 2-3 h | 0 |
| **J2-J3** | Collecteur v2 via Claude Code sur une branche courte : client HTTP (lecture de `errors`, en-têtes, 429 et tentatives, ≤ 2 requêtes par seconde), stockage brut sur disque avec manifeste, file de travail reprenable, lots de 20 ; tests sur 3 à 5 payloads réels anonymisés ; relecture et fusion | 4-5 h | ~50 (tests) |
| **J3** | Inventaire : `/status` et `/leagues` → **tableau de couverture** versionné dans `docs/cadrage/04_donnees_sources.md` | 1 h | ~20 |
| **J4** | Listes de matchs de tout le périmètre | 0,5 h (lancement) | ~250 |
| **J4-J6** | Détails par lots : top 5 manquants (dont 2025-26 et 2026-27), puis D2, puis coupes. **Tourne la nuit.** | 1 h de suivi | ~2 500 |
| **J7** | Contrôles de qualité (G.9) sur les détails ; rattrapage des échecs ; **sauvegarde n° 1** | 2 h | ~100 |
| **J8-J10** | Joueurs (profils et saisons), entraîneurs, transferts, équipes, blessures | 1 h | ~5 000 |
| **J8 → fin** | **Journal quotidien** : matchs de J et J+1, compositions à T-60 pour les 5 championnats, cotes et prédictions de l'API (facultatif). Planifié ou lancé à la main. | 10 min par jour | ~150 par jour |
| **J11-J14** | Contrôles de qualité complets ; rapport qualité versionné ; en parallèle, sans quota : début de la documentation de cadrage (K) | 4-6 h | ~0 |
| **J15-J18** | Rattrapages ; recollecte des matchs reportés ou modifiés ; P3 s'il reste du temps (sidelined, standings, autres championnats) | 2 h | selon besoin |
| **J19-J20** | **Gel des données** : manifeste final (nombres, sha256), fichier `DATA_FREEZE.md`, tag Git `data-freeze-2026-10` ; **2 sauvegardes vérifiées par une restauration test** ; décision de renouvellement | 2 h | 0 |

Total : environ 25 à 30 h, compatible avec 3 semaines à 10 h. Quota consommé : environ 12 000 à 15 000 requêtes, soit moins de 10 % du disponible, ce qui laisse une large réserve pour les erreurs.

### G.5 Données historiques à sauvegarder absolument

Par ordre de priorité :

1. Détails des matchs du top 5, **2025-26 et 2026-27 compris**.
2. Détails D2 et coupes.
3. Profils joueurs (naissance).
4. Entraîneurs.
5. Transferts.
6. Blessures.
7. Journal quotidien (compositions à T-60 et cotes) : c'est le seul moyen d'avoir des données « telles qu'elles étaient connues avant le match ».

**Tout le reste se reconstruit ou se retélécharge gratuitement.**

### G.6 Éviter les doublons et reprendre après une erreur

- **Clé canonique de requête** = endpoint + paramètres triés, qui donne un hash et un nom de fichier. Avant chaque appel, le collecteur consulte le manifeste : si la requête est `done`, on saute.
- **Pour les détails de matchs** : l'ensemble des `fixture_id` déjà obtenus (lu dans le manifeste ou un index) détermine les lots restants. Il n'y a plus de parcours du JSONB.
- **Écriture atomique** : écrire dans `*.tmp`, puis renommer, puis ajouter la ligne au manifeste. Un plantage ne laisse jamais de fichier à moitié écrit.
- **File de travail** (`ops.fetch_queue` en Postgres, ou un fichier SQLite) : statuts `pending`, `done`, `failed`, `retry`, nombre de tentatives, dernière erreur. Relancer la commande ne rejoue que ce qui n'est pas `done`.
- **Politique d'erreur** :

| Cas | Comportement |
|---|---|
| HTTP 429 | Pause de 60 s, puis nouvelle tentative |
| HTTP 5xx ou délai dépassé | 3 tentatives avec attente croissante |
| `errors` non vide (plan, paramètre invalide) | `failed`, **sans nouvelle tentative**, raison journalisée |
| `results = 0` alors qu'on attend des données | `suspect` : à revoir à la main |

- **Garde-fou de quota** : lire `x-ratelimit-requests-remaining` à chaque réponse et s'arrêter proprement sous une réserve (par exemple 500, gardée pour le journal quotidien).
- **Ne jamais écraser** : une recollecte (score corrigé, match reporté) crée un nouveau fichier horodaté ; le chargeur prend la plus récente.

### G.7 Format et organisation des fichiers

```
data/raw/
  api_football/
    leagues/league=39.json.gz
    fixtures_list/league=39/season=2023.json.gz
    fixtures_detail/season=2023/<hash_requete>.json.gz      ← une réponse de lot (≤ 20 matchs)
    players/league=39/season=2023/page=01.json.gz
    coachs/team=33.json.gz
    transfers/team=33.json.gz
    injuries/league=39/season=2023.json.gz
    daily/2026-10-03/lineups_T-60/<hash>.json.gz            ← journal quotidien
  football_data/mmz4281/2324/E0.csv                          ← fichier CSV tel que téléchargé
  understat/…
data/raw/_manifest/api_football.jsonl                        ← une ligne par requête (reconstructible)
```

**Chaque fichier est autoportant** : il contient une enveloppe `{request: {endpoint, params}, fetched_at, http_status, headers_quota, body: <réponse API intacte>}`. Si le manifeste était perdu, on pourrait le reconstruire en relisant les fichiers.

### G.8 Suivi des requêtes

Le manifeste (et sa copie `ops.fetch_log` en base) contient une ligne par requête :

`horodatage | source | endpoint | params | http_status | errors | results | quota_restant_jour | durée_ms | fichier | sha256`

Il sert à trois choses :

- une commande `fp collect status` affiche le quota du jour, les files, les échecs et la progression par bloc ;
- la date de dernière collecte réussie par source devient l'information « date de récupération des données » affichée dans l'application ;
- c'est la trace de provenance demandée.

### G.9 Contrôles de qualité, versionnés dans `reports/data_quality/`

| Famille | Contrôle | Seuil attendu |
|---|---|---|
| Complétude | Matchs listés par championnat-saison = attendu (380, 306…) ; tout match terminé a un détail | 100 % |
| Complétude | Détail : 2 compositions × 11 titulaires, 1 gardien titulaire par équipe ; `players` et `events` non vides (selon `coverage`) | ≥ 99 % sur les saisons couvertes |
| Cohérence entre sources | Score API = score football-data ; date à ±1 jour ; buts dans `events` = score | 100 % (sinon liste nominative) |
| Identifiants | Tout `player.id` des compositions existe dans les profils ; un identifiant correspond à un seul joueur (variantes de nom tolérées) ; **doublons de personnes** (même nom et même date de naissance, identifiants différents) listés | Liste à revoir |
| Plausibilité | Minutes entre 0 et 130 ; note entre 3 et 10 ; somme des minutes d'une équipe ≈ 990 à 1 100 | Anomalies listées |
| Couverture | `coverage` déclaré contre observé, par saison | Tableau |
| Stabilité des identifiants | Une même équipe garde le même `team.id` d'une saison à l'autre (renommages, promotions) ; un joueur transféré garde son `player.id` | À vérifier sur 10 cas connus |

### G.10 Ce qui peut attendre (gratuit et durable)

- CSV football-data (toutes colonnes, 2000 → aujourd'hui, dont D2 et cotes) : téléchargeables à tout moment, en respectant l'usage prévu par le site, « league match prediction », pour des particuliers ([conditions](https://www.football-data.co.uk/data.php)).
- Understat, sous réserve de la décision 17.
- Recalcul de toutes les variables, de l'Elo, des modèles.

### G.11 Anticiper la fin de l'abonnement

- Rédiger `DATA_FREEZE.md` : périmètre, nombres, trous connus, date de gel, sha256 du manifeste.
- Faire deux sauvegardes (disque externe + cloud gratuit, archive chiffrée avec 7-Zip AES) et **tester une restauration**.
- Documenter ce qui **ne sera plus rafraîchi** : compositions et statistiques joueurs de la saison en cours après la date de gel, blessures, changements d'entraîneur postérieurs au gel. Dans l'application, ces éléments sont traités comme des « données manquantes », avec leur raison. Une saisie manuelle documentée reste possible pour les entraîneurs.
- **Option à garder en tête** (décision 28) : un mois d'abonnement ponctuel une fois par an, en juin (19 $), suffirait à compléter la saison écoulée.

### G.12 Masse salariale et valeur des effectifs : ordre de préférence et repli

| Rang | Solution | Verdict | Raison |
|---|---|---|---|
| 1 | **Indicateur substitutif « qualité du onze »** construit sur les données collectées. Pour chaque joueur à la date *t* : moyenne de sa note API (ou de ses contributions par 90 minutes) sur ses N derniers matchs, pondérée par les minutes et **rétrécie vers la moyenne de son poste** quand il a peu joué (moyenne bayésienne empirique, un bon exercice d'inférence). Qualité du XI = moyenne des 11 ; plus la **part des titulaires habituels absents**. | ✅ **Recommandé** (version intermédiaire) | Disponible pour tous les matchs collectés, calculable à la date *t* sans fuite, hypothèses peu nombreuses et testables, aucune fragilité juridique. C'est la traduction la plus fidèle de l'idée « masse salariale du onze ». |
| 2 | **Force d'équipe sans les joueurs : Elo** calculé soi-même | ✅ **Dès le MVP** | La masse salariale est surtout un indicateur de force à long terme ; l'Elo et l'xG mesurent directement cette force. Toujours disponible, gratuit, simple. |
| 3 | Expérience et âge : minutes cumulées des titulaires, âge moyen (dates de naissance collectées) | ✅ Complément | Objectif, peu coûteux |
| 4 | Estimation d'un salaire par club, championnat, âge et poste | ❌ | Hypothèses arbitraires, invérifiables |
| 5 | Valeur marchande (Transfermarkt ou jeux de données qui en dérivent) | ❌ | Fragile juridiquement : CGU, droit des bases de données. Cohérent avec la décision déjà prise dans le dépôt. |
| 6 | Masse salariale réelle (estimations publiques du type Capology) | ❌ | Payante ou scrapée, incomplète, non datée match par match |
| — | MVS actuel (`market_value/`) | ⏸ En pause | Pondérations arbitraires, « réputation » redondante avec le classement, calcul lourd, pas de vérité terrain pour le valider |

**Stratégie de repli** : si la variable « qualité du XI » n'apporte **aucun gain mesurable au-delà de l'Elo et de l'xG** (intervalle de confiance du gain qui contient 0), on la **supprime** et on documente ce résultat négatif. C'est un résultat en soi.

### G.13 Stabilité des identifiants

- API-FOOTBALL fournit des identifiants numériques stables pour les championnats, les équipes, les joueurs, les entraîneurs et les matchs. La saison est une année (2023 = saison 2023-24).
- **Recommandation (décision 7)** : faire d'API-FOOTBALL le **référentiel maître**. football-data et Understat deviennent des sources d'enrichissement, rattachées par un rapprochement versionné (YAML d'équipes et appariement des matchs par équipes et date).
- Points à vérifier pendant la collecte :
  - doublons de joueurs côté API (même personne, deux identifiants) ;
  - équipes réserves ou homonymes ;
  - changements de nom de club.

---

## H. Analyse de l'indicateur de stabilité

### H.1 L'« implémentation » existante

**Il n'existe aucun code** : `grep` ne trouve que la colonne `features.team_match_features.squad_stability_score_season` (`db/models.py`, migration 0002) et la mention « bloquée » dans `modeling/features_config.py`. La spécification se trouve dans `docs/RECAP_PROJET.md` §8 et `docs/recaps/recap_decisions_projet.md` §5, reprise d'un mémoire de stage :

> Pour chaque équipe et chaque saison (remise à zéro à chaque saison) : matrice symétrique joueur × joueur, avec 1 si les deux joueurs ont été titulaires ensemble, diagonale à 0 ; cumul match après match ; pour un match, restriction de la matrice cumulée aux 11 titulaires, somme, normalisation par `110 × nombre de matchs joués` → score entre 0 et 1.

Dans le mémoire, l'indicateur donnait un rapport de cotes de 5,32 dans une régression logistique sur la victoire, avec contrôle de la masse salariale et de l'âge.

### H.2 Ta proposition comparée à la spécification

Ta description (étapes 1 à 7) et la spécification décrivent **le même objet**. La spécification précise trois points que ta description laisse ouverts :

1. **La normalisation** : 110 = 11 × 10 paires ordonnées, et le nombre de matchs.
2. **La restriction aux 11 titulaires du match évalué.**
3. **La remise à zéro par saison.**

Un point reste ambigu dans les deux, et il est **critique** : la matrice utilisée pour le match *m* doit être cumulée **jusqu'au match m−1 inclus**, jamais jusqu'à *m*. Sinon, le match évalué ajoute mécaniquement 110 au numérateur. Au premier match de la saison, le score vaudrait alors 1 pour toutes les équipes. Ce n'est pas une fuite au sens strict (la composition est connue avant le coup d'envoi), mais c'est un biais mécanique.

**Autre point de vocabulaire** : la dimension « nombre de joueurs × nombre de joueurs » change au fil des arrivées. En pratique, on ne construit jamais cette matrice en entier (voir H.3).

### H.3 Résultat clé : la matrice se ramène à un comptage de titulaires communs

Notons :

- **x_k** ∈ {0,1}^P le vecteur indicateur des titulaires du match *k* ;
- **C** = Σ_{k<m} (x_k x_kᵀ − diag(x_k)) la matrice cumulée ;
- **s_k** = |XI_m ∩ XI_k| le nombre de titulaires du match *m* qui étaient aussi titulaires au match *k*.

Alors la somme de la matrice cumulée restreinte au onze du match *m* vaut :

```
x_mᵀ C x_m  =  Σ_{k<m} [ (x_mᵀ x_k)² − x_mᵀ x_k ]  =  Σ_{k<m} s_k (s_k − 1)
```

Donc :

```
Stabilité_reset(m)  =  (1/n) · Σ_{k ∈ saison, k<m}  s_k(s_k − 1) / 110
```

**Autrement dit, l'indicateur est exactement la moyenne, sur les matchs précédents de la saison, d'une fonction convexe du nombre de titulaires communs avec chacun d'eux.** Quelques valeurs de s(s−1)/110 :

| Titulaires communs s | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|
| s(s−1)/110 | 0,27 | 0,38 | 0,51 | 0,65 | 0,82 | 1,00 |

Conséquences pratiques :

1. **Il n'est pas nécessaire de construire la matrice** : un calcul en O(nombre de matchs passés × 11) suffit, rapide et testable.
2. **Toutes les stratégies demandées s'écrivent comme une pondération** w_k des matchs passés :
   ```
   S_w(m) = Σ_k w_k · s_k(s_k − 1) / (110 · Σ_k w_k)
   ```
   Remise à zéro : w_k = 1 si même saison. Historique intégral : w_k = 1. Fenêtre : w_k = 1 si k fait partie des N derniers. Décroissance : w_k = λ^rang ou exp(−ξ·Δjours). Report partiel : w_k = α pour la saison précédente. Valeur initiale fondée sur la saison précédente : pseudo-observations, c'est-à-dire un rétrécissement bayésien.
3. **La version « paires » apporte probablement peu par rapport au simple nombre de titulaires communs.** Sur la plage réaliste s ∈ [6, 11], s(s−1) et s sont presque parfaitement corrélés (≈ 0,99). L'intérêt propre de la matrice réside ailleurs : dans la **distribution** des paires (minimum, paires inédites, cohésion par ligne), voir H.6.
4. **Exercice pédagogique** : implémenter les deux versions (matrice et recouvrement) et **prouver leur égalité par un test** pytest sur des compositions aléatoires. Cela relie l'algèbre linéaire (forme quadratique xᵀCx) au code.

**Réponse franche à ta question « existe-t-il plus simple, plus robuste ou plus interprétable ? » : oui.**

- Le nombre de titulaires communs avec le match précédent, une moyenne pondérée des recouvrements, ou l'ancienneté collective (nombre moyen de titularisations des 11 dans le club) sont plus simples.
- Ils sont au moins aussi robustes.
- Ils sont nettement plus interprétables (« 9 titulaires sur 11 étaient déjà là la semaine dernière »).

La matrice reste utile pour les variables de distribution et comme support pédagogique.

### H.4 Le début de saison et la remise à zéro : vérification de ton intuition

| Ton intuition | Verdict | Explication |
|---|---|---|
| « Très peu informatif en début de saison » | ✅ **Confirmé, et pire** | Au 1er match, n = 0 : le score vaut 0/0, il est **indéfini** et doit être imputé. Aux matchs 2 à 5, il repose sur 1 à 4 comparaisons : une seule rotation forcée (semaine de coupe, blessure) le fait varier fortement. |
| « Prédictions instables ou proches de l'aléatoire au début » | ⚠️ **Nuancé** | La prédiction ne dépend pas que de cette variable. Si son coefficient est modeste, son bruit pèse peu. L'instabilité du début de saison vient surtout des **autres** variables remises à zéro : le classement (indéfini au 1er match, d'où les 1 226 lignes écartées dans `dataset.py`) et la forme. **Le problème du début de saison est général**, et il se traite globalement (Elo et fenêtres qui traversent les saisons). |
| « L'indicateur devient progressivement plus pertinent » | ⚠️ **À moitié** | Sa variance diminue, oui. Mais avec un poids égal pour tous les matchs de la saison, il devient **inerte** : en fin de saison, trois recrues d'hiver ou un changement d'entraîneur ne bougent presque pas la moyenne. Il gagne en stabilité ce qu'il perd en réactivité. |
| *(Non mentionné)* **La remise à zéro détruit l'information qu'on veut mesurer** | ❗ | Au 2e match, une équipe qui a gardé son onze de la saison passée et une équipe avec 6 recrues ont le même score si elles alignent deux fois le même onze. L'indicateur mesure alors la **rotation intra-saison**, pas « l'habitude de jouer ensemble ». |
| *(Non mentionné)* **Biais d'atténuation** | ❗ | Le bruit de mesure du début de saison, une erreur sur la variable explicative, **tire le coefficient estimé vers 0 sur toute la saison**. On sous-estime l'effet partout, pas seulement au début. |

**Conclusion** : ton intuition est juste pour le début de saison, mais incomplète. Le remède n'est pas « ne jamais remettre à zéro » (l'historique intégral devient lui aussi inerte avec les années). C'est une **décroissance des anciens matchs, sans remise à zéro**, limitée aux matchs **dans le club** : un joueur parti ne compte plus, puisque seules les lignes du onze actuel sont lues ; une recrue arrive avec 0.

### H.5 Comparaison des stratégies

Légende : ++ très bon, + bon, ~ moyen, − faible, −− mauvais.

| Stratégie | Pertinence statistique | Risque de fuite* | Difficulté | Historique nécessaire | Début de saison | Transferts | Joueurs inconnus | Interprétabilité | Coût de calcul |
|---|---|---|---|---|---|---|---|---|---|
| 1. Remise à zéro par saison (spécification) | − (bruit au début, inerte à la fin, atténuation) | Nul | + | 1 saison | −− (indéfini, puis bruité) | + (recrue = 0) | + (0) | + | ++ |
| 2. Historique intégral (dans le club) | ~ (inerte, poids égal pour des matchs de 5 ans) | Nul | + | Toutes les saisons | + | + | + | + | ++ |
| 3. Historique partiel (saison en cours + précédente) | + | Nul | + | 2 saisons | + | + | + | + | ++ |
| 4. Décroissance temporelle (en jours) | ++ (réactif, pas de rupture) | Nul | + | 1-2 saisons | ++ | + | + | ~ (paramètre ξ) | ++ |
| 5. Pondération des matchs récents (par rang) | ++ | Nul | + | 1-2 saisons | ++ | + | + | ~ (demi-vie h) | ++ |
| 6. Report pour les joueurs toujours au club | ≡ automatique dès que l'historique est **limité au club** | Nul | — | — | ++ | ++ | + | + | — |
| 7. Gestion spécifique des transferts (paires formées dans un autre club) | ~ (cas rare : deux joueurs venant du même club) | ⚠️ si on utilise des listes de transferts futures | − | Toutes les compositions, tous clubs | + | ++ | ~ | − | ~ |
| 8. Valeur initiale fondée sur la saison précédente (pseudo-observations) | + (rétrécissement bayésien) | Nul | ~ | 2 saisons | + | ~ | + | ~ | ++ |
| 9. Fenêtre glissante des N derniers matchs | + | Nul | + | N matchs | + | + | + | ++ | ++ |
| 10. Titulaires communs avec le match précédent (0-11) | + (bruité seul) | Nul | ++ | 1 match | + (dès le 2e match de la saison, en traversant l'intersaison) | + | + | ++ | ++ |
| 10b. Ancienneté collective (titularisations moyennes des 11 dans le club, sur 365 jours) | + | Nul | ++ | 1 an | ++ | ++ | + | ++ | ++ |

\* À condition de n'utiliser que les matchs strictement antérieurs et les compositions connues à T-60.

**Remarque importante pour les promus** : si les compositions de D2 ne sont pas collectées, un promu a une histoire vide, donc toutes ses paires valent 0 et il paraît « instable ». C'est faux. C'est un argument de plus pour collecter les D2 pendant l'abonnement.

### H.6 Transformer la matrice en variables

À partir des 55 paires du onze (pondérées selon la stratégie retenue) :

| Variable | Définition | Intérêt | Recommandation |
|---|---|---|---|
| Cohésion moyenne | Moyenne des 55 paires (= S_w) | Mesure globale | ✅ |
| Maillon faible | Minimum ou 10e percentile des paires | Une seule paire inédite peut coûter (défense centrale) | Test |
| Paires inédites | Part des paires à 0 | Lisible | Test |
| Dispersion | Écart-type des paires | Noyau stable + éléments nouveaux | Plus tard |
| Cohésion par ligne | Même calcul restreint à gardien et défenseurs, aux milieux, aux attaquants (via `pos` ou `grid`) | La cohésion défensive devrait compter plus pour les buts encaissés | ✅ en seconde vague |
| Sous-groupes | Plus grande clique de joueurs ayant au moins k titularisations communes (graphe) | Pédagogique (théorie des graphes) | Avancé |
| Ancienneté collective | Titularisations ou minutes moyennes des 11 pour le club | Simple, robuste | ✅ |
| Pondération par temps de jeu | Co-présence réelle = min(minutes_i, minutes_j) pour deux titulaires : c'est exact, puisque les deux commencent à la minute 0 | Tient compte des sorties précoces | Seconde vague |
| Nouveaux titulaires | Nombre de titulaires avec moins de 3 titularisations dans le club sur 365 jours | Transferts, jeunes | ✅ |
| Agrégation match | Somme et différence des deux équipes | Pour le **total** de buts, les deux cohésions comptent | ✅ |

**Garde-fou** : dans la première expérience, au plus 3 variables de stabilité par équipe (colinéarité, surapprentissage).

### H.7 Recommandation

- **MVP : aucune variable de stabilité.** Toutes dépendent des compositions. Or après l'abonnement, les compositions récentes ne seront plus disponibles en live, et le MVP doit rester fonctionnel. On mesure d'abord le socle sans elles.
- **Version intermédiaire, horizon « avec composition »**, 3 variables par équipe :
  1. `xi_overlap_prev` : titulaires communs avec le match précédent de l'équipe ;
  2. `xi_cohesion_ewm` : cohésion par paires avec **décroissance exponentielle par rang de match** (demi-vie h choisie en validation interne parmi {3, 5, 10, 20, ∞}), **sans remise à zéro**, historique limité au club, compositions D2 incluses ;
  3. `xi_new_starters` : nombre de titulaires récents.
- **Variante sans composition** (pour l'horizon avant composition, si des compositions récentes sont disponibles) : taux de rotation des 5 derniers matchs, c'est-à-dire 11 moins la moyenne des recouvrements entre onze consécutifs.
- **Périmètre des matchs** : championnat seulement dans un premier temps, pour que les données soient identiques à l'entraînement et en live. Test d'une variante « toutes compétitions » ensuite.

### H.8 Protocole pour trancher (expérience dédiée)

1. **Modèle de référence** : Poisson par équipe avec les groupes G0 à G3 (contexte, Elo, xG, repos).
2. **Variantes comparées** : aucune stabilité (contrôle) ; remise à zéro (spécification d'origine) ; historique intégral ; fenêtre N = 10 ; décroissance h ∈ {3, 5, 10, 20} ; titulaires communs seuls ; ancienneté collective seule.
3. **Mesure** : gain de log-loss du total et de RPS en validation glissante, avec intervalle bootstrap par journée, **globalement et par tranche de journées** (1-5, 6-15, 16 et plus). C'est ce qui vérifie ton intuition sur tes données.
4. **Diagnostics** : corrélation de chaque variante avec les résidus du modèle de référence par tranche ; corrélation entre variantes (on s'attend à plus de 0,9 entre paires et recouvrement).
5. **Règle de décision, écrite avant de lancer** : on retient la variante **la plus simple** dont le gain n'est pas significativement inférieur à la meilleure. Si aucune n'a un gain dont l'intervalle exclut 0, la stabilité est **abandonnée** et le résultat documenté.

### H.9 Améliorations ultérieures

Cohésion par ligne, co-présence en minutes, interaction avec le changement d'entraîneur (nouveau système, nouvelles paires), et, pour l'horizon avant composition, un « onze probable » (les 11 joueurs les plus titularisés récemment, sans les absents connus).

---

## I. Stratégie de modélisation

### I.1 Cadre du problème (décisions 8, 9 et 11)

| Élément | Recommandation |
|---|---|
| **Cible d'apprentissage** | Buts marqués par **chaque équipe** (Y_H, Y_A), modélisés par une loi de comptage de paramètre λ_H ou λ_A. C'est ce que fait déjà le modèle A. |
| **Sortie produit** | La **loi du total** T = Y_H + Y_A : E[T] = λ_H + λ_A, P(T = k), intervalle de prédiction à 80 %, P(T ≥ 3). En secondaire : λ par équipe, loi jointe, et donc 1N2 et score exact « gratuits ». |
| **Unité d'observation** | Apprentissage : ligne (match, équipe), 2 par match. Évaluation : **match**. |
| **Horizon** | H1 « avant composition » (J-1 jusqu'au coup d'envoi) pour le MVP ; H2 « avec composition » (T-60 min) en version intermédiaire. Chaque variable déclare son horizon. |
| **Variables disponibles** | Seulement ce qui est connu à l'horizon. Catalogue en I.3. |

### I.2 Pourquoi modéliser par équipe plutôt que le total directement ?

| Option de cible | Avantages | Inconvénients | Verdict |
|---|---|---|---|
| Total T seul | Simple, c'est directement le produit | Mauvaise spécification : l'attaque de l'un rencontre la défense de l'autre de façon **multiplicative** par équipe ; log(λ_H + λ_A) n'est pas linéaire dans les variables. Perte d'information (qui marque). | Utile comme **étape pédagogique** (M1, M2) et comme référence |
| Buts domicile seuls, ou extérieur seuls | — | Partiel | ❌ |
| Deux prédictions séparées (H et A) | Structure attaque × défense naturelle ; données doublées ; total, 1N2 et score dérivables | Suppose une indépendance conditionnelle (à tester : Dixon-Coles, Poisson bivarié) | ✅ **Cœur du modèle** |
| Distribution plutôt que valeur ponctuelle | Quantifie l'incertitude, qui est énorme (voir C.2) ; permet la calibration et les intervalles | Métriques plus riches à apprendre | ✅ **Toujours** : la valeur ponctuelle n'est qu'un résumé de la loi |

Si Y_H et Y_A suivent des lois de Poisson indépendantes, T suit une loi de Poisson de paramètre λ_H + λ_A. Avec une corrélation (Dixon-Coles ou Poisson bivarié), la loi de T change surtout sur les petites valeurs (0, 1, 2), ce qui est testable.

### I.3 Catalogue des variables par groupes (progression 2 → 4 → 8 → 10… variables)

| Groupe | Variables (× 2 équipes sauf mention) | Source | Disponible à | Historique | Après l'abonnement | Risque de fuite | Coût |
|---|---|---|---|---|---|---|---|
| **G0 Contexte** (2) | Domicile ; championnat (effets fixes) ; + indicateur huis clos (2020-21) | Calendrier | Connu à l'avance | Tout | ✅ | Nul | Nul |
| **G1 Force globale** (+2 = 4) | Elo avant match (propre, adverse) | Elo maison sur football-data 2000+ (+ D2) | J-1 | 2000+ | ✅ | Faible : prendre l'Elo **avant** le match | Faible |
| **G2 Attaque et défense** (+4 = 8) | xG pour et contre, lissés exponentiellement, **sans remise à zéro par saison**, avec ancienneté maximale ; buts pour et contre | Understat, football-data | J-1 | 2014+ | ⚠️ Understat (décision 17) | Faible | Moyen |
| **G3 Calendrier** (+2 = 10) | Jours de repos ; matchs joués sur 14 jours ; match européen en milieu de semaine | Listes de matchs toutes compétitions | Connu à l'avance | Sauvegardé | ⚠️ Coupes non couvertes par les sources gratuites stables : **rejeu seulement**, sauf nouvelle source | Nul | Faible |
| **G4 Entraîneur** (+2 à 4) | Ancienneté en jours ; « nouveau coach » (moins de 5 matchs) ; éventuellement effet coach régularisé (avancé) | Compositions (coach) + `/coachs` | J-1 | Sauvegardé | ❌ live (saisie manuelle possible) | Faible | Faible |
| **G5 Qualité du XI** (+2 à 4) | Qualité moyenne rétrécie des titulaires ; part des habituels absents ; âge moyen | Statistiques joueurs + profils | **T-60** | Sauvegardé | ❌ live | Moyen : exclure le match courant des notes | Moyen |
| **G6 Stabilité** (+2 à 6) | Voir H.7 | Compositions | **T-60** | Sauvegardé | ❌ live | Faible (m−1) | Faible |
| **G7 Absences** (+2) | Blessés ou suspendus parmi les habituels | `/injuries` | J-1 | 2021+ (à vérifier) | ❌ | Moyen (listes révisées après coup ?) | Moyen |
| **G8 Style (non supervisé)** | Cluster de style d'équipe ; interaction style × style | Statistiques d'équipe API | J-1 | Sauvegardé | ❌ | Faible si clusters appris sur le passé | Moyen |
| *Référence de marché* | Cotes plus/moins 2,5 et 1N2 (ouverture et clôture) | football-data | Ouverture J-2 ; **clôture = coup d'envoi** | 2000+ | ✅ | **Élevé** si la cote de clôture est utilisée pour H1 | Nul |

Les variables z1-z8 actuelles (forme, buts, xG, classement) restent des **candidates** du groupe G2. Le classement sera probablement dominé par l'Elo, ce qui est à vérifier par ablation.

### I.4 Progression des modèles

| Étape | Modèle | Concept pédagogique | Question à laquelle l'étape répond | Outil |
|---|---|---|---|---|
| M0 | **Références** B0 : Poisson(moyenne globale) ; B1 : moyenne par championnat × domicile ou extérieur, glissante ; marché : P(> 2,5) implicite | Pourquoi une référence ; propriété des scores | « Quel est le niveau zéro ? » | pandas, scipy |
| M1 | **Régression linéaire** T = AX + B (OLS) | Moindres carrés, hypothèses de Gauss-Markov, résidus, R², intervalles de confiance et de prédiction | « Pourquoi la linéaire ne suffit pas ? » (prédictions possiblement négatives, variance croissante avec la moyenne, loi discrète, intervalle symétrique absurde) | statsmodels OLS |
| M2 | **Poisson GLM sur T** | Lien log, maximum de vraisemblance, IRLS, déviance, **test de dispersion** (φ = χ²/ddl) | « Une loi de comptage fait-elle mieux ? » | statsmodels GLM |
| M3 | **Poisson par équipe** (modèle A remis à plat), avec erreurs standard groupées par match | Structure attaque × défense, loi du total par somme | « Faut-il décomposer par équipe ? » | statsmodels |
| M4 | **Dispersion** : binomiale négative si φ > 1 ; sinon constat (souvent φ ≈ 1 ou < 1 une fois les covariables incluses) | Surdispersion, sous-dispersion, test du rapport de vraisemblance | « La loi de Poisson est-elle adéquate ? » | statsmodels NB |
| M5 | **Dépendance entre équipes** : Dixon-Coles (existant), Poisson bivarié | Loi jointe, correction des petits scores | « La corrélation change-t-elle la loi du total ? » | code maison (existant), scipy |
| M6 | **Régularisation** : Poisson ridge ou lasso, splines (non-linéarités) | Compromis biais-variance, validation des hyperparamètres | « Plus de variables sans surapprendre ? » | scikit-learn `PoissonRegressor`, patsy |
| M7 | **Non linéaire** : gradient boosting à perte de Poisson | Arbres, ensembles, importance par permutation | « Y a-t-il des interactions que le GLM rate ? » | `HistGradientBoostingRegressor(loss="poisson")` |
| M8 | **Forces dynamiques** : Dixon-Coles pondéré dans le temps, réajusté à chaque date | Décroissance temporelle, paramètres latents | « Les forces latentes ajoutent-elles à Elo + xG ? » | code existant (`dixon_coles.py`) |
| Final | Le meilleur selon le protocole (I.7), **pas décidé à l'avance** | Sélection de modèle | — | — |

**Rôle du non supervisé** : clustering de styles d'équipes (k-means ou GMM sur profils statistiques par demi-saison), visualisé par ACP, puis testé comme groupe G8. C'est un vrai usage (hypothèse : deux styles offensifs donnent plus de buts), évalué comme les autres. Le clustering de joueurs (MVS) reste un exercice facultatif.

### I.5 Découpage et validation temporelle

```
2000 ─────── 2015-16 │ 2016-17 … 2020-21 │ 2021-22 │ 2022-23 │ 2023-24 │ 2024-25 ║ 2025-26 ║ 2026-27 →
Elo seul    rodage   │  apprentissage initial  │   validation glissante (4 plis)       ║ TEST SCELLÉ ║ prospectif
```

- **Validation glissante à fenêtre croissante** : pour chaque pli, on apprend sur toutes les saisons antérieures et on teste sur la saison suivante. Soit 4 plis et environ 7 000 matchs de test cumulés.
- Les **hyperparamètres** (demi-vies, fenêtres, régularisation) se choisissent par une validation **interne** à chaque pli (dernière saison d'apprentissage), comme le fait déjà `_select_xi`.
- **2025-26 est mise sous scellés** : elle n'est pas encore en base, ce qui est l'occasion idéale. Elle sert une seule fois, pour le modèle final. 2024-25 a déjà servi à décider (A contre B) : elle devient un pli de validation.
- **2026-27 est prospective** : les prédictions sont journalisées **avant** le coup d'envoi par l'application, puis évaluées. C'est la preuve ultime d'absence de fuite.
- **Régimes particuliers** : huis clos (indicateur), Ligue 1 à 18 clubs (effet championnat par saison ou tendance), 2019-20 incomplète.

### I.6 Métriques

| Métrique | Rôle | Pourquoi |
|---|---|---|
| **Log-loss du total** −mean log P̂(T = t_obs) | **Principale** | Règle de score strictement propre, liée à la vraisemblance, sensible à toute la distribution |
| **RPS du total** (catégories 0 à 7+) | Secondaire | Ordinale : prédire 3 quand il y a 4 buts est « moins faux » que prédire 0 |
| Brier de P(T > 2,5) | Secondaire | Lisible, directement comparable au marché |
| MAE et RMSE de E[T] | Descriptive | Pour comparer avec la régression linéaire (M1), **pas pour sélectionner** |
| Calibration | Diagnostic | Diagramme de fiabilité de P(T ≥ 3) par décile ; histogramme PIT randomisé (variable discrète) |
| Couverture des intervalles à 80 % et 90 % et largeur moyenne | Diagnostic | Honnêteté de l'incertitude affichée dans l'application |
| Log-loss par équipe (Y_H, Y_A) | Diagnostic | Vérifie chaque sous-modèle |
| Gain par tranche de journées | Diagnostic | Début de saison (H.4) |

**Inférence sur les écarts** : différence de perte **appariée match par match** entre deux modèles, intervalle à 95 % par **bootstrap par blocs de journées** (les matchs d'une même journée sont corrélés), test de Diebold-Mariano en complément.

### I.7 Comparer équitablement

1. Mêmes plis, **mêmes matchs** : l'intersection des matchs où tous les modèles comparés ont une prédiction. C'est essentiel, car les variables de composition manquent sur certains matchs.
2. Toutes les étapes ajustables (imputation, standardisation, sélection) sont ajustées **dans** le pli.
3. **Règle de décision écrite avant l'expérience** : un groupe de variables ou un modèle plus complexe est adopté seulement si le gain de log-loss du total a un intervalle à 95 % qui exclut 0 **et** si la calibration ne se dégrade pas. À gain non significatif, on garde le plus simple.
4. **Tous les essais sont journalisés** (fichiers `reports/experiments/*.json`), y compris ceux qui échouent. Le nombre d'essais est connu, ce qui aide à se méfier des comparaisons multiples.
5. Présentation finale : une **courbe d'apport** (gain cumulé par groupe G0 → G8, avec intervalles), ce qui répond directement à ta question « que rapporte chaque information ? ».

### I.8 Risques de fuite de données (liste de contrôle)

| Risque | Parade |
|---|---|
| Fenêtres calculées avec `<=` au lieu de `<` | Déjà traité (`<`) ; test existant ; ajouter un test « la ligne du match m ne change pas si l'on modifie le résultat de m » |
| Stabilité ou qualité du XI incluant le match courant | Calcul jusqu'à m−1 ; test dédié |
| Notes ou statistiques du joueur incluant le match courant | Idem |
| Standardisation ou imputation ajustée sur tout le jeu | Pipeline ajusté dans le pli |
| Hyperparamètres ou choix de variables faits sur le test | Validation interne ; 2025-26 scellée |
| Cote de clôture utilisée pour une prédiction à J-1 | Cote d'ouverture seulement, et en référence, pas en variable |
| Données révisées après coup (xG recalculé, listes de blessés complétées) | Journal quotidien daté ; dans le rapport, le reconnaître comme une limite |
| Rapprochements d'équipes faits avec des informations futures (renommages) | Sans effet sur la cible, acceptable |
| Date seule (football-data) contre heure (API) | Horodatage API en UTC comme référence |
| Remplissage silencieux des colonnes manquantes (`fill_value=0.0`) | Échec explicite |

---

## J. Stratégie Git pour une personne seule

### J.1 Options analysées

| Option | Pour | Contre | Verdict |
|---|---|---|---|
| Une branche par étape (01, 02…) | Simple à nommer | Branches de plusieurs semaines, conflits, fusions énormes | ❌ |
| **Une branche par sous-étape ou fonctionnalité** (≤ 1 semaine, ≤ ~10 h) | Changements petits et relisibles, retour arrière facile | Un peu de discipline | ✅ **Recommandé** |
| Commits directs sur `main` pour les changements mineurs | Pas de cérémonie | Risque si c'est du code | ✅ **Seulement la documentation de suivi** (`ETAT_PROJET.md`, `JOURNAL_ERREURS.md`, coquilles) |
| Pull Requests même seul | Relecture de la différence dans l'interface, CI visible, trace du « pourquoi » | Quelques clics | ✅ **Pour tout ce qui touche du code, des migrations ou des dépendances** |
| Validation locale avant fusion | Tests et analyse avant de pousser | — | ✅ Hook pre-commit et pre-push |
| Tags aux jalons | Revenir à un état connu, lier le rapport LaTeX à une version | — | ✅ |
| Branche `dev` en plus de `main` (actuel) | — | Double fusion sans bénéfice, pas de prod séparée | ❌ **Supprimer** (elle est identique à `main`) |

### J.2 Règles proposées

- **`main`** : toujours « vert » (les tests passent), toujours relançable. C'est la seule branche longue.
- **Quand créer une branche** : dès qu'on touche au code, à une migration, aux dépendances ou à la CI. Une branche = une sous-étape de `docs/realisation/` = un sujet.
- **Nommage** : `<type>/<etape>-<sujet-court>`, par exemple :
  - `fix/03-collecteur-lots-ids`
  - `feat/04-referentiel-ids-sources`
  - `feat/06-elo`
  - `exp/09-variantes-stabilite`
  - `docs/01-cadrage`
  - `chore/02-ruff-precommit`
- **Commits** : atomiques (un changement logique, qui compile et passe les tests), au format *Conventional Commits* en français :
  ```
  feat(ingestion): collecte des détails de matchs par lots de 20 identifiants

  Remplace l'appel unitaire /fixtures?id= par /fixtures?ids= (max 20).
  Divise la consommation de quota par ~20. Lit le champ `errors` et
  les en-têtes de quota ; s'arrête sous la réserve configurée.

  Refs: docs/realisation/03_collecte/README.md
  ```
  Types : `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `build`, `ci`, `data` (mappings et manifestes), `exp` (expériences). Titre de 72 caractères au plus, à l'impératif. Le corps explique le **pourquoi**.
- **Avant de fusionner** : `git fetch` puis `git rebase origin/main` (conflits résolus **dans la branche**) ; `uv run pytest` ; `uv run ruff check` ; `git push` ; ouvrir la PR avec un modèle (quoi, pourquoi, comment c'est testé, docs mises à jour ?). Relire l'onglet « Files changed » ligne par ligne. CI verte, puis fusion.
- **Type de fusion** : **merge commit** (comme aujourd'hui). Il conserve les commits atomiques et montre les limites de chaque sous-étape. `git revert -m 1 <merge>` annule une fonctionnalité entière, ce qui est un bon exercice. On supprime la branche après la fusion.
- **Tags annotés** :
  - `v0.1.0` : **état actuel, à poser avant la refonte** (point de retour) ;
  - `v0.2.0` : collecteur v2 ;
  - `data-freeze-2026-10` : gel des données ;
  - `v0.3.0` : référentiel ;
  - `v0.4.0` : variables ;
  - `v0.5.0` : modèle sélectionné ;
  - `v0.6.0` : API ;
  - `v1.0.0` : MVP.
- **Protection de `main`** : indisponible pour un dépôt privé sur GitHub Free ([doc GitHub](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)). On la remplace par un **hook `pre-push`** local qui refuse de pousser sur `main` si les tests échouent, et par la discipline « PR pour le code ».
- **CI** : ajouter un service Postgres dans GitHub Actions pour lancer **aussi** les tests `db`, plus `ruff`.
- **Identité** : fixer `git config --global user.name` et `user.email` une fois pour toutes (deux identités coexistent aujourd'hui).

### J.3 Secrets, fichiers générés, données volumineuses

- `.env` ignoré par Git. La clé API y est (en `SecretStr` dans `config.py`) pour que les tâches planifiées la trouvent. **Jamais** dans une conversation, un log ou un commit.
- Hook `gitleaks` en pre-commit : il détecte une clé avant qu'elle parte.
- **Si une clé a fuité** : la régénérer d'abord dans le tableau de bord (réécrire l'historique ne suffit pas, elle a déjà été vue), puis nettoyer.
- `data/`, `models/`, `reports/**/*.parquet`, `.ipynb_checkpoints` : ignorés.
- **Ce qui se versionne** : les **manifestes** (nombres, sha256), les YAML de rapprochement, les définitions d'expériences, les résultats JSON légers, les figures du rapport.
- Données sauvegardées **hors Git** : disque externe et cloud. Les licences (football-data : usage privé) interdisent de toute façon de publier les données.
- Le dépôt reste **privé**.

### J.4 Apprentissages Git planifiés

Petits exercices sur un fichier de documentation, dans `docs/realisation/02_environnement/` : provoquer et résoudre un conflit ; `git revert` contre `git reset` (local seulement) ; `git reflog` pour retrouver un commit « perdu » ; `git stash` ; `git bisect` sur un test ; tag annoté et `git checkout v0.1.0`. Une heure au total, très rentable.

---

## K. Structure documentaire

### K.1 Arborescence proposée

```
CLAUDE.md                                ← racine (lu automatiquement par Claude Code)
README.md                                ← vitrine : but, démarrage rapide, liens
docs/
├── README.md                            ← index de navigation de toute la doc
├── ETAT_PROJET.md                       ← état et prochaines actions
├── JOURNAL_ERREURS.md                   ← journal des erreurs
├── cadrage/
│   ├── 01_contexte_et_objectifs.md      (contexte, objectifs fonctionnels et pédagogiques)
│   ├── 02_perimetre.md                  (MVP, intermédiaire, avancé, hors périmètre, critères de fin)
│   ├── 03_contraintes_hypotheses_risques.md
│   ├── 04_donnees_sources.md            (sources, licences, inventaire des endpoints, tableau de couverture)
│   ├── 05_strategie_donnees.md          (collecte, stockage, couches, qualité, provenance)
│   ├── 06_catalogue_variables.md        (définition, source, horizon, fuite, coût : registre lisible)
│   ├── 07_strategie_modelisation.md
│   ├── 08_strategie_evaluation.md       (plis, métriques, règle de décision)
│   ├── 09_strategie_inference.md        (disponibilité, horizons, rejeu et live)
│   ├── 10_architecture_cible.md         (schémas : couches, flux, réseau)
│   ├── 11_architecture_depot.md
│   ├── 12_pipelines_et_flux.md          (contrats entre briques, commandes, planification)
│   ├── 13_methode_de_travail.md         (Git, sessions Claude, définition de terminé)
│   └── 14_glossaire.md                  (vocabulaire métier et technique)
├── technologies/
│   ├── README.md                        (retenues, facultatives, écartées, avec raisons)
│   ├── _modele_mini_cours.md            (à quoi ça sert, comment ça marche, place dans le projet,
│   │                                     ce que ça remplace, avantages, limites, commandes essentielles)
│   ├── uv.md  git_github.md  docker_compose.md  postgresql.md  sqlalchemy_alembic.md
│   ├── pytest.md  pandas_parquet.md  statsmodels_sklearn.md  fastapi.md  streamlit.md
│   └── ruff_precommit.md  wsl2.md  latex.md          (un fichier par technologie, au moment où elle entre)
├── decisions/                           ← ADR (Architecture Decision Records)
│   ├── README.md                        (index : n°, titre, statut, date)
│   ├── _modele_adr.md                   (contexte, options, décision, conséquences, statut)
│   └── ADR-0001-… .md                   (une par décision de la partie M)
├── realisation/
│   ├── README.md                        (carte des étapes, statut, jalons)
│   ├── _modele_etape.md                 (objectif, critères d'entrée, sous-étapes, fichiers, commandes,
│   │                                     tests, erreurs possibles, décisions, résultats attendus,
│   │                                     critères de sortie)
│   ├── 01_cadrage/
│   ├── 02_environnement/                (uv, WSL2, Docker, ruff, pre-commit, CI, CLI, exercices Git)
│   ├── 03_collecte/                     (sprint API-FOOTBALL : collecteur v2, inventaire, gel)
│   ├── 04_referentiel/                  (staging reconstruit depuis le brut, identifiants, migrations)
│   ├── 05_qualite_donnees/
│   ├── 06_variables/                    (Elo, glissants, calendrier, puis composition et stabilité)
│   ├── 07_exploration/
│   ├── 08_protocole_et_references/      (plis, métriques, références B0, B1 et marché)
│   ├── 09_modeles/                      (M1 → M8, une sous-étape par modèle)
│   ├── 10_selection_et_entrainement_final/
│   ├── 11_inference/
│   ├── 12_api/
│   ├── 13_interface/
│   ├── 14_tests_bout_en_bout/
│   ├── 15_exploitation_et_suivi/        (planification, suivi prospectif, maintenance)
│   └── 16_documentation_finale/
│       (chaque étape : README.md ; sous-dossiers NN_sous_etape/README.md créés quand on démarre)
├── resultats/                           ← synthèses lisibles des expériences (liens vers reports/*.json)
├── archives/                            ← anciens récaps et RECAP_PROJET.md, figés, non maintenus
└── latex/
    ├── mathematiques/  (main.tex, chapitres/*.tex, figures/, references.bib)
    └── rapport/        (main.tex, chapitres/*.tex, figures/, references.bib)
```

**Pourquoi cette organisation**

- Les 17 étapes de ton exemple sont regroupées en **16**, en fusionnant « ingestion » et « stockage », qui sont indissociables. Les étapes « baselines, modélisation, évaluation » deviennent **protocole et références**, puis **modèles**, puis **sélection** : le protocole doit exister **avant** les modèles.
- **On ne crée pas de dossiers vides** : un sous-dossier naît quand la sous-étape démarre.
- Le dossier `decisions/` (ADR) répond à « raisons de chaque choix » et remplace la section « décisions révisées » du RECAP.
- **Migration de l'existant** :

| Fichier actuel | Destination |
|---|---|
| `OBJECTIFS.md` | `cadrage/01` |
| `RECAP_PROJET.md` | Découpé entre `cadrage/`, `decisions/` et `JOURNAL_ERREURS.md`, puis archivé |
| `MODELE_MATHEMATIQUE.md` | Source des chapitres LaTeX |
| `RESULTATS_MODELE.md` | `resultats/` |
| `API_FOOTBALL_ABONNEMENT.md` | `realisation/03_collecte/` |
| `recaps/` | `archives/` |

### K.2 Rôle, détail et fréquence de mise à jour

| Fichier | Rôle | Niveau de détail | Mise à jour |
|---|---|---|---|
| `CLAUDE.md` (racine) | Consignes **stables** pour Claude Code : but (3 lignes), carte du dépôt, commandes, conventions, règles Git, tests et documentation, définition de terminé, contraintes (gratuit, local, légalité, **ne jamais consommer de quota API sans accord explicite**, ne jamais afficher de secret, ne jamais modifier `data/raw`), fichiers à lire d'abord (`docs/ETAT_PROJET.md`, puis le README de l'étape en cours), comportement attendu (reformuler la tâche, proposer un plan, petits commits, mettre à jour l'état et le journal). **150 lignes au plus**, rien de daté. | Synthétique | Rare (changement de convention) |
| `docs/ETAT_PROJET.md` | Où on en est : jalon courant ; fait récemment ; en cours ; bloqué ; décisions ouvertes (liens ADR) ; prochaines actions à court terme (prochaine session), moyen terme (jalon), long terme ; **commandes et tests à lancer en début de prochaine session**. **100 lignes au plus.** | Concis, factuel | **À chaque fin de session** |
| `docs/JOURNAL_ERREURS.md` | Une entrée par erreur résolue : identifiant, date, contexte, message, cause, solution, fichiers, prévention, test de non-régression. Reprendre les incidents du RECAP §9 (port 5432, BOM, xG non persisté, doublons, Ajaccio). | Détaillé | À chaque erreur résolue |
| `docs/decisions/ADR-*.md` | Une décision : contexte, options, choix, conséquences, statut (proposée, acceptée, remplacée) | Moyen | À chaque décision ; jamais réécrite, mais remplacée par une nouvelle ADR |
| `docs/cadrage/*` | Référence du « quoi » et du « pourquoi » | Moyen à détaillé | À chaque jalon ou changement de périmètre |
| `docs/technologies/*` | Mini-cours et place dans le projet | Pédagogique | À l'entrée d'une technologie |
| `docs/realisation/*/README.md` | Le « comment » de chaque étape | Détaillé et opérationnel | Pendant l'étape, puis figé |
| `docs/resultats/*` | Ce que disent les expériences | Moyen, chiffré | À chaque expérience |
| `docs/latex/mathematiques/` | De ŷ = AX + B aux modèles réellement utilisés : notations, hypothèses, équations, fonctions de coût, estimation, lois, métriques, intervalles, limites, et **lien vers le fichier Python** correspondant à chaque concept (forme quadratique de la stabilité incluse) | Long, rigoureux | Au fil de l'étape 09 (un chapitre par modèle) |
| `docs/latex/rapport/` | Rapport final (page de titre, résumé, sommaire, contexte, objectifs, problématique, état de l'art, contraintes, données, qualité, architecture, solutions, décisions, développement, méthodologie, modèles, protocole, résultats, limites, difficultés, perspectives, conclusion, annexes, bibliographie) | Rédigé, narratif | À chaque jalon (environ 1 fois par mois) |

**LaTeX et Overleaf** : l'offre gratuite d'Overleaf n'inclut **ni Git ni la synchronisation GitHub**, et limite l'historique à 24 heures ([doc Overleaf](https://docs.overleaf.com/getting-started/free-and-premium-plans/premium-features)).

- La **source de vérité est le dépôt**. Chaque dossier LaTeX est autonome (`main.tex`, chapitres, figures, bibliographie).
- Pour Overleaf : téléverser le dossier en zip à chaque jalon.
- Pour compiler en local, sans Overleaf : Tectonic (un seul exécutable) ou TeX Live sous WSL2.
- Les figures sont générées par du code dans `reports/figures/` et copiées dans le dossier LaTeX.

---

## L. Roadmap

Hypothèses : 10 h par semaine, seul, Claude Code pour l'essentiel du code, et environ 40 % du temps consacré à relire et comprendre.

| Période | Jalon | Contenu principal | Heures | Critères de fin |
|---|---|---|---|---|
| **S0** · 24-27 sept. | **J0 Cadrage validé** | État des lieux (annexe 1) ; export et sauvegarde du brut ; décisions 1 à 12 → ADR ; tag `v0.1.0` | 4 | Décisions bloquantes tranchées ; brut existant copié hors Docker |
| **S1** · 28 sept. - 4 oct. | **J1 Collecteur v2** | Collecteur v2 (lots de 20, `errors`, quota, fichiers, reprise) ; inventaire de couverture ; listes et détails du top 5 (dont 2025-26 et 2026-27), D2, coupes | 10 | Détails collectés et **contrôlés** pour le top 5 ; tag `v0.2.0` |
| **S2** · 5-11 oct. | — | Joueurs, coachs, transferts, blessures ; journal quotidien ; contrôles de qualité ; `CLAUDE.md`, `ETAT_PROJET.md`, `JOURNAL_ERREURS.md`, squelette de `docs/` | 10 | Rapport qualité v1 ; documentation de suivi en place |
| **S3** · 12-18 oct. (fin d'abonnement) | **J2 Données gelées** | Rattrapages ; `DATA_FREEZE.md` ; 2 sauvegardes **restaurées avec succès** ; tag `data-freeze-2026-10` | 8 | Plus rien d'irrécupérable ne dépend de l'abonnement |
| S4-S6 · jusqu'à mi-nov. | **J3 Référentiel** | WSL2 (si retenu) ; base locale unique ; migration 0004 (identifiants sources, index, coach, `ops`) ; `staging` **reconstruit depuis le brut** ; YAML de rapprochement ; tests sur payloads réels | 30 | `fp load` reconstruit tout en moins de 2 h ; contrôles de qualité au vert ; plus aucune correction manuelle en base |
| S7-S9 · jusqu'à début déc. | **J4 Variables v2** | Elo maison ; glissants sans remise à zéro ; calendrier ; registre des variables ; instantanés Parquet ; exploration statistique (notebooks) | 30 | Jeu de données versionné ; catalogue des variables rédigé ; chapitre LaTeX « données » |
| S10-S12 · jusqu'à fin déc. | **J5 Protocole et références** | Plis, métriques du total, bootstrap ; B0, B1, marché ; M1 (linéaire), M2 et M3 (Poisson) ; chapitres LaTeX 1 à 3 | 30 | Rapport de validation glissante ; M3 comparé à B1 avec intervalles |
| S13-S16 · jusqu'à fin janv. | **J6 Modèle MVP sélectionné** | M4, M5, M6 ; ablations G0-G3 ; règle de décision appliquée ; test scellé 2025-26 **une seule fois** ; carte d'identité du modèle | 40 | Modèle MVP choisi et justifié (ADR) ; tag `v0.5.0` |
| S17-S19 · jusqu'à mi-févr. | **J7 Inférence et API** | `predict` avec disponibilité et traçabilité ; FastAPI (routes F.6) ; tests d'API | 30 | `GET /matches` et `POST /predictions` fonctionnent en rejeu ; tag `v0.6.0` |
| S20-S22 · jusqu'à début mars | **J8 MVP** | Streamlit ; mode rejeu et live avant composition ; test de bout en bout ; documentation ; rapport LaTeX v1 | 30 | Critères E.1 remplis ; **tag `v1.0.0`** |
| Mars → juin 2027 | **J9 Version intermédiaire** | Composition : qualité du XI, stabilité (expérience H.8), entraîneur ; régularisation, boosting ; Compose avec 3 services ; planification ; suivi prospectif | ~120 | Critères E.2 |
| Au-delà | J10 Version avancée | Au choix, selon l'envie et les résultats | — | Critères E.3 |

**Marge** : environ 20 % de temps imprévu est inclus implicitement (vacances, bugs). Si le retard dépasse 3 semaines, on réduit le périmètre du MVP (par exemple M5 et M6 passent en version intermédiaire), **pas** la qualité du protocole.

---

## M. Sujets à convenir avant de démarrer

Classement par priorité. Légende :

- 🔴 bloquante tout de suite (avant de dépenser plus de quota) ;
- 🟠 bloquante pour la phase suivante (à trancher avant la fin de l'abonnement) ;
- 🟡 importante, non bloquante ;
- ⚪ reportable.

Les mentions **[dépôt]** et **[données]** signalent une décision qui dépend de l'analyse du dépôt ou de la disponibilité réelle des données.

### 🔴 1. Que faire du backfill API-FOOTBALL en cours ? [données]

- **Question** : laisser tourner `api_football_scraper.py` actuel, ou l'arrêter pour passer au collecteur v2 ?
- **Pourquoi** : ses défauts (D4 à D6, D8) font perdre du temps et exposent le brut. Son état réel m'est inconnu.
- **Options et conséquences** :
  - (a) le laisser finir : aucune modification de code, mais une collecte lente et un brut uniquement dans Docker ;
  - (b) l'arrêter tout de suite : on repart proprement, mais on risque d'interrompre une saison à mi-parcours (sans gravité, la collecte reprend) ;
  - (c) le laisser finir la saison en cours de traitement, puis l'arrêter : le compromis.
- **Recommandation** : (c) + **exporter tout de suite** le contenu de `raw.api_football_fixture_detail` en fichiers et le copier hors du PC. Rien de ce qui a été téléchargé n'est perdu : les payloads contiennent les identifiants.

### 🔴 2. Quel périmètre collecter pendant l'abonnement ? [données]

- **Question** : quelles compétitions, quelles saisons, quels endpoints ?
- **Pourquoi** : c'est la seule décision réellement irréversible du projet.
- **Options et conséquences** :
  - (a) top 5, 2015-2024 (actuel) : manque la saison écoulée et la saison en cours, les promus, le repos, l'âge, les coachs ;
  - (b) (a) + 2025-26 et 2026-27 : le minimum vital ;
  - (c) (b) + D2 + coupes + joueurs + coachs + transferts + blessures + journal quotidien : environ 15 000 requêtes, tout le potentiel du projet ;
  - (d) (c) + autres championnats : un plus marginal.
- **Recommandation** : **(c)**, et (d) seulement s'il reste du temps. À ajuster après l'inventaire de couverture (`/leagues`).

### 🔴 3. Sous quel format stocker le brut ? [dépôt]

- **Question** : garder le JSONB dans Postgres comme seule copie, ou des fichiers ?
- **Pourquoi** : aujourd'hui, un `docker compose down -v` efface des données payantes (D8).
- **Options et conséquences** :
  - (a) JSONB seul : simple, mais fragile et lent (D6) ;
  - (b) fichiers `.json.gz` + manifeste comme source de vérité, JSONB facultatif : robuste, sauvegardable, rejouable, avec un peu de code ;
  - (c) les deux, systématiquement : double stockage à maintenir.
- **Recommandation** : **(b)**.

### 🔴 4. Faut-il modifier le collecteur pendant l'abonnement ? [dépôt]

- **Question** : accepter une courte phase de développement (environ 5 h) avant de continuer la collecte ?
- **Pourquoi** : sans lots de 20, lecture de `errors`, garde-fou de quota et reprise, le périmètre (c) est plus lent et plus risqué (collectes silencieusement vides).
- **Options et conséquences** : (a) non : on reste sur le périmètre (a) ou (b) ; (b) oui, sur une branche `fix/03-collecteur-lots-ids`, avec des tests sur payloads réels.
- **Recommandation** : **(b)**. Le workflow Git (décision 15) peut être appliqué tout de suite, à titre provisoire.

### 🔴 5. Date de fin et renouvellement de l'abonnement

- **Question** : quand l'abonnement se termine-t-il exactement, et se renouvelle-t-il automatiquement ?
- **Pourquoi** : le planning G.4 en dépend. Le guide indique une souscription le 22/09 « pour 1 mois », ta mission dit environ 20 jours.
- **Options** : laisser expirer ; couper le renouvellement automatique ; prolonger d'un mois (19 $).
- **Recommandation** : vérifier dans le tableau de bord, **couper le renouvellement automatique** si tu ne le veux pas, et reporter la question d'un réabonnement ponctuel (décision 28).

### 🔴 6. Où et comment sauvegarder ?

- **Question** : quelle stratégie de sauvegarde pour le brut et les manifestes ?
- **Pourquoi** : une panne de disque après la fin de l'abonnement serait irrémédiable.
- **Options** : disque externe ; cloud gratuit (Google Drive, OneDrive) en archive chiffrée ; les deux.
- **Recommandation** : **les deux**, après chaque journée de collecte importante, avec **un test de restauration** avant le gel.

### 🟠 7. Quel référentiel maître pour les identifiants ? [dépôt]

- **Question** : qui fait foi pour matchs, équipes et joueurs ?
- **Pourquoi** : identification par nom = homonymes fusionnés (D1, D2), corrections manuelles non reproductibles (D11).
- **Options et conséquences** :
  - (a) garder la logique actuelle (football-data crée les matchs, noms pour les joueurs) : dette et erreurs silencieuses ;
  - (b) API-FOOTBALL maître (identifiants numériques), football-data et Understat rattachés par YAML versionnés, `staging` **reconstruit depuis le brut** : environ 30 h, mais une base saine ;
  - (c) un identifiant interne neutre et des tables de correspondance pour toutes les sources : plus général, plus long.
- **Recommandation** : **(b)**, en gardant la structure de tables `*_source_mapping` existante (qui rend (c) possible plus tard).

### 🟠 8. Cible, sortie et métrique principale

- **Question** : que prédit-on exactement, et comment juge-t-on ?
- **Pourquoi** : aujourd'hui, on évalue le score exact et le 1N2, pas le nombre de buts.
- **Options et conséquences** :
  - (a) total T directement : simple, mal spécifié ;
  - (b) buts par équipe, puis loi du total : cohérent avec l'existant, riche ;
  - (c) valeur ponctuelle seule : trompeuse, vu le bruit.
- **Recommandation** : **(b)**, avec une **sortie en distribution**, le **log-loss du total** comme métrique principale, le RPS et le Brier plus/moins 2,5 en secondaire ; M1 et M2 (sur T) comme étapes pédagogiques.

### 🟠 9. Horizon de prédiction et rôle des compositions

- **Question** : le MVP prédit-il avant ou après la publication des compositions ?
- **Pourquoi** : c'est ce qui décide quand le bouton s'active, quelles variables sont possibles et ce qui marche après l'abonnement.
- **Options et conséquences** :
  - (a) après composition seulement (décision actuelle du dépôt) : bouton inactif sauf 1 h avant le match, et **impossible en live sans abonnement** ;
  - (b) avant composition pour le MVP, deux horizons en version intermédiaire : MVP toujours fonctionnel, apport de la composition mesuré à part ;
  - (c) « onze probable » : complexité et erreurs.
- **Recommandation** : **(b)**. Cela modifie la décision « booléen compo publiée » de `RECAP_PROJET.md` §2, et nécessite donc une ADR.

### 🟠 10. Comment l'application fonctionne-t-elle après l'abonnement ?

- **Question** : live, rejeu, ou les deux ?
- **Pourquoi** : le plan gratuit ne couvre que les saisons 2022 à 2024.
- **Options et conséquences** :
  - (a) live seulement : dépend des sources gratuites, sans composition ;
  - (b) rejeu seulement (date de référence passée, données « telles que connues à l'époque ») : toujours démontrable, évaluation visible, mais pas de « vrais » prochains matchs ;
  - (c) les deux : rejeu complet et live avant composition (football-data fixtures et cotes, Understat).
- **Recommandation** : **(c)**, rejeu d'abord.

### 🟠 11. Protocole de validation et mise sous scellés

- **Question** : comment découper le temps, et quelle saison garder intacte ?
- **Pourquoi** : 2024-25 a déjà servi à décider ; il faut un test vierge.
- **Options** : (a) une saison de test (actuel) ; (b) validation glissante 2021-22 → 2024-25 + **2025-26 scellée** + 2026-27 prospective.
- **Recommandation** : **(b)**, décidée **maintenant**, tant que 2025-26 n'est pas en base.

### 🟠 12. Masse salariale et MVS

- **Question** : que faire de la variable « masse salariale » et du module `market_value/` ?
- **Pourquoi** : le salaire réel est indisponible, la valeur marchande est juridiquement fragile, et le MVS est arbitraire (G.12).
- **Options et conséquences** :
  - (a) poursuivre le MVS : lourd, invérifiable ;
  - (b) le mettre en pause, avec un indicateur « qualité du XI » en version intermédiaire et l'Elo dès le MVP : simple et testable ;
  - (c) tout supprimer : perte d'un exercice non supervisé possible.
- **Recommandation** : **(b)**. Le code et les tests du MVS sont conservés ; `hdbscan` pourra être retiré.

### 🟡 13. Environnement de travail et matériel

- **Question** : Windows natif avec Git Bash, ou WSL2 (Ubuntu) ?
- **Pourquoi** : plusieurs incidents passés sont propres à Windows (BOM, encodage, port 5432) ; Bash est ton terminal de référence ; cron est natif sous WSL2.
- **Options et conséquences** : (a) Windows : rien à changer, mais frictions et pas de cron ; (b) WSL2 : environ 2 h de mise en place, plus de RAM (Docker Desktop utilise déjà WSL2).
- **Recommandation** : **(b)**, **après** le gel des données (ne pas changer d'environnement pendant la collecte).
- **Il me faut** : RAM, espace disque libre, version de Windows.

### 🟡 14. Une ou trois bases ?

- **Question** : garder dev, test et prod Neon ?
- **Options et conséquences** :
  - (a) garder : triple maintenance, limite de stockage Neon, aucune vraie prod ;
  - (b) une base locale « de travail » (reconstructible) et une base de test éphémère : simple ;
  - (c) SQLite : sans Docker, moins formateur.
- **Recommandation** : **(b)**. Neon et `APP_ENV=prod` sont retirés.

### 🟡 15. Workflow Git

- **Question** : adopter J.2 ?
- **Options** : (a) actuel, `feature` → `dev` → `main` ; (b) `main` + branches courtes + PR pour le code + merge commit + tags.
- **Recommandation** : **(b)**, suppression de `dev`, tag `v0.1.0` immédiat.

### 🟡 16. Variante de stabilité et protocole

- **Question** : figer la remise à zéro par saison (spécification actuelle) ou tester des variantes ?
- **Options** : (a) spécification telle quelle ; (b) expérience H.8, avec une variante à décroissance recommandée à défaut.
- **Recommandation** : **(b)**, avec une règle de décision écrite avant l'expérience.

### 🟡 17. Sources gratuites complémentaires [données]

- **Question** : quelles sources gratuites utiliser en plus d'API-FOOTBALL ?
- **Pourquoi** : ClubElo est désormais derrière une authentification ; le statut d'Understat n'est pas documenté ; football-data doit être gardé en entier.
- **Options** : Elo maison ou ClubElo ; Understat conservé ou remplacé (xG API-FOOTBALL si présent dans `statistics`, à vérifier ; ou xG exclu du live).
- **Recommandation** : **Elo maison** ; **vérifier les CGU et le `robots.txt` d'Understat** avec le même critère que Transfermarkt, avant d'en dépendre pour le live ; football-data en colonnes complètes.

### 🟡 18. Rôle des cotes

- **Question** : les cotes sont-elles une variable ou une référence de comparaison ?
- **Pourquoi** : une variable « cote » rend le modèle meilleur mais sans intérêt pédagogique (il recopierait le marché).
- **Options** : (a) référence seulement ; (b) variable dans la version avancée, cote d'ouverture seulement.
- **Recommandation** : **(a)**, (b) éventuellement plus tard, comme une expérience séparée.

### 🟡 19. Restructuration de la documentation

- **Question** : migrer vers l'arborescence K ?
- **Recommandation** : oui, pendant S2 (tâche qui ne consomme pas de quota) ; récaps archivés, pas supprimés.

### 🟡 20. Conventions

- **Question** : langue et nommage ?
- **Recommandation** : identifiants de code en anglais (comme aujourd'hui) ; documentation, docstrings et messages de commit en français ; `snake_case` ; noms de variables de modèle préfixés par groupe (`g1_elo_own`…) ; ruff comme référence de style.

### 🟡 21. Technologie API et interface

- **Question** : quels outils pour l'API et l'interface ?
- **Options** : FastAPI + Streamlit (rapide, Python) ; FastAPI + Jinja et HTMX (plus « web », plus long).
- **Recommandation** : FastAPI + Streamlit ; HTMX éventuellement en version avancée.

### 🟡 22. Orchestration et planification

- **Question** : comment enchaîner et planifier les traitements ?
- **Options** : `python -m` + Makefile ; CLI Typer ; orchestrateur (écarté).
- **Recommandation** : CLI `fp` (Typer) + cron sous WSL2 à partir de la version intermédiaire ; lancements manuels documentés avant.

### ⚪ 23. MLflow

Facultatif. Des fichiers JSON d'expériences suffisent au MVP ; MLflow en version intermédiaire seulement si leur lecture devient pénible.

### ⚪ 24. DuckDB

Facultatif, pour de l'analyse SQL sur Parquet pendant l'exploration.

### ⚪ 25. Modèles avancés et non supervisé

Poisson bivarié, modèles hiérarchiques, styles d'équipes : en version avancée, selon les résultats.

### ⚪ 26. Compilation LaTeX

Overleaf gratuit avec téléversement manuel, contre Tectonic ou TeX Live en local. On décide quand le premier chapitre est prêt.

### ⚪ 27. Accès réseau distant

Accès depuis le Wi-Fi local, puis éventuellement Tailscale : en version avancée seulement.

### ⚪ 28. Réabonnement ponctuel

Un mois par an (juin) pour compléter la saison écoulée ; ou abonnement pendant quelques journées pour une démo live avec composition. À décider au printemps 2027.

### ⚪ 29. Jeux de données dérivés de Transfermarkt

Je **confirme l'exclusion** décidée dans le dépôt (même provenance, même fragilité). À rouvrir seulement si ta position sur ce risque change.

### ⚪ 30. Blessures dans le modèle

En version intermédiaire ou avancée, selon la couverture réelle observée (probablement 2021+) et la qualité des listes.

---

## Annexe 1 : vérifications immédiates, en lecture seule, à lancer sur ta base dev

Rien ici ne modifie la base, et rien ne consomme de quota.

```sql
-- 1. Avancement du backfill et taille du brut
SELECT count(*) AS n_fixtures,
       pg_size_pretty(pg_total_relation_size('raw.api_football_fixture_detail')) AS taille
FROM raw.api_football_fixture_detail;

SELECT raw_payload->'league'->>'season' AS saison,
       raw_payload->'league'->>'id'     AS league,
       count(*)
FROM raw.api_football_fixture_detail GROUP BY 1,2 ORDER BY 1,2;

-- 2. Format réel du poste dans les statistiques joueurs (attendu : 'G','D','M','F')
SELECT DISTINCT raw_payload->'players'->0->'players'->0->'statistics'->0->'games'->>'position'
FROM raw.api_football_fixture_detail LIMIT 10;

-- 3. Les identifiants joueurs sont bien présents dans le brut (le brut est sain)
SELECT raw_payload->'lineups'->0->'startXI'->0->'player' AS exemple_joueur
FROM raw.api_football_fixture_detail LIMIT 3;

-- 4. Compositions, entraîneur, statistiques d'équipe, xG API éventuel
SELECT count(*) FILTER (WHERE jsonb_array_length(raw_payload->'lineups') = 2)     AS avec_2_compos,
       count(*) FILTER (WHERE raw_payload->'lineups'->0->'coach'->>'id' IS NOT NULL) AS avec_coach,
       count(*) FILTER (WHERE jsonb_array_length(raw_payload->'statistics') = 2)  AS avec_stats_equipe,
       count(*) FILTER (WHERE raw_payload::text LIKE '%expected_goals%')          AS avec_xg_api
FROM raw.api_football_fixture_detail;

-- 5. Staging déjà touché ? (si > 0, vérifier les homonymes)
SELECT (SELECT count(*) FROM staging.lineup) AS lineup,
       (SELECT count(*) FROM staging.player_match_stats) AS pms,
       (SELECT count(*) FROM staging.player) AS players;
```

Et dans le tableau de bord API-FOOTBALL : date de fin, renouvellement automatique, requêtes consommées depuis le 22/09.

## Annexe 2 : sources consultées

- [API-FOOTBALL : récupérer toutes les données d'un championnat (paramètre `ids`, 20 maximum)](https://www.api-football.com/news/post/how-to-get-all-fixtures-data-from-one-league)
- [API-FOOTBALL : fonctionnement des limites de débit (300 par minute en Pro, en-têtes, 429)](https://www.api-football.com/news/post/how-ratelimit-works)
- [API-FOOTBALL : guide de démarrage (quotas et tarifs des offres)](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
- [API-FOOTBALL : nouveautés (players/profiles, injuries par ids)](https://www.api-football.com/news/post/api-football-new-release-available)
- [Message d'erreur du plan gratuit : saisons 2022 à 2024 seulement](https://github.com/nimeshjm/fantasy-football/issues/58)
- [Type des postes dans les réponses fixtures (G, D, M, F) : client Go api-football](https://pkg.go.dev/github.com/syurchen93/api-football-client/response/fixtures)
- [football-data.co.uk : contenu, cotes, conditions d'usage](https://www.football-data.co.uk/data.php)
- [football-data.org : limites de l'offre gratuite en 2026](https://www.thestatsapi.com/blog/football-data-org-free-tier-limits-2026)
- [ClubElo : API CSV passée derrière une authentification (signalé le 23/09/2026)](https://github.com/probberechts/soccerdata/issues/977)
- [GitHub : branches protégées et offres](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Overleaf : fonctions premium (Git et GitHub non inclus en gratuit)](https://docs.overleaf.com/getting-started/free-and-premium-plans/premium-features)
