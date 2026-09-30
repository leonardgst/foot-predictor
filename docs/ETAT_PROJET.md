# État du projet

**Dernière mise à jour** : 2026-09-30 (fin du lot 2 de la partie 4)
**Partie courante** : 4/6, protocole, références et modèle MVP (J5, J6), phase A. **Lots 1 et 2 faits** (protocole, références, modèles M1 à M6) ; lot 3 (ablations, choix du modèle H1, gel de la liste) à la prochaine session. Les phases B des parties 2, 3 et 4 reprennent après la session de gel du **lundi 19 octobre**, sur demande.

**Reprise de la partie 4 au lot 3, sous-étape 4.13** (choix du modèle H1 et gel de la liste, branche `docs/10-choix-modele-h1` ; 4.12 faite : G0 + G1 + G2 retenus, G3 et D2 sans gain, `docs/resultats/ablations.md`). Relancer le prompt de la partie 4 ; lire d'abord `docs/retours/partie-4-lot2_2026-09-30.md`.
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
- **Partie 4, lot 2** (2026-09-30, PR #50 à #54, `docs/retours/partie-4-lot2_2026-09-30.md`) : M1 à M6 sur G0 + G1 (`docs/resultats/modeles.md`, chapitre LaTeX « Modèles ») ; **structure retenue : M3, Poisson par équipe** (ADR-0038), qui bat B1 de +0,0087 [+0,0048 ; +0,0126] ; NB, Dixon-Coles et régularisation sans gain ; G2 + G3 apportent +0,0091 à M3.

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

**Reprise de la partie 4, lot 3, à la prochaine session** (commandes de départ) :

```bash
cd /c/fp-travail && git fetch origin --tags && git switch --detach origin/main && uv sync --all-groups
uv run alembic current                        # 0007_cotes_football_data
uv run python -m foot_predictor.collect.api_football lock-status
uv run pytest -q                              # 571 réussis, 2 sautés au 2026-09-30
git switch --no-track -c feat/09-ablations origin/main
```

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

**Long terme** : 4. protocole, références et modèle MVP (J5, J6) ; 5. inférence, API et interface, `v1.0.0` (J7, J8) ; 6. version intermédiaire (J9).

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
