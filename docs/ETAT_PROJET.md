# État du projet

**Dernière mise à jour** : 2026-10-22 (partie 3 terminée : jeu sur le brut définitif identique à `ba2b91f7`, tag `v0.4.0`)
**Partie courante** : les phases A des parties 1 à 5 sont faites (dernière : partie 5, inférence, API et interface ; `docs/retours/partie-5a_2026-10-04.md`). **Collecte terminée** : la session de gel du 19 octobre est faite (`docs/retours/partie-1b_2026-10-19.md`). **Parties 2 et 3 terminées** (tags `v0.3.0` et `v0.4.0` ; `docs/retours/partie-2_2026-10-19.md`, `docs/retours/partie-3_2026-10-22.md`). Les phases B des parties 4 et 5 se font sur demande, dans cet ordre.

**Reprise de la partie 4 à la phase B, sous-étape 4.16** (test scellé H1, **une seule fois**), puis 4.17 (entraînement final, tag `v0.5.0`), puis la partie 5 à la phase B (lot 4, 5.13 : ouverture du scellé), chacune seulement après la précédente ; commandes plus bas.
**Abonnement API-FOOTBALL** : terminé le **2026-10-22 à 07:56 UTC** (ADR-0005) ; plus aucune collecte.

## Terminé

- Cadrage, collecteur v2, collecte P1 à P4 ; partie 1 (PR #15 à #21) ; partie 2, phase A (PR #22 à #31) : référentiel reconstruit par `load`. **Partie 3, phase A** (PR #32 à #42, `docs/retours/partie-3a_2026-09-29.md`) : scellé et porte unique (ADR-0028), registre et jeu versionné (ADR-0030), variables (ADR-0029, 0031 à 0033), notebooks (ADR-0034).
- **Partie 4, phase A** (PR #43 à #58, `docs/retours/partie-4a_2026-09-30.md`) : tirs d'API-FOOTBALL et jeu **`ds-2026-09-30-ba2b91f7`** (ADR-0035) ; cotes (migration 0007, ADR-0036) ; protocole figé (ADR-0037, tag `protocole-v1`) ; structure M3 (ADR-0038) ; **modèle MVP H1 : M3 sur G0 + G1 + G2, top 5** (ADR-0039), +0,0179 [+0,0133 ; +0,0226] sur B1 ; code du test scellé, **tag `pre-scelle-h1`**.
- **Partie 5, lot 1** (2026-09-30, PR #59 à #64, `docs/retours/partie-5-lot1_2026-09-30.md`) : architecture (ADR-0040), groupes `api` et `ui` ; `inference/` : variables par la fonction de l'entraînement (622 lignes identiques au bit près), modèles de rejeu par pli (écart nul avec l'évaluation), disponibilité et prédiction, **migration 0008** (`ops.prediction`, `ops.model_registry`).
- **Partie 5, lot 2** (2026-10-01, PR #65 à #67, `docs/retours/partie-5-lot2_2026-10-01.md`) : **API FastAPI locale** (`api/`, 7 routes) ; **tirs de football-data en live** : écart de log-loss −0,00002 [−0,00021 ; +0,00018], non significatif, pas de recalibration (ADR-0041).
- **Partie 5, lot 3** (2026-10-04, PR #68 à #71, `docs/retours/partie-5a_2026-10-04.md`) : **interface Streamlit** (`ui/`, 3 écrans, par l'API seulement) ; **football-data en live**, superposé en mémoire (ADR-0042 ; répétition 2023-24 : 335 résultats sur 335, buts et Elo identiques) ; **bout en bout** en CI (brut → `load` → API → interface → `ops.prediction`) ; chapitre LaTeX « Inférence et disponibilité ».

- **Gel des données** (2026-10-19, PR #73, tag `data-freeze-2026-10` sur `8144bbc`, `docs/DATA_FREEZE.md`) : **17 336 fichiers** (306 Mo) vérifiés dans le brut, la sauvegarde sur `D:` et la restauration ; 102 554 matchs terminés, tous avec détail ; `raw_check` À REGARDER sans point bloquant ; dernier `refresh` : 70 requêtes ; bilan T-60 : 91 matchs, 99,95 % de titulaires identiques (sous le critère de 2 %). 9 tâches planifiées supprimées ; `C:/foot-predictor` à jour sur `main`.
- **Partie 2, phase B, 2.10** (2026-10-19, PR #76 ; chiffres dans `docs/realisation/04_referentiel/README.md`, « Résultats de 2.10 ») :
  - **`load` n° 6** sur le brut définitif : 493 s, 167 980 matchs (+104, tours de coupe) ;
  - `check-referentiel` : appariement football-data 99,98 % (seuil 99,5 %), identité des joueurs OK, top 5 : 0,14 % de matchs avec exclusion (seuil 1 %) ;
  - **CSV football-data recopiés** dans `C:/foot-predictor/data/raw` : 17 607 fichiers vérifiés, 0 écart ; le dossier du worktree reste celui du live et de `--external-raw-dir` ;
  - **Constat E-058** : les identifiants internes de `staging` changent quand le brut grandit (équipes, joueurs, matchs « hors_api ») ; `ops.prediction` n'a pas d'`api_fixture_id`.
- **Partie 2, phase B, 2.11** (2026-10-19, PR #77 ; « Résultats de 2.11 » dans le même README) :
  - chemins gelés jusqu'au gel (`collect/api_football/`, `rawstore/`, `raw_check`, tâches planifiées et leurs tests) **sous ruff et pre-commit** : 38 corrections, formatage de 37 fichiers à AST identique ; seules les migrations 0001 à 0003 restent exclues ;
  - **`raw_check` appelle `ingestion/collisions.py`** (ADR-0020) : sur le brut définitif, résumé et détails identiques octet pour octet hors en-tête ;
  - **E-036** (`test_freeze` intermittent) et **E-052** (`download.py` sans `www`) corrigés.
- **Partie 2, phase B, 2.12** (2026-10-19, PR #78, `docs/retours/partie-2_2026-10-19.md`) : **`load` n° 7** sur le même brut, avec le code de la PR #77 : 15 empreintes sur 15 identiques au n° 6 ; jalon J3 tenu sur le brut définitif ; **tag `v0.3.0`** sur la fusion de la PR #78.
- **Partie 3, phase B, 3.11** (2026-10-22, PR #79, `docs/retours/partie-3_2026-10-22.md` ; chiffres dans `docs/realisation/06_variables/README.md`, « Résultats de 3.11 ») :
  - `build` sur le chargement n° 7 : **`ds-2026-10-22-bf786ef1`**, 196 098 lignes ; `check --invariance` OK aux deux dates de coupe ;
  - comparée par identifiants API à `ba2b91f7` : **196 098 lignes sur 196 098, même ordre, 0 écart** sur les 65 colonnes ; seuls `match_id` (« hors_api ») et `team_id` diffèrent, jamais dans le top 5 depuis 2015-16 ; jalon J4 tenu, **tag `v0.4.0`** sur la fusion de la PR #79 ;
  - point 0 : `C:/foot-predictor` remis sur `main` ; `C:/fp_restauration/` absent ; décisions d'E-058 (voir « Points de vigilance »).

## En cours

- Rien. Aucune tâche planifiée ni collecte automatique.

## Bloqué

- Rien. Points de vigilance :
  - `lock-status` (avec `--raw-dir C:/foot-predictor/data/raw` depuis le worktree) avant chaque `git pull` dans `C:/foot-predictor` ; **jamais de `load` si le verrou est occupé** ; `load` dure de 6 à 13 minutes (377 s pour le chargement n° 7, 493 s pour le n° 6, 778 s pour le n° 5) ;
  - **identifiants internes non stables d'un brut à l'autre** (E-058). Décidé le 2026-10-22 :
    - passer `api_fixture_id` à `save_prediction` au lot 4 de la partie 5, avant 5.14, avec un test ;
    - garder telles quelles les 78 lignes de rejeu d'`ops.prediction` ;
    - pointer `inference check --only rows` sur un jeu du `staging` courant (`ds-2026-10-22-bf786ef1` ou plus récent) avant de le relancer : avec `ba2b91f7`, 1 jour sur 17 aurait un écart de clés ;
  - **chemins figés par `pre-scelle-h1`** (`modeling/`, `features/`, `seal.py`, `experiments/`, `tests/modeling`, `tests/features`) jusqu'à la fin du test scellé : on les importe, on ne les modifie pas ;
  - **scellé** : aucune valeur d'un match joué à partir du 1er juillet 2025 ; lecture des matchs par `features/sources.py` seulement ;
  - **disque externe `D:`** : invisible un moment après le gel, revenu et recompté (E-056) : 17 336 fichiers et journal au sha256 attendu. Copies facultatives faites le 19 octobre (E-031), sha256 identiques : `D:/foot-predictor/copies-2026-10-19/` (`fp_dumps/` et `football_data/`) ;
  - Docker Desktop doit tourner (bases arrêtées sinon, E-050) : `docker ps` en début de session.

## Décisions ouvertes

- **Renouvellement automatique de l'abonnement : coupé par l'utilisateur le 2026-10-19** (déclaré, non vérifiable par l'assistant ; fin de l'abonnement le 22 octobre à 07:56 UTC, ADR-0005). Conditions de football-data relues le 2026-10-04 et citées (ADR-0042) : interprétation à relire. Rapport : décisions 16, 18, 20 à 22.

## Prochaines actions

**Reprise de la partie 4 à la phase B, sous-étape 4.16** (sur demande ; parties 2 et 3 terminées, tags `v0.3.0` et `v0.4.0`) :
```bash
cd /c/fp-travail && git fetch origin --tags && git switch --detach origin/main && uv sync --all-groups
docker ps                                                          # deux conteneurs « Up » (E-050)
git tag -l data-freeze-2026-10 v0.3.0 v0.4.0 pre-scelle-h1        # les quatre tags doivent exister
uv run python -m foot_predictor.collect.api_football --raw-dir C:/foot-predictor/data/raw lock-status   # libre
git diff --stat pre-scelle-h1..HEAD -- src/foot_predictor/modeling src/foot_predictor/features src/foot_predictor/seal.py experiments tests/modeling tests/features   # VIDE, sinon s'arrêter
git switch --no-track -c data/10-test-scelle-h1 origin/main
uv run python -m foot_predictor.features build --sealed-test --experiment experiments/scelle_h1.yaml   # 1 ligne au journal
uv run python -m foot_predictor.modeling evaluate experiments/scelle_h1.yaml --sealed-test --dataset <version de data/datasets_scelles/>
# UNE seule fois ; résultat tel quel dans docs/resultats/test_scelle_h1.md ; en cas d'erreur technique : ne pas relancer, écrire et s'arrêter
git switch --no-track -c feat/10-modele-final origin/main   # 4.17, après fusion de 4.16
uv run python -m foot_predictor.modeling train --final experiments/scelle_h1.yaml --model M3_G0G2 --include-sealed     --dataset <version scellée> --validation-report reports/experiments/<rapport du test scellé>.json
# ADR de clôture, tag v0.5.0, retour docs/retours/partie-4_<date>.md
```

**Reprise de la partie 5 à la phase B** (lots 4 et 5, sur demande, après `v0.5.0`) :
```bash
cd /c/fp-travail && git fetch origin --tags && git switch --detach origin/main && uv sync --all-groups
docker ps ; uv run alembic current        # deux conteneurs « Up » (E-050) ; 0008
git tag -l data-freeze-2026-10 v0.3.0 v0.4.0 v0.5.0     # les quatre tags, sinon s'arrêter
grep scelle_h1.yaml reports/sealed_tests.md ; uv run python -m foot_predictor.inference models   # test terminé ; modèle ...-avec-scelle
uv run python -m foot_predictor.collect.api_football --raw-dir C:/foot-predictor/data/raw lock-status   # libre
git switch --no-track -c feat/11-ouverture-scelle origin/main      # 5.13
# lot 4, avant 5.14 (E-058) : api_fixture_id passé à save_prediction, avec un test ;
#   inference check --only rows sur un jeu du staging courant (ds-2026-10-22-bf786ef1 ou plus récent)
# 5.14 (live réel ; plafond écrit dans la PR) :
uv run python -m foot_predictor.collect.football_data.live fixtures --max-requests 1
uv run python -m foot_predictor.collect.football_data.live season --season 2026 --max-requests 10
```

**Long terme** : fin de la partie 5, `v1.0.0` (J7, J8) ; 6. version intermédiaire (J9).
