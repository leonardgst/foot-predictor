# État du projet

**Dernière mise à jour** : 2026-10-19 (gel des données fait, tag `data-freeze-2026-10`)
**Partie courante** : les phases A des parties 1 à 5 sont faites (dernière : partie 5, inférence, API et interface ; `docs/retours/partie-5a_2026-10-04.md`). **Collecte terminée** : la session de gel du 19 octobre est faite (`docs/retours/partie-1b_2026-10-19.md`). Les phases B des parties 2 à 5 se font sur demande, dans cet ordre.

**Reprise de la partie 2 à la phase B, sous-étape 2.10** (`load` sur le brut définitif), puis 3.11, 4.16, 4.17, puis la partie 5 à la phase B (lot 4, 5.13 : ouverture du scellé), chacune seulement après la précédente (tags `v0.3.0`, `v0.4.0`, `v0.5.0`) ; commandes plus bas.
**Échéance** : fin de l'abonnement API-FOOTBALL le **2026-10-22 à 07:56 UTC**. Marge de recollecte jusqu'au 21 au soir ; plus rien à collecter, sauf décision contraire (ADR-0005).

## Terminé

- Cadrage, collecteur v2, collecte P1 à P4 ; partie 1 (PR #15 à #21) ; partie 2, phase A (PR #22 à #31) : référentiel reconstruit par `load`. **Partie 3, phase A** (PR #32 à #42, `docs/retours/partie-3a_2026-09-29.md`) : scellé et porte unique (ADR-0028), registre et jeu versionné (ADR-0030), variables (ADR-0029, 0031 à 0033), notebooks (ADR-0034).
- **Partie 4, phase A** (PR #43 à #58, `docs/retours/partie-4a_2026-09-30.md`) : tirs d'API-FOOTBALL et jeu **`ds-2026-09-30-ba2b91f7`** (ADR-0035) ; cotes (migration 0007, ADR-0036) ; protocole figé (ADR-0037, tag `protocole-v1`) ; structure M3 (ADR-0038) ; **modèle MVP H1 : M3 sur G0 + G1 + G2, top 5** (ADR-0039), +0,0179 [+0,0133 ; +0,0226] sur B1 ; code du test scellé, **tag `pre-scelle-h1`**.
- **Partie 5, lot 1** (2026-09-30, PR #59 à #64, `docs/retours/partie-5-lot1_2026-09-30.md`) : architecture (ADR-0040), groupes `api` et `ui` ; `inference/` : variables par la fonction de l'entraînement (622 lignes identiques au bit près), modèles de rejeu par pli (écart nul avec l'évaluation), disponibilité et prédiction, **migration 0008** (`ops.prediction`, `ops.model_registry`).
- **Partie 5, lot 2** (2026-10-01, PR #65 à #67, `docs/retours/partie-5-lot2_2026-10-01.md`) : **API FastAPI locale** (`api/`, 7 routes) ; **tirs de football-data en live** : écart de log-loss −0,00002 [−0,00021 ; +0,00018], non significatif, pas de recalibration (ADR-0041).
- **Partie 5, lot 3** (2026-10-04, PR #68 à #71, `docs/retours/partie-5a_2026-10-04.md`) : **interface Streamlit** (`ui/`, 3 écrans, par l'API seulement) ; **football-data en live**, superposé en mémoire (ADR-0042 ; répétition 2023-24 : 335 résultats sur 335, buts et Elo identiques) ; **bout en bout** en CI (brut → `load` → API → interface → `ops.prediction`) ; chapitre LaTeX « Inférence et disponibilité ».

- **Gel des données** (2026-10-19, PR #73, tag `data-freeze-2026-10` sur `8144bbc`, `docs/DATA_FREEZE.md`) : **17 336 fichiers** (306 Mo) vérifiés dans le brut, la sauvegarde sur `D:` et la restauration ; 102 554 matchs terminés, tous avec détail ; `raw_check` À REGARDER sans point bloquant ; dernier `refresh` : 70 requêtes ; bilan T-60 : 91 matchs, 99,95 % de titulaires identiques (sous le critère de 2 %). 9 tâches planifiées supprimées ; `C:/foot-predictor` à jour sur `main`.

## En cours

- Rien. Aucune tâche planifiée ni collecte automatique.

## Bloqué

- Rien. Points de vigilance :
  - `lock-status` avant chaque `git pull` dans `C:/foot-predictor` ; **jamais de `load` si le verrou est occupé** ; `load` dure environ 13 minutes (778 s, chargement n° 5) ;
  - **chemins figés par `pre-scelle-h1`** (`modeling/`, `features/`, `seal.py`, `experiments/`, `tests/modeling`, `tests/features`) jusqu'à la fin du test scellé : on les importe, on ne les modifie pas ;
  - **scellé** : aucune valeur d'un match joué à partir du 1er juillet 2025 ; lecture des matchs par `features/sources.py` seulement ;
  - **disque externe `D:`** : invisible un moment après le gel, revenu et recompté (E-056) : 17 336 fichiers et journal au sha256 attendu. Copies facultatives faites le 19 octobre (E-031), sha256 identiques : `D:/foot-predictor/copies-2026-10-19/` (`fp_dumps/` et `football_data/`) ;
  - `C:/fp_restauration/` (copie de test) à supprimer par l'utilisateur ;
  - Docker Desktop doit tourner (bases arrêtées sinon, E-050) : `docker ps` en début de session.

## Décisions ouvertes

- **Renouvellement automatique de l'abonnement : coupé par l'utilisateur le 2026-10-19** (déclaré, non vérifiable par l'assistant ; fin de l'abonnement le 22 octobre à 07:56 UTC, ADR-0005). Conditions de football-data relues le 2026-10-04 et citées (ADR-0042) : interprétation à relire. Rapport : décisions 16, 18, 20 à 22.

## Prochaines actions

**Reprise de la partie 2 à la phase B, sous-étape 2.10** : `load` sur le brut définitif et recopie des CSV, puis 2.11 (chemins gelés, dont E-036), 2.12 (tag `v0.3.0`). Commandes : `docs/realisation/04_referentiel/README.md`, section « Phase B ».
```bash
cd /c/fp-travail && git fetch origin --tags && git switch --detach origin/main && uv sync --all-groups
git tag -l data-freeze-2026-10 ; docker ps                       # tag présent ; deux conteneurs « Up » (E-050)
uv run python -m foot_predictor.collect.api_football lock-status   # libre, avant tout load
```

**Reprise de la partie 3 à la phase B après la session de gel et la phase B de la partie 2** (3.11, sur demande) :
```bash
cd /c/fp-travail && git fetch origin --tags && git switch --detach origin/main && uv sync --all-groups
git tag -l v0.3.0                                          # phase B de la partie 2 faite
uv run python -m foot_predictor.features build             # nouveau staging (brut définitif)
uv run python -m foot_predictor.features check --invariance
# comparer (matchs d'avant le 2025-07-01) les lignes de la nouvelle version à ds-2026-09-30-ba2b91f7 (ADR-0035)
# puis tag v0.4.0, ETAT_PROJET.md, docs/retours/partie-3_<date>.md
```

**Reprise de la partie 4 à la phase B** (après le gel, `v0.3.0` et `v0.4.0` ; sur demande) :
```bash
cd /c/fp-travail && git fetch origin --tags && git switch --detach origin/main && uv sync --all-groups
git tag -l data-freeze-2026-10 v0.3.0 v0.4.0 pre-scelle-h1        # les quatre tags doivent exister
uv run python -m foot_predictor.collect.api_football lock-status   # libre
git diff --stat pre-scelle-h1..HEAD -- src/foot_predictor/modeling src/foot_predictor/features experiments   # VIDE, sinon s'arrêter
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
uv run python -m foot_predictor.collect.api_football lock-status   # libre
git switch --no-track -c feat/11-ouverture-scelle origin/main      # 5.13
# 5.14 (live réel ; plafond écrit dans la PR) :
uv run python -m foot_predictor.collect.football_data.live fixtures --max-requests 1
uv run python -m foot_predictor.collect.football_data.live season --season 2026 --max-requests 10
```

**Long terme** : fin de la partie 5, `v1.0.0` (J7, J8) ; 6. version intermédiaire (J9).
