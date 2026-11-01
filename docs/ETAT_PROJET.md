# État du projet

**Dernière mise à jour** : 2026-11-01 (6.5 : jeu de données H2)
**Partie courante** : les phases A des parties 1 à 5 sont faites (dernière : partie 5, inférence, API et interface ; `docs/retours/partie-5a_2026-10-04.md`). **Collecte terminée** : la session de gel du 19 octobre est faite (`docs/retours/partie-1b_2026-10-19.md`). **Parties 2, 3 et 4 terminées** (tags `v0.3.0`, `v0.4.0` et `v0.5.0` ; `docs/retours/partie-2_2026-10-19.md`, `partie-3_2026-10-22.md`, `partie-4_2026-10-22.md`). **Partie 5 terminée** (tags `v0.6.0` et `v1.0.0` ; `docs/retours/partie-5_2026-10-31.md`) : **le MVP est terminé**.

**Reprise : partie 6, version intermédiaire (J9)** : 6.6, exploration H2 en notebook (`docs/07-exploration-h2`) sur le jeu `ds-2026-11-01-94e07897` : distributions, début de saison, corrélations entre variantes de cohésion et avec les habituels absents (−0,85 avec la cohésion h5), lues par `load_dataset`. Aucun autre test ni entraînement final H1 ; aucun modèle H1 ne se modifie.
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
- **Partie 4, phase B, 4.16 : test scellé H1** (2026-10-22, PR #80 à #82, `docs/resultats/test_scelle_h1.md`) :
  - jeu scellé `ds-2026-10-22-94969da0` (205 216 lignes, dont 9 118 scellées) ; premier `evaluate --sealed-test` en **échec technique**, sans résultat (E-059) ;
  - **ADR-0043**, relance unique par `foot_predictor.sealed_rerun` (PR #81), faite à 12:05 UTC : rapport `scelle-h1-20261022T120542`, sha256 des prédictions identique au premier lancement ;
  - **le modèle retenu bat B1 sur les matchs scellés** : +0,0189 [+0,0102 ; +0,0282] de log-loss du total, sur 2 092 matchs (validation glissante : +0,0179) ; couverture de [q10 ; q90] à 0,2 point de l'annoncée ; pente de calibration 1,00. Le marché avant clôture reste meilleur sur plus/moins 2,5 ;
  - **E-060** : la ligne « règle de décision » des tableaux (« ne remplace pas B1 ») n'a pas de sens sur un pli unique. Elle est publiée telle quelle et expliquée ; **corrigé le 2026-10-31** (PR #92) : « non applicable » sous 3 plis, tableaux des rapports à 4 plis identiques octet pour octet.
- **Partie 4, phase B, 4.17 : modèle final H1** (2026-10-22, PR #83, **ADR-0044**, `docs/retours/partie-4_2026-10-22.md`) :
  - `train --final --include-sealed` sur `94969da0` : **`scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle`**, 40 180 lignes jusqu'au 2026-10-18, demi-vie 240 jours ; carte dans `reports/model_cards/` ;
  - demi-vie validée par la procédure figée sur le début de 2026-27 (341 matchs), choix de l'utilisateur avant le lancement ; coefficients à 0,009 au plus de ceux du modèle sans scellé ;
  - **E-061** : `dirty: true` à tort dans la carte et dans le manifeste de `94969da0` (journal écrit avant la lecture de l'état Git ; **corrigé dans le code le 2026-10-31**, PR #93) ; jalon J6 atteint, **tag `v0.5.0`** sur la fusion de la PR #83.
- **Partie 5, phase B, 5.13 : ouverture du scellé** (2026-10-22, PR #84, **ADR-0045** ; « Ouverture du scellé » dans `docs/realisation/11_inference/README.md`) :
  - porte : `load_matches(opened_for_inference=True)`, refusée avant le test H1, sans ligne de journal, réservée à `inference/` (test d'architecture) ; développement et cotes fermés jusqu'au test de H2 ;
  - live : historique complet ; **rejeu des saisons scellées fermé jusqu'au test de H2** (choix de l'utilisateur) ; modèle final actif dans `ops.model_registry` (`models --activate`) ;
  - réel : 434 lignes de la période scellée identiques au bit près au jeu `94969da0` (8 jours) ; rejeu de 2021-22 à 2024-25 inchangé ; live du 2026-10-24 : top 5 « périmé » jusqu'à 5.14.
- **Partie 5, phase B, 5.14 : live réel** (2026-10-22, PR #86 ; « Live réel » dans `docs/realisation/11_inference/README.md`) :
  - football-data superposé au contexte d'inférence (API, `predict`, nouvelle commande `live --days N [--save]` et son rapport) ; contexte de l'API reconstruit par clé (chargement, fichiers, jour) ; cote avant clôture des matchs à venir ;
  - collecte : 11 requêtes (accord de l'utilisateur, plafonds 1 + 10), 0 ligne inutilisable (promus dans le YAML) ; **56 matchs du top 5 sur 7 jours, 91 % « périmés »** ;
  - **5 prédictions live tracées** (23 octobre, avant le coup d'envoi) : début du journal prospectif ; **E-062** : une réponse live indisponible n'est plus jamais écrite.
- **Partie 5, phase B, fraîcheur par équipe** (2026-10-22, PR #87, **ADR-0046**) : règle **approchée** choisie par l'utilisateur après mesure (E-063 : l'exactitude d'abord annoncée était fausse, à cause de l'a priori μ des glissants) ; tolérance 0,005 sur λ et 0,002 sur P(T > 2,5) ; répétition conforme (Elo identique, écart maximal 0,0005 sur λ) ; live : **14 % d'indisponibles**, **48 prédictions live tracées** (journée du 23 au 26 octobre, `ops.prediction` : 131 lignes).
- **Partie 5, phase B, 5.15 : bout en bout réel** (2026-10-31, PR #88, `docs/retours/partie-5-lot4_2026-10-31.md` ; chiffres dans `docs/realisation/14_tests_bout_en_bout/README.md`, section 3) :
  - collecte football-data : 11 requêtes (accord de l'utilisateur) ; live sur 7 jours : 48 matchs du top 5, **43 disponibles, 10 % d'indisponibles** ; **41 prédictions live tracées** avant le coup d'envoi, 2 refusées (matchs commencés) ; `ops.prediction` : 89 lignes live, 83 de rejeu ;
  - API et interface sur la vraie base, en rejeu (18/05/2025) et en live (31/10/2026) : une prédiction s'affiche, 403 pour un jour passé en live et pour les saisons scellées en rejeu ; API sur le port 8001 (**E-064** : 8000 tenu par le relais de WSL) ;
  - **critères E.1** : 1, 2, 4 et 5 remplis ; 3 en diagnostic publié tel quel (scellé : 5 déciles sur 10 sous 3 points, pente 1,00, ADR-0037) ; 6 rempli pour la documentation, rapport LaTeX v1 en 5.16. Aucun `load` (choix de l'utilisateur : preuves de 2.12 et 3.11). **Tag `v0.6.0`** sur la fusion de la PR #88.
- **Partie 5, phase B, 5.16 : documents LaTeX** (2026-10-31, PR #89 et #90 ; `docs/realisation/16_documentation_finale/README.md`) : document mathématique à jour (ADR-0044 à ADR-0046) ; **rapport v1** (`docs/latex/rapport/`, 8 chapitres et annexes, 11 références vérifiées par l'utilisateur) ; Overleaf (ADR-0034 inchangée), **compilés sans erreur** (utilisateur).
- **Partie 5, phase B, 5.17 : clôture** (2026-10-31, PR #91, `docs/retours/partie-5_2026-10-31.md`) : jalons J7 et J8 atteints, critère 6 d'E.1 rempli ; **tag `v1.0.0`** sur la fusion de la PR #91.
- **Partie 5, phase B, E-058 corrigé** (2026-10-22, PR #85) : `api_fixture_id` porté par la réponse et recopié par `save_prediction` (API et commande) ; `check --only rows` sur `ds-2026-10-22-bf786ef1`, même chargement n° 7 vérifié : 622 lignes identiques au bit près ; 5 prédictions de rejeu réelles tracées avec leur identifiant API (`ops.prediction` : 83 lignes).

## En cours

- Rien. Aucune tâche planifiée ni collecte automatique.

## Bloqué

- Rien.
- Points de vigilance :
  - `lock-status` (avec `--raw-dir C:/foot-predictor/data/raw` depuis le worktree) avant chaque `git pull` dans `C:/foot-predictor` ; **jamais de `load` si le verrou est occupé** ; `load` dure de 6 à 13 minutes (377 s pour le chargement n° 7, 493 s pour le n° 6, 778 s pour le n° 5) ;
  - **identifiants internes non stables d'un brut à l'autre** (E-058, corrigé par la PR #85) : hors de `staging`, rapprocher par l'identifiant API ; les 78 premières lignes d'`ops.prediction` restent sans identifiant API ; un nouveau `load` sur un brut plus grand demanderait un nouveau jeu pour `check --only rows` ;
  - **fin du gel de `pre-scelle-h1`** avec la fusion de la PR #83 (ADR-0044) : les chemins figés se modifient de nouveau par PR (E-060 et E-061 faits). Garde : une PR qui touche `modeling/models/` montre que les prédictions du modèle final H1 sont inchangées ;
  - **scellé** : aucune valeur d'un match joué à partir du 1er juillet 2025 ; lecture des matchs par `features/sources.py` seulement ; ouvert à `inference/` seulement (ADR-0045), jamais au développement de H2 ;
  - **disque externe `D:`** : invisible un moment après le gel, revenu et recompté (E-056) : 17 336 fichiers et journal au sha256 attendu. Copies facultatives faites le 19 octobre (E-031), sha256 identiques : `D:/foot-predictor/copies-2026-10-19/` (`fp_dumps/` et `football_data/`). **Copies du 2026-10-31** (décision du 22 octobre) : jeu scellé `ds-2026-10-22-94969da0` et modèle final H1, 4 fichiers, sha256 identiques à `C:`, dans `D:/foot-predictor/copies-2026-10-22/` (`datasets_scelles/`, `models/`) ;
  - Docker Desktop doit tourner (bases arrêtées sinon, E-050) : `docker ps` en début de session ;
  - **port 8000 tenu par le relais de WSL** (E-064) : API sur `--port 8001`, interface avec `FP_API_URL=http://127.0.0.1:8001` ;
  - live : collecter le vendredi soir ou le samedi matin ; le 2026-10-31 à 13:03 UTC, 2 matchs étaient déjà commencés.

## Décisions ouvertes

- **Renouvellement automatique de l'abonnement : coupé par l'utilisateur le 2026-10-19** (déclaré, non vérifiable par l'assistant ; fin de l'abonnement le 22 octobre à 07:56 UTC, ADR-0005). Conditions de football-data relues le 2026-10-04 et citées (ADR-0042) : interprétation à relire. Rapport : décisions 16, 18, 20 à 22.

## Prochaines actions

**Corrections reportées faites** : E-060 (PR #92), E-061 (PR #93), E-065 (`test_freeze`, PR #94). **6.0 fait** (PR #95) : cadrage de H2, ADR-0047 acceptée (D1 à D10 selon les recommandations). D10 fait (PR #96). **6.1 fait** : `load_lineups` et `load_team_sheets` (porte), groupes G4 à G6 à l'horizon H2 au registre, garde « modèle H1 sans variable H2 » dans `build_card` ; H1 inchangé (rejeu : écart nul ; coefficients identiques). **6.2 fait** : `features/lineup_stability.py` (G6 : `xi_overlap_prev`, `xi_cohesion_ewm_h3/5/10/20/inf`, `xi_new_starters`), égalité matrice = recouvrement testée, invariance à la troncature sans écart sur données réelles, 0 % de valeurs vides sur les plis ; texte du catalogue déduit du registre. **6.3 fait** : `features/xi_quality.py` (G5 : `xi_quality` rétrécie vers la moyenne du poste avec k = 772,6 minutes estimé sur 2015-16 à 2019-20, `xi_regulars_missing`, `xi_mean_age`), 0,15 % de `xi_quality` vide sur les plis, invariance à la troncature sans écart, calcul vérifié contre un calcul naïf ; D9 : 0,3 % de titulaires sans note antérieure, variante corrigée non déclenchée ; **les habituels absents sont corrélés à −0,85 avec la cohésion G6** (à regarder en 6.6). **6.4 fait** : `features/coach.py` (G4 : `coach_tenure_days` plafonnée à 365 jours, `coach_is_new` à moins de 5 matchs ; période ininterrompue du même entraîneur, entraîneur inconnu laissé vide), 0,08 % de valeurs vides sur les plis, invariance à la troncature sans écart, 300 lignes vérifiées par un calcul naïf ; censure à gauche de 2016-17 mesurée (19,5 % de « nouveaux » contre 10 %), d'où l'apprentissage dès 2017-18. **6.5 fait** : fiches G4 à G6 au registre (24 colonnes, 68 → 92), `build_frame_h2` (jeu H1 inchangé), `features build --horizon H2` (45 s), `check` selon l'horizon du manifeste ; jeu **`ds-2026-11-01-94e07897`**, colonnes H1 identiques au bit près à `bf786ef1`, invariance à la troncature sans écart sur les 92 colonnes, 0,46 % de lignes incomplètes sur les plis. À faire en 6.9 : `modeling/sealed.py` fixe le tag `pre-scelle-h1` (`FROZEN_TAG`), à généraliser pour le test H2.

**Reprise** (partie 6 ou live courant, sur demande) :
```bash
cd /c/fp-travail && git fetch origin --tags && git switch --detach origin/main && uv sync --all-groups
docker ps ; uv run alembic current        # deux conteneurs « Up » (E-050) ; 0008
git tag -l data-freeze-2026-10 v0.5.0 v0.6.0 v1.0.0     # les quatre tags, sinon s'arrêter
uv run python -m foot_predictor.inference models     # actif : scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle (5.13)
uv run python -m foot_predictor.collect.api_football --raw-dir C:/foot-predictor/data/raw lock-status   # libre
# live courant (accord de l'utilisateur pour chaque collecte ; fichier des prochains matchs : vendredi après-midi et mardi)
uv run python -m foot_predictor.collect.football_data.live fixtures --max-requests 1
uv run python -m foot_predictor.collect.football_data.live season --season 2026 --max-requests 10
uv run python -m foot_predictor.inference live --days 7 --save     # rapport + prédictions disponibles tracées
# services (E-064 : port 8000 pris par WSL)
uv run python -m foot_predictor.api serve --port 8001
FP_API_URL=http://127.0.0.1:8001 uv run streamlit run src/foot_predictor/ui/app.py
```

**Partie 6** (plan du cadrage, section 8, environ 118 heures) : 6.1 porte des compositions et registre H2 ; 6.2 à 6.4 variables G6, G5, G4 (faites) ; 6.5 jeu H2 (fait ; colonnes H1 identiques à `bf786ef1`) ; 6.6 à 6.8 exploration et expériences ; 6.9 modèle H2 et tag `pre-scelle-h2` ; 6.10 H2 en rejeu ; phase B : test scellé H2, ouverture du rejeu des saisons scellées, rapport v2 (jalon J9).
