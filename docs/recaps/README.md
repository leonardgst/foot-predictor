# Récaps projet — foot-predictor

Ce dossier centralise l'historique des décisions et de l'avancement du projet,
généré au fil des conversations avec Claude. Chaque document complète le
précédent — à lire dans l'ordre ci-dessous pour reconstituer le fil sans
avoir à deviner la chronologie depuis les noms de fichiers.

**Pour reprendre le projet rapidement** : lire au minimum le document marqué
👉 ci-dessous (dernier état connu), plus `recap_decisions_projet.md` si besoin
de recontextualiser une décision plus ancienne.

---

## Ordre de lecture

| # | Document | Contenu |
|---|---|---|
| 1 | `Objectifs_projet` | Cadrage initial : objectif fonctionnel (prédire un résultat de match) et objectif réel (projet pédagogique end-to-end de data science) |
| 2 | `recap_decisions_projet.md` | Décisions de cadrage : périmètre, données retenues, indicateur de stabilité, architecture SI (raw/staging/features), stack technique |
| 3 | `recap_mise_en_place_git_docker.md` | Mise en place concrète : dépôt Git/GitHub, branches, environnements PostgreSQL via Docker (dev/test) |
| 4 | `recap_etape1_infra_finalisee.md` | Étape 1 : infra Neon (prod), Alembic, VSCode/SQLTools — incidents rencontrés et résolus (port Postgres, encodage BOM, etc.) |
| 5 | `recap_etape2_schema_tables.md` | Étape 2 : conception complète du schéma de tables (raw / staging / features) |
| 6 | `recap_etape3_pipeline_et_mvs.md` | Étape 3 : abandon de Transfermarkt, conception du Market Value Score (MVS), pipeline d'ingestion des 3 sources retenues |
| 7 | `recap_debug_ingestion_understat.md` | Debug : équipes dupliquées suite à un mapping YAML corrigé après coup (19 fusions), décalage de date ±1 jour. 568 → 0 lignes ignorées |
| 8 | `prochaine_etape_clustering_mvs.md` | 👉 **Prochaine étape à démarrer** : clustering de style + calcul du MVS (partie Performance) |
| 9 | `recap_mise_en_ordre_git_et_verifications.md` | Remise à plat du dépôt (commit `4af1eb2`), dépendances de `market_value/`, recréation de `check_raw.py` et premier résultat sur SP1 |

---

## État d'avancement en un coup d'œil

- ✅ Infra (Docker dev/test, Neon prod, Alembic) opérationnelle sur les 3 environnements
- ✅ Schéma `raw` / `staging` / `features` conçu et migré
- ✅ Pipeline d'ingestion football-data.co.uk + Understat (équipe) fonctionnel, testé, bug de réconciliation corrigé
- ✅ Code du module `market_value/` (clustering, per90, percentiles, persistence) écrit — **committé sur `dev` mais pas encore exécuté sur de vraies données**
- 🚧 Bloqué en attente d'abonnement API-Football (plan gratuit insuffisant : ne couvre que les 2 derniers jours, aucun match des championnats suivis) :
  - `staging.lineup`, `staging.player_match_stats` : vides
  - `features.team_match_features.squad_avg_age` / `squad_stability_score_season` : non calculables
  - Tout le pipeline `market_value/` (MVS) : bloqué faute de données à charger
- ⬜ Tests automatisés (`tests/` toujours vide)
- ⬜ Choix du modèle statistique final pour le score exact (Poisson / Dixon-Coles)
- ⬜ Consommation de `raw.api_football_injuries` (capturée mais jamais ingérée)
- ⬜ Stratégie de scraping planifiée (cron/fréquence)

---

## Point de vigilance transversal à garder en tête

Corriger un fichier de mapping YAML (`*_teams.yaml`) après coup **ne suffit
jamais à lui seul** à réparer une entité déjà créée en base : la logique
`get_or_create_*` de `common.py` priorise le `*_source_mapping` déjà
enregistré sur le contenu du YAML (cf. `recap_debug_ingestion_understat.md`).
Toute correction de mapping doit s'accompagner d'une vérification des entités
déjà résolues avant la correction — en particulier pour `api_football_teams.yaml`
une fois l'ingestion API-Football lancée.

---

*Dossier à maintenir à jour : ajouter chaque nouveau récap ici avec sa ligne
dans le tableau, et mettre à jour la section "état d'avancement" en conséquence.*
