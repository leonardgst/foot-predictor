# Journal des erreurs

Une entrée par erreur résolue, la plus récente en haut. Modèle :

```
## E-NNN — Titre court (AAAA-MM-JJ)
- Contexte :
- Message d'erreur :
- Cause :
- Solution :
- Fichiers concernés :
- Prévention :
- Test de non-régression :
```

---

## E-021 — PR fusionnée dans une branche déjà fusionnée au lieu de `main` (2026-09-29)

- **Contexte** : la PR #12 (tri de `docs/`) avait été ouverte avec pour base `docs/01-adr-0008-0013`, la branche de la PR #11, pour ne montrer que ses propres commits. La #11 a été fusionnée dans `main` avant la #12, et sa branche n'a pas été supprimée.
- **Message d'erreur** : aucun ; GitHub a affiché la #12 « Merged », mais le tri (archives, ADR-0014, `docs/README.md`, journal E-006 à E-020) n'est jamais arrivé dans `main`.
- **Cause** : une PR empilée garde sa base d'origine tant que la branche de base existe. GitHub ne la redirige vers `main` que lorsque cette branche est supprimée.
- **Solution** : nouvelle branche `docs/01-tri-documentation-vers-main`, partie de `docs/01-tri-documentation`, avec fusion de `origin/main` (conflit sur `ETAT_PROJET.md` résolu en gardant l'état P3), puis nouvelle PR vers `main`.
- **Fichiers concernés** : aucun fichier de code ; historique Git et branches distantes.
- **Prévention** : supprimer la branche d'une PR dès sa fusion (règle de `CLAUDE.md`) ; avant de fusionner une PR, vérifier que sa base est `main` (`gh pr view <n> --json baseRefName`).
- **Test de non-régression** : sans objet (procédure Git).

Les entrées ci-dessous reprennent les incidents documentés avant le 2026-09-24 (source : `RECAP_PROJET.md` §9 et §12, et les récaps, archivés dans `docs/archives/`). Les numéros sont des identifiants, pas un ordre chronologique : E-006 à E-020 ont été ajoutées lors du tri de la documentation (2026-09-28).

## E-020 — HDBSCAN entraîné sans `prediction_data` (2026-09-22)

- **Contexte** : écriture des tests de `market_value/clustering/assign_cluster.py`.
- **Message d'erreur** : `AttributeError: No prediction data was generated`.
- **Cause** : `_fit_hdbscan` (`build_clusters.py`) créait `hdbscan.HDBSCAN` sans `prediction_data=True` ; `hdbscan.approximate_predict` échouait à la première réaffectation d'un joueur.
- **Solution** : `prediction_data=True` ajouté à l'entraînement.
- **Fichiers concernés** : `market_value/clustering/build_clusters.py`, `assign_cluster.py`.
- **Prévention** : tester aussi le chemin de réutilisation d'un modèle sauvegardé, pas seulement l'entraînement.
- **Test de non-régression** : partiel. `test_assign_cluster_uses_hdbscan_approximate_predict_when_no_native_predict` construit son propre modèle ; aucun test ne vérifie l'option dans `_fit_hdbscan`.

## E-019 — `KeyError` quand aucun joueur n'a assez de minutes (2026-09-22)

- **Contexte** : `market_value/preprocessing/per90.py::build_player_vectors`, par exemple en tout début de saison.
- **Message d'erreur** : `KeyError`, levé par `pd.DataFrame([]).set_index("player_id")`.
- **Cause** : après le filtre `MIN_MINUTES_PER_MATCH`, la liste des lignes éligibles est vide.
- **Solution** : renvoyer un DataFrame vide.
- **Fichiers concernés** : `market_value/preprocessing/per90.py`.
- **Test de non-régression** : `tests/market_value/test_per90.py::test_input_with_no_eligible_rows_returns_empty_dataframe`.

## E-005 — xG équipe jamais enregistré (2026-09-22)

- **Contexte** : backfill Understat sur 10 saisons.
- **Message d'erreur** : aucun ; le script annonçait 18 008 lignes « traitées » alors que seules 6,6 % des lignes avaient un xG.
- **Cause** : `upsert_team_match_xg` était importée dans `understat.py` mais jamais appelée.
- **Solution** : appel ajouté pour chaque équipe ; couverture passée à 99,98 %.
- **Fichiers concernés** : `ingestion/understat.py`, `ingestion/common.py`.
- **Prévention** : après une ingestion, vérifier les colonnes remplies, pas seulement le nombre de lignes « traitées ». Un compteur de succès doit mesurer ce qui est écrit, pas ce qui est lu.
- **Test de non-régression** : à ajouter (test d'ingestion vérifiant que `xg_for` est non nul).

## E-004 — Équipe Ajaccio mal rattachée (2026-09-22)

- **Contexte** : backfill football-data et Understat.
- **Message d'erreur** : 41 lignes ignorées.
- **Cause** : `Ajaccio` (AC Ajaccio, 2022-23) mappé vers `GFC Ajaccio` dans les YAML ; `Ajaccio GFCO` absent.
- **Solution** : YAML corrigés, équipes renommées et `TeamSourceMapping` repointé **à la main en base dev**.
- **Fichiers concernés** : `mappings/football_data_teams.yaml`, `mappings/understat_teams.yaml`.
- **Prévention** : corriger un YAML ne répare pas une entité déjà créée (voir E-003). `mappings/api_football_teams.yaml` contient encore `Ajaccio: GFC Ajaccio` (rapport B.4, D2) ; correction définitive par le référentiel par identifiants (ADR-0008).
- **Test de non-régression** : non.

## E-018 — Accents et emojis mal affichés dans la console Windows (2026-09-21)

- **Contexte** : scripts lancés depuis Git Bash ou PowerShell (`check_raw.py`, `check_env.py`).
- **Message d'erreur** : caractère `�` à la place des lettres accentuées ; plantage à l'affichage des emojis (message non consigné).
- **Cause** : la console Windows n'utilise pas UTF-8 par défaut.
- **Solution** : préfixer la commande par `PYTHONIOENCODING=utf-8`.
- **Prévention** : environnement WSL2 envisagé (décision M13).

## E-017 — `check_raw.py` disparu du disque (2026-09-21)

- **Contexte** : remise en ordre du dépôt ; le RECAP décrivait `scripts/one_off/check_raw.py` comme conservé.
- **Message d'erreur** : aucun ; fichier introuvable.
- **Cause** : script jamais commité.
- **Solution** : script **reconstruit** d'après sa description ; ce n'est pas l'original.
- **Fichiers concernés** : `scripts/one_off/check_raw.py`.
- **Prévention** : un script cité dans la documentation est commité dans la même session.

## E-014 — Dépendances utilisées mais non déclarées (2026-09-21)

- **Contexte** : `pyyaml` à l'étape 3 (juillet), puis contrôle d'import des 35 modules lors de la remise en ordre.
- **Message d'erreur** : `ModuleNotFoundError` à l'import de 11 modules de `market_value/`.
- **Cause** : `pyyaml`, puis `pandas`, `numpy`, `scikit-learn`, `hdbscan` et `joblib` importés sans figurer dans `pyproject.toml`.
- **Solution** : `uv add` des paquets manquants.
- **Fichiers concernés** : `pyproject.toml`, `uv.lock`.
- **Prévention** : ajouter une dépendance avec `uv add` au moment où on l'importe ; la CI, qui part d'un environnement neuf, le signale dès qu'un test importe le module.

## E-016 — Dates décalées d'un jour entre Understat et football-data (2026-07-24)

- **Contexte** : ingestion Understat, après la fusion des 19 doublons (E-003).
- **Message d'erreur** : `2 lignes ignorées (match/team_match introuvable)`.
- **Cause** : fuseau horaire (UTC ou heure locale) avant troncature à la date, pour des matchs tardifs.
- **Solution** : tolérance de ±1 jour dans `resolve_match_cross_source()`. En 2026-09, 3 matchs restent non résolus (écart de plus d'un jour, probablement des reports).
- **Fichiers concernés** : `ingestion/common.py`.
- **Prévention** : la tolérance devient ambiguë si deux équipes se rencontrent deux fois à moins de 2 jours d'écart ; les coupes sont désormais collectées (ADR-0002). Règles actuelles : ADR-0008 (±1 jour) et ADR-0011 (sans date après le gel).
- **Test de non-régression** : `tests/ingestion/test_common.py` (`..._tolerates_one_day_offset`, `..._ambiguous_pair_within_two_days`).

## E-003 — 19 équipes en double après correction de YAML (2026-07-24)

- **Contexte** : ingestion Understat, 568 lignes ignorées sur 1 184.
- **Message d'erreur** : aucun, lignes ignorées silencieusement.
- **Cause** : `get_or_create_team` renvoie le mapping déjà enregistré sans relire le YAML ; une correction de YAML a donc créé une seconde équipe.
- **Solution** : script `scripts/one_off/fusion.py` (19 fusions, en base dev uniquement).
- **Fichiers concernés** : `ingestion/common.py`, `mappings/*.yaml`.
- **Prévention** : un taux de lignes ignorées élevé mérite un diagnostic avant d'avancer. Corriger un YAML ne répare jamais une entité déjà créée. Solution durable : référentiel par identifiants sources, reconstruit depuis le brut, sans correction manuelle en base (ADR-0008).
- **Test de non-régression** : tests de réconciliation dans `tests/ingestion/test_common.py`.

## E-015 — Schéma construit sur une source avant vérification de ses conditions d'utilisation (2026-07-21)

- **Contexte** : schéma de l'étape 2 conçu autour de Transfermarkt (compositions, valeurs marchandes).
- **Message d'erreur** : aucun ; erreur de méthode.
- **Cause** : CGU et `robots.txt` de Transfermarkt vérifiés après la conception ; ils interdisent le scraping. Les wrappers et jeux de données dérivés reposent sur le même scraping.
- **Solution** : tables Transfermarkt supprimées (migration `0003_market_value_score`), compositions prises dans API-FOOTBALL. Valeur marchande écartée définitivement (ADR-0013).
- **Prévention** : vérifier les CGU et le `robots.txt` d'une source **avant** d'écrire du code. Même cas ouvert : Understat (rapport B.4, D13 ; décision M17).

## E-013 — Organisation `src/` non déclarée dans `pyproject.toml` (juillet 2026, étapes 2 et 3)

- **Contexte** : premiers tests contre un vrai Postgres.
- **Cause** : le `pyproject.toml` généré par `uv init` ne déclarait pas le paquet sous `src/`.
- **Solution** : `[tool.hatch.build.targets.wheel] packages = ["src/foot_predictor"]`.
- **Fichiers concernés** : `pyproject.toml`.
- **Prévention** : tester contre un vrai Postgres et un environnement installé, pas seulement en test unitaire.

## E-012 — Identifiant de révision Alembic trop long (juillet 2026, étapes 2 et 3)

- **Contexte** : application des migrations.
- **Message d'erreur** : non consigné.
- **Cause** : l'identifiant dépassait la colonne `alembic_version.version_num` (`varchar(32)`).
- **Solution** : identifiant raccourci.
- **Fichiers concernés** : `migrations/versions/`.
- **Prévention** : identifiants courts du type `0004_referentiel` ; tester chaque migration sur la base de test.

## E-011 — Type enum Postgres créé deux fois (juillet 2026, étapes 2 et 3)

- **Contexte** : migration `0002_create_tables`.
- **Message d'erreur** : non consigné (le type existe déjà).
- **Cause** : l'enum était créé explicitement, puis une seconde fois automatiquement par `create_table`.
- **Solution** : création explicite retirée.
- **Fichiers concernés** : `migrations/versions/0002_create_tables.py`.
- **Prévention** : appliquer chaque migration sur une base vide (base de test) avant de la commiter.

## E-010 — `ModuleNotFoundError: No module named 'foot_predictor'` à `alembic upgrade head` (2026-07-18)

- **Contexte** : première migration.
- **Cause** : `prepend_sys_path = .` dans `alembic.ini`, alors que le paquet est sous `src/`.
- **Solution** : `prepend_sys_path = src` et `src/foot_predictor/__init__.py` présent.
- **Fichiers concernés** : `alembic.ini`.

## E-009 — `alembic init migrations` : `Directory already exists` (2026-07-18)

- **Contexte** : mise en place d'Alembic.
- **Cause** : dossier `migrations/versions/` créé à l'avance, vide.
- **Solution** : déplacer `versions/` hors de `migrations/`, lancer `alembic init`, puis le remettre.
- **Fichiers concernés** : `migrations/`.

## E-008 — `uv add` : `error: Project is missing a [project] table` (2026-07-18)

- **Contexte** : ajout des premières dépendances.
- **Cause** : `pyproject.toml` présent mais vide.
- **Solution** : supprimer le fichier, puis `uv init --no-readme`.
- **Fichiers concernés** : `pyproject.toml`.

## E-007 — SQLTools : connexion invisible, `Received null` sur le mot de passe (2026-07-18)

- **Contexte** : connexion aux bases depuis VSCode.
- **Cause** : connexions résiduelles dans les réglages VSCode (utilisateur **et** espace de travail) et identifiants en cache dans le Gestionnaire d'identifiants Windows.
- **Solution** : vider `sqltools.connections` dans les deux réglages, nettoyer le Gestionnaire d'identifiants, puis `Developer: Reload Window`.

## E-006 — `password authentication failed` persistant après réinitialisation du volume (2026-07-18)

- **Contexte** : remise à zéro de la base dev.
- **Cause** : le volume `pg_dev_data` n'était pas réellement supprimé avant `docker compose up`.
- **Solution** : `stop`, `rm -f`, `volume rm`, puis `up` ; vérifier `running bootstrap script` dans `docker logs`.
- **Prévention** : depuis la collecte, ne jamais supprimer de volume ni lancer `docker compose down -v` (CLAUDE.md).

## E-002 — `postgres_user Field required` malgré la variable présente (2026-07-18)

- **Contexte** : chargement de la configuration.
- **Message d'erreur** : `pydantic_core.ValidationError: postgres_user Field required`.
- **Cause** : fichier `.env` enregistré en UTF-8 **avec BOM**, qui corrompt le nom de la première variable.
- **Solution** : réenregistrer les `.env.*` en UTF-8 sans BOM.
- **Prévention** : environnement WSL2 envisagé (décision M13).

## E-001 — `password authentication failed` sur la base dev (2026-07-18)

- **Contexte** : connexion SQLTools et Python à Postgres.
- **Cause** : une installation Postgres native Windows occupait le port 5432.
- **Solution** : port dev déplacé sur 5440 dans `docker-compose.yml` et `.env.dev`.
- **Prévention** : désactiver le service Windows `postgresql-x64-XX` (droits administrateur). Diagnostic par élimination : arrêter le conteneur ; si l'erreur reste une erreur Postgres plutôt que `connection refused`, un autre serveur répond.
