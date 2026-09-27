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

Les entrées ci-dessous reprennent les incidents documentés avant le 2026-09-24 (source : `docs/RECAP_PROJET.md` §9 et `docs/recaps/`).

## E-005 — xG équipe jamais enregistré (2026-09-22)

- **Contexte** : backfill Understat sur 10 saisons.
- **Message d'erreur** : aucun ; le script annonçait 18 008 lignes « traitées » alors que seules 6,6 % des lignes avaient un xG.
- **Cause** : `upsert_team_match_xg` était importée dans `understat.py` mais jamais appelée.
- **Solution** : appel ajouté pour chaque équipe ; couverture passée à 99,98 %.
- **Fichiers concernés** : `ingestion/understat.py`, `ingestion/common.py`.
- **Prévention** : après une ingestion, vérifier les colonnes remplies, pas seulement le nombre de lignes « traitées ».
- **Test de non-régression** : à ajouter (test d'ingestion vérifiant que `xg_for` est non nul).

## E-004 — Équipe Ajaccio mal rattachée (2026-09-22)

- **Contexte** : backfill football-data et Understat.
- **Message d'erreur** : 41 lignes ignorées.
- **Cause** : `Ajaccio` (AC Ajaccio, 2022-23) mappé vers `GFC Ajaccio` dans les YAML ; `Ajaccio GFCO` absent.
- **Solution** : YAML corrigés, équipes renommées et `TeamSourceMapping` repointé **à la main en base dev**.
- **Fichiers concernés** : `mappings/football_data_teams.yaml`, `mappings/understat_teams.yaml`.
- **Prévention** : `mappings/api_football_teams.yaml` contient encore `Ajaccio: GFC Ajaccio` (rapport B.4, D2). Correction définitive prévue avec le référentiel par identifiants.
- **Test de non-régression** : non.

## E-003 — 19 équipes en double après correction de YAML (2026-07-24)

- **Contexte** : ingestion Understat, 568 lignes ignorées sur 1 184.
- **Message d'erreur** : aucun, lignes ignorées silencieusement.
- **Cause** : `get_or_create_team` renvoie le mapping déjà enregistré sans relire le YAML ; une correction de YAML a donc créé une seconde équipe.
- **Solution** : script `scripts/one_off/fusion.py` (19 fusions, en base dev uniquement).
- **Fichiers concernés** : `ingestion/common.py`, `mappings/*.yaml`.
- **Prévention** : référentiel par identifiants sources, reconstruit depuis le brut, sans correction manuelle en base (ADR à venir, décision M7).
- **Test de non-régression** : tests de réconciliation dans `tests/ingestion/test_common.py`.

## E-002 — `postgres_user Field required` malgré la variable présente

- **Contexte** : chargement de la configuration.
- **Cause** : fichier `.env` enregistré en UTF-8 **avec BOM**, qui corrompt le nom de la première variable.
- **Solution** : réenregistrer les `.env.*` en UTF-8 sans BOM.
- **Prévention** : environnement WSL2 envisagé (décision M13).

## E-001 — `password authentication failed` sur la base dev

- **Contexte** : connexion SQLTools et Python à Postgres.
- **Cause** : une installation Postgres native Windows occupait le port 5432.
- **Solution** : port dev déplacé sur 5440 dans `docker-compose.yml` et `.env.dev`.
- **Prévention** : désactiver le service Windows `postgresql-x64-XX`. Diagnostic : arrêter le conteneur ; si l'erreur reste une erreur Postgres, un autre serveur répond.
