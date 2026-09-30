# État du projet

**Dernière mise à jour** : 2026-09-30 (fin de la partie 4, phase A)
**Partie courante** : 4/6, protocole, références et modèle MVP (J5, J6). **Phase A faite** (lots 1 à 3) ; la **phase B** (test scellé, entraînement final) reprend après la session de gel du **lundi 19 octobre** et les phases B des parties 2 et 3, sur demande.

**Reprise de la partie 4 à la phase B** (4.16 puis 4.17), après les préconditions ci-dessous ; lire d'abord `docs/retours/partie-4a_2026-09-30.md`.
**Échéance dure** : fin de l'abonnement API-FOOTBALL le **2026-10-22 à 07:56 UTC** ; gel le 19, marge les 20 et 21 (ADR-0005).

## Terminé

- Cadrage, collecteur v2, collecte P1 à P4 ; partie 1 (PR #15 à #21) ; partie 2, phase A (PR #22 à #31) : référentiel reconstruit par `load`.
- **Partie 3, phase A** (PR #32 à #42, `docs/retours/partie-3a_2026-09-29.md`) : scellé technique et porte unique (ADR-0028), tirs de football-data (ADR-0029), registre et jeu versionné (ADR-0030), Elo (ADR-0031), glissants et `xg_proxy` (ADR-0032), calendrier et huis clos (ADR-0033), notebooks et LaTeX (ADR-0034).
- **Partie 4, lot 1** (2026-09-30, PR #43 à #49, `docs/retours/partie-4-lot1_2026-09-30.md`) :
  - tirs d'API-FOOTBALL depuis 2015-16 quand elle est complète, `xg_proxy` = 0,3076 · tirs cadrés, jeu **`ds-2026-09-30-ba2b91f7`** (ADR-0035) ;
  - cotes plus/moins 2,5 dans `staging.match_odds` (migration 0007, `ops.load_run` n° 5), référence de marché (ADR-0036) ;
  - `modeling/` : métriques, protocole, bootstrap par blocs, exécuteur d'expériences, anciens modules dans `modeling/legacy/` ;
  - **protocole et règle de décision figés** (ADR-0037, tag `protocole-v1`) ;
  - références : B1 bat B0 de +0,0046 [+0,0010 ; +0,0080] en log-loss du total ; le marché bat B1 de +0,0091 en Brier de P(T > 2,5) (`docs/resultats/references.md`).
- **Partie 4, lot 2** (PR #50 à #54) : M1 à M6 sur G0 + G1 ; **structure retenue : M3, Poisson par équipe** (ADR-0038) ; NB, Dixon-Coles et régularisation sans gain.
- **Partie 4, lot 3** (PR #55 à #58, `docs/retours/partie-4a_2026-09-30.md`) : ablations (G1 +0,0094, G2 +0,0092, G3 et D2 sans gain, `docs/resultats/ablations.md`) ; **modèle MVP H1 : M3 sur G0 + G1 + G2, top 5** (ADR-0039), qui bat B1 de +0,0179 [+0,0133 ; +0,0226] ; carte d'identité (`reports/model_cards/`) ; code du test scellé ; **tag `pre-scelle-h1`**.

## En cours

- Collecte automatique par tâches planifiées jusqu'au 18 octobre. Aucune commande à lancer à la main avant le 19.

## Bloqué

- Rien. Points de vigilance :
  - **aucun `git pull` dans `C:/foot-predictor` avant l'étape 7 du gel** (ADR-0021) ; ensuite, `lock-status` avant chaque `git pull` ;
  - portable **allumé, branché, capot ouvert, session ouverte** aux dates des tâches ;
  - **jamais de `load` pendant une tâche** (lundis 5 et 12 octobre de 07:45 à 11:00, ou verrou occupé) ; `load` dure désormais environ 13 minutes (778 s, chargement n° 5) ;
  - **scellé** : aucune valeur d'un match joué à partir du 1er juillet 2025 ; lecture des matchs par `features/sources.py` seulement ;
  - copies sur le disque externe non faites (E-031) : `C:/fp_dumps/` et les CSV football-data.

## Décisions ouvertes

- Renouvellement automatique de l'abonnement : à couper au gel. Conditions de football-data (ADR-0023) : à relire.
- Rapport, décisions 16, 18, 20 à 22.

## Prochaines actions

**Automatiques** (tâches planifiées, journaux dans `C:/foot-predictor/data/logs/`) : `refresh` puis `run` les lundis 5 et 12 octobre à 08:00 ; journal T-60 les 9, 10, 11, 12, 16, 17 et 18 octobre.

**Session de gel, lundi 19 octobre** : suivre `docs/realisation/03_collecte/gel.md` (code du tag `v0.2.0`).

**Reprise de la partie 2 à la phase B après la session de gel** : 2.10 (`load` sur le brut définitif, recopie des CSV), 2.11 (chemins gelés, dont E-036), 2.12 (tag `v0.3.0`). Commandes : `docs/realisation/04_referentiel/README.md`, section « Phase B ».

**Reprise de la partie 3 à la phase B après la session de gel et la phase B de la partie 2** (3.11, sur demande) :

```bash
cd /c/fp-travail && git fetch origin --tags && git switch --detach origin/main && uv sync --all-groups
git tag -l v0.3.0                                          # phase B de la partie 2 faite
uv run python -m foot_predictor.features build             # nouveau staging (brut définitif)
uv run python -m foot_predictor.features check --invariance
# comparer, pour les matchs antérieurs au 2025-07-01, les lignes de la nouvelle version à ds-2026-09-30-ba2b91f7
# (jeu en vigueur depuis la partie 4, ADR-0035 ; et non plus ds-2026-09-29-83d28f3b)
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

**Long terme** : 5. inférence, API et interface, `v1.0.0` (J7, J8) ; 6. version intermédiaire (J9).

## Commandes de la session de gel (19 octobre)

Code exécuté : celui du tag `v0.2.0`, jamais `origin/main` (ADR-0021). Aucun `git pull` dans `C:/foot-predictor` avant l'étape 7 de `gel.md`.

```bash
cd /c/foot-predictor
schtasks //Query //FO TABLE | grep FootPredictor
grep -l ERREUR data/logs/*.log
uv run python -m foot_predictor.collect.api_football lock-status   # libre ; PAS de git pull ici
uv run python -m foot_predictor.collect.api_football refresh --season 2026 --yes
uv run python -m foot_predictor.collect.api_football run --max-requests 300
uv run python -m foot_predictor.collect.api_football status
uv run python -m foot_predictor.collect.api_football t60-report
cd /c/fp-travail && git fetch origin --tags && git switch --no-track -c data/03-gel-2026-10 v0.2.0
export PRE_COMMIT_ALLOW_NO_CONFIG=1   # dès l'étape 4 : sans elle, tout commit, push et push de tag échoue sur ce tag (E-034)
uv sync --all-groups && uv run pytest -m "not db" -q   # 288 réussis ; si seul test_freeze échoue (E-036), relancer
uv run python -m foot_predictor.collect.api_football --raw-dir C:/foot-predictor/data/raw freeze \
    --dest D:/foot-predictor/data-freeze-2026-10/raw --restore-to C:/fp_restauration/raw
# même terminal (variable exportée) : commit, git push -u origin data/03-gel-2026-10, PR, fusion,
#   git tag -a data-freeze-2026-10 origin/main ..., git push origin data-freeze-2026-10
# puis seulement : suppression des tâches, lock-status, git pull --ff-only et uv sync dans C:/foot-predictor
# retour du worktree sur main : git switch --detach origin/main && unset PRE_COMMIT_ALLOW_NO_CONFIG
```
