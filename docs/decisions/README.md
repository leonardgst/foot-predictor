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
| [0008](ADR-0008-referentiel-identifiants.md) | API-FOOTBALL fait foi pour les identifiants ; `staging` reconstruit depuis le brut | acceptée | 2026-09-28 | M7 |
| [0009](ADR-0009-cible-metrique.md) | Cible : buts par équipe ; sortie : loi du total ; métrique principale : log-loss du total | acceptée | 2026-09-28 | M8 |
| [0010](ADR-0010-horizons-prediction.md) | Deux horizons : avant composition (MVP), avec composition (version intermédiaire) | acceptée | 2026-09-28 | M9 |
| [0011](ADR-0011-apres-abonnement.md) | Après l'abonnement : rejeu en mode principal, live partiel avant composition | acceptée | 2026-09-28 | M10 |
| [0012](ADR-0012-validation-scelles.md) | Validation glissante 2021-22 → 2024-25 ; matchs postérieurs au 30 juin 2025 sous scellés | acceptée | 2026-09-28 | M11 |
| [0013](ADR-0013-masse-salariale-mvs.md) | Pas de masse salariale ; « qualité du XI » en version intermédiaire ; MVS gelé | acceptée | 2026-09-28 | M12, M29 |

**Décisions encore ouvertes** (rapport, partie M) :

- 13 à 22 : importantes, non bloquantes. Les plus liées aux ADR ci-dessus :
  - 17 : Understat, qui conditionne l'xG en live (ADR-0011) ;
  - 16 : variante de stabilité ;
  - 19 : restructuration de la documentation.
- 23 à 28 et 30 : reportables. La décision 29 (données dérivées de Transfermarkt) est confirmée par l'ADR-0013.
