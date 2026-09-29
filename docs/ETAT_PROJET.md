# État du projet

**Dernière mise à jour** : 2026-09-29 (fin de la session « partie 1 »)
**Partie courante** : 1/6, terminer et geler la collecte. La collecte tourne seule par tâches planifiées jusqu'au 18 octobre ; il reste la session de gel du **19 octobre**.
**Échéance dure** : fin de l'abonnement API-FOOTBALL le **2026-10-22 à 07:56 UTC** ; gel le 19 octobre, marge les 20 et 21 (ADR-0005)

## Terminé

- Cadrage, collecteur v2 et contrôle du brut (PR #5 à #9). P1, P2 et P3 collectés et contrôlés : 102 089 matchs détaillés.
- Décisions M7 à M12 (ADR-0008 à 0013) et tri de `docs/` (ADR-0014).
- **Partie 1** (2026-09-29, PR #15 à #21), retour dans `docs/retours/partie-1_2026-09-29.md` :
  - **test de collision** dans `raw_check` (P1 à P3 ensemble) : 81 identifiants en collision réelle, après écartement de 3 faux positifs (identifiant 0, statistiques inversées, entrées répétées). Le seuil de l'ADR-0008 est dépassé : l'**ADR-0015 est proposée** ;
  - **profils ciblés** (ADR-0016) : 927 requêtes, 496 dates de naissance obtenues ; 429 titulaires restent sans date (61 top 5, 157 D2, 211 P3) ;
  - **verrou de collecte**, `lock-status`, **journal T-60** et son bilan (ADR-0017) ;
  - **9 tâches planifiées** `FootPredictor_*` créées (ADR-0018) ;
  - **commande `freeze`** et procédure `docs/realisation/03_collecte/gel.md` ; répétition à blanc réussie (9 min 18 s) ;
  - **MLS 2017** : liste redemandée, identique, donc trou de la source ; **P4** : 146 classements et 396 lots `sidelined` (ADR-0019).
- Quota consommé le 29/09 (journal) : 2 786 requêtes, dont 1 473 pour la partie 1 (budget accordé : 3 000).

## En cours

- Collecte automatique par tâches planifiées (voir « Prochaines actions »). Aucune commande à lancer à la main avant le 19 octobre.

## Bloqué

- Rien. Points de vigilance :
  - **avant tout `git pull` dans `C:/foot-predictor`** : `lock-status` doit répondre « libre » (`CLAUDE.md`) ;
  - le portable doit être **allumé, branché, capot ouvert, session ouverte** aux dates des tâches ; ne pas fermer leur fenêtre noire ;
  - ne pas exécuter `ingestion/api_football.py` ; ne jamais lancer `docker compose down -v` ni supprimer `data/raw/` ;
  - **scellé (ADR-0012)** : aucune analyse des résultats des matchs joués à partir du 1er juillet 2025.

## Décisions ouvertes

- **ADR-0015 (proposée)** : traitement des 81 collisions (exclusion automatique au chargement). À trancher avant J3.
- Renouvellement automatique de l'abonnement : à vérifier dans le tableau de bord, à couper au gel.
- Rapport, décisions 13 à 22 (M13 à M15 et M17 en partie 2).

## Prochaines actions

**Automatiques (tâches planifiées, journaux dans `C:/foot-predictor/data/logs/`)**

- [ ] **Lun. 5 oct., 08:00** : `refresh` de la saison 2026 (P1 et P3), puis `run` plafonné à 250.
- [ ] **Ven. 9, sam. 10, dim. 11, lun. 12 oct.** : journal T-60 (16:00 le vendredi et le lundi, 09:30 le week-end ; 80 requêtes au plus par jour).
- [ ] **Lun. 12 oct., 08:00** : `refresh`, puis `run` (250 au plus).
- [ ] **Ven. 16, sam. 17, dim. 18 oct.** : journal T-60.
- Le lendemain de chaque tâche, en 2 minutes si possible : `grep ERREUR data/logs/*.log` et `status`.

**Session de gel, lundi 19 octobre** (détail : `docs/realisation/03_collecte/gel.md`)

- [ ] Relire les journaux des tâches ; dernier `refresh` puis `run` ; `status` avec 0 failed.
- [ ] `t60-report`, puis `freeze` vers `D:/foot-predictor/data-freeze-2026-10/raw`, avec test de restauration.
- [ ] Relire et committer `docs/DATA_FREEZE.md` ; tag `data-freeze-2026-10` ; supprimer les tâches ; couper le renouvellement.

**Long terme : découpage du reste du projet en 6 parties**

1. **Terminer et geler la collecte** : cette partie, puis la session de gel du 19 octobre.
2. **Socle propre et référentiel** (J3) : nettoyage, décisions M13 à M15 et M17, brut en fichiers pour football-data et Understat, migration 0004, chargeurs brut → `staging` par identifiants API, YAML de rapprochement, `load` reproductible.
3. **Variables et exploration** (J4) : registre des variables avec horizon, Elo maison, fenêtres sans remise à zéro, calendrier, instantanés Parquet, scellé technique, exploration.
4. **Protocole, références et modèle MVP** (J5, J6) : plis glissants, métriques du total, références, progression des modèles, ablations, test scellé n° 1.
5. **Inférence, API et interface : MVP `v1.0.0`** (J7, J8).
6. **Version intermédiaire** (J9) : horizon H2 (qualité du XI, stabilité, entraîneur), modèles plus riches, test scellé n° 2.

## Commandes de la session de gel (19 octobre)

```bash
cd /c/foot-predictor
schtasks //Query //FO TABLE | grep FootPredictor
grep -l ERREUR data/logs/*.log
uv run python -m foot_predictor.collect.api_football lock-status && git pull --ff-only
uv run python -m foot_predictor.collect.api_football refresh --season 2026 --yes
uv run python -m foot_predictor.collect.api_football run --max-requests 300
uv run python -m foot_predictor.collect.api_football status
uv run python -m foot_predictor.collect.api_football t60-report
cd /c/fp-travail && git fetch origin && git switch --no-track -c data/03-gel-2026-10 origin/main
uv run python -m foot_predictor.collect.api_football --raw-dir C:/foot-predictor/data/raw freeze \
    --dest D:/foot-predictor/data-freeze-2026-10/raw --restore-to C:/fp_restauration/raw
```
