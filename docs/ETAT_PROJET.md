# État du projet

**Dernière mise à jour** : 2026-09-29 (fin de la partie 2, phase A)
**Partie courante** : 2/6, socle propre et référentiel (J3). **Phase A faite** ; la **phase B** reprend après la session de gel du **lundi 19 octobre**, sur demande.
**Échéance dure** : fin de l'abonnement API-FOOTBALL le **2026-10-22 à 07:56 UTC** ; gel le 19, marge les 20 et 21 (ADR-0005).

## Terminé

- Cadrage, collecteur v2, P1 à P4 collectés et contrôlés ; partie 1 (PR #15 à #21) : collisions, profils ciblés, verrou, T-60, 9 tâches planifiées, `freeze`.
- **Partie 2, phase A** (2026-09-29, PR #22 à #31), retour dans `docs/retours/partie-2a_2026-09-29.md` :
  - réparations : commande T-60 du README, **code du gel figé au tag `v0.2.0`** (ADR-0021), répétition du passage sur ce tag réussie ;
  - décisions : collisions 2b (ADR-0020), M15 workflow Git (0022), M17 Understat écarté (0023), bruts externes (0024), M14 bases (0025), M13 Windows (0026), périmètre des chargeurs (0027) ;
  - outillage : ruff, pre-commit (gitleaks, caractères de contrôle), CI avec Postgres et **tous** les tests ;
  - nettoyage : anciens collecteurs et ancien chargement retirés, `scripts/archives/`, `hdbscan` et `understatapi` retirés, branches fusionnées supprimées ;
  - brut football-data : 270 CSV (10 divisions, 2000-01 à 2026-27) dans `C:/fp-travail/data/raw` ;
  - migration 0004 ; YAML de rapprochement produits depuis le brut ; chargeurs API et football-data ;
  - **`load` : deux reconstructions complètes identiques (375 s et 563 s)** ; appariement football-data 99,98 % ; rapport `reports/data_quality/referentiel_2026-09-29.md`.

## En cours

- Collecte automatique par tâches planifiées jusqu'au 18 octobre. Aucune commande à lancer à la main avant le 19.

## Bloqué

- Rien. Points de vigilance :
  - **aucun `git pull` dans `C:/foot-predictor` avant l'étape 7 du gel** (ADR-0021) ; ensuite, `lock-status` avant chaque `git pull` ;
  - portable **allumé, branché, capot ouvert, session ouverte** aux dates des tâches ; ne pas fermer leur fenêtre noire ;
  - `load` ne vise que `foot_predictor_travail` ; l'ancienne base `foot_predictor_dev` reste intacte (ADR-0025) ;
  - **scellé (ADR-0012)** : aucune analyse des résultats des matchs joués à partir du 1er juillet 2025 ;
  - copies sur le disque externe non faites (permissions de la session, E-031) : dump de l'ancienne base (`C:/fp_dumps/`) et CSV football-data. À faire à la main, ou en phase B sur accord.

## Décisions ouvertes

- Renouvellement automatique de l'abonnement : à vérifier dans le tableau de bord, à couper au gel.
- Conditions de football-data (ADR-0023) : interprétation à relire.
- ADR-0020 : 4 joueur-saisons du top 5 perdent plus de 10 % de leurs titularisations ; scission par équipe à étudier au J9.
- Rapport, décisions 16, 18 et 20 à 22 (dont M22, orchestration, et WSL2 après le gel).

## Prochaines actions

**Automatiques (tâches planifiées, journaux dans `C:/foot-predictor/data/logs/`)**

| Date | Tâche |
|---|---|
| lun. 5 oct., 08:00 | `refresh` saison 2026, puis `run` (250 au plus) |
| ven. 9, sam. 10, dim. 11, lun. 12 oct. | journal T-60 (80 requêtes au plus par jour) |
| lun. 12 oct., 08:00 | `refresh`, puis `run` (250 au plus) |
| ven. 16, sam. 17, dim. 18 oct. | journal T-60 |

Le lendemain de chaque tâche, si possible : `grep ERREUR data/logs/*.log` et `status`.

**Session de gel, lundi 19 octobre** : suivre `docs/realisation/03_collecte/gel.md` (code du tag `v0.2.0`).

**Reprise de la partie 2 à la phase B après la session de gel** (commandes exactes : `docs/realisation/04_referentiel/README.md`, section « Phase B ») :

- [ ] 2.10 : vérifier le tag `data-freeze-2026-10`, `docs/DATA_FREEZE.md` sur `main`, `C:/foot-predictor` à jour, verrou libre ; `load` sur le brut définitif, `check-referentiel` (appariement ≥ 99,5 %) ; recopie des CSV football-data vers `C:/foot-predictor/data/raw`, sha256 vérifiés.
- [ ] 2.11 : ruff et pre-commit sur les chemins gelés ; `raw_check` appelle `ingestion/collisions.py` (résumé identique octet pour octet, hors date).
- [ ] 2.12 : tag `v0.3.0`, retour final `docs/retours/partie-2_<date>.md`.

**Long terme** : 3. variables et exploration (J4) ; 4. protocole, références et modèle MVP (J5, J6) ; 5. inférence, API et interface, `v1.0.0` (J7, J8) ; 6. version intermédiaire (J9).

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
uv sync --all-groups && uv run pytest -m "not db" -q                 # 288 réussis (répété le 29/09)
uv run python -m foot_predictor.collect.api_football --raw-dir C:/foot-predictor/data/raw freeze \
    --dest D:/foot-predictor/data-freeze-2026-10/raw --restore-to C:/fp_restauration/raw
# même terminal (variable exportée) : commit, git push -u origin data/03-gel-2026-10, PR, fusion,
#   git tag -a data-freeze-2026-10 origin/main ..., git push origin data-freeze-2026-10
# puis seulement : suppression des tâches, lock-status, git pull --ff-only et uv sync dans C:/foot-predictor
# retour du worktree sur main : git switch --detach origin/main && unset PRE_COMMIT_ALLOW_NO_CONFIG
```
