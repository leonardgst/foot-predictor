# Décisions (ADR)

Une ADR (*Architecture Decision Record*) consigne une décision : contexte, options, choix, conséquences. Elle ne se réécrit pas : si la décision change, une nouvelle ADR la remplace. En cas de désaccord avec le rapport de cadrage du 2026-09-24, **les ADR font foi**.

Modèle : [`_modele_adr.md`](_modele_adr.md). Les numéros « M » renvoient à la partie M du rapport de cadrage.

| ADR | Titre | Statut | Date | Rapport |
|---|---|---|---|---|
| [0001](ADR-0001-backfill-en-cours.md) | Arrêt de l'ancien backfill, recollecte complète par le collecteur v2 | acceptée | 2026-09-27 | M1 |
| [0002](ADR-0002-perimetre-collecte.md) | Périmètre de collecte pendant l'abonnement (maximum utile, par paliers) | acceptée | 2026-09-27 | M2 |
| [0003](ADR-0003-format-brut.md) | Brut en fichiers `.json.gz` + journal de requêtes | acceptée | 2026-09-27 | M3 |
| [0004](ADR-0004-collecteur-v2.md) | Collecteur v2 avant de poursuivre la collecte | acceptée | 2026-09-27 | M4 |
| [0005](ADR-0005-abonnement.md) | Fin de l'abonnement (2026-10-22) et calendrier de gel | acceptée | 2026-09-27 | M5 |
| [0006](ADR-0006-sauvegarde.md) | Sauvegarde unique sur disque externe au gel, avec test de restauration | acceptée | 2026-09-27 | M6 |
| [0007](ADR-0007-paquet-collect.md) | Collecteur v2 dans `collect/api_football/` (conflit de nom avec `ingestion/api_football.py`) | acceptée | 2026-09-27 | F.3, F.9 |

**Décisions encore ouvertes** (rapport, partie M) : 7 à 12 à trancher avant la fin de l'abonnement ; 13 à 22 importantes non bloquantes ; 23 à 30 reportables.
