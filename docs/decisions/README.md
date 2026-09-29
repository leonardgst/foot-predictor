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
| [0008](ADR-0008-referentiel-identifiants.md) | API-FOOTBALL fait foi pour les identifiants ; `staging` reconstruit depuis le brut | acceptée, complétée par 0011 | 2026-09-28 | M7 |
| [0009](ADR-0009-cible-metrique.md) | Cible : buts par équipe ; sortie : loi du total ; métrique principale : log-loss du total | acceptée | 2026-09-28 | M8 |
| [0010](ADR-0010-horizons-prediction.md) | Deux horizons : avant composition (MVP), avec composition (version intermédiaire) | acceptée, journal T-60 précisé par 0017 | 2026-09-28 | M9 |
| [0011](ADR-0011-apres-abonnement.md) | Après l'abonnement : rejeu en mode principal, live partiel avant composition | acceptée | 2026-09-28 | M10 |
| [0012](ADR-0012-validation-scelles.md) | Validation glissante 2021-22 → 2024-25 ; matchs postérieurs au 30 juin 2025 sous scellés | acceptée | 2026-09-28 | M11 |
| [0013](ADR-0013-masse-salariale-mvs.md) | Pas de masse salariale ; « qualité du XI » en version intermédiaire ; MVS gelé | acceptée | 2026-09-28 | M12, M29 |
| [0014](ADR-0014-tri-documentation.md) | Restructuration de la documentation : première passe (archives, index, aucun dossier vide) | acceptée | 2026-09-28 | M19, K |
| [0015](ADR-0015-collisions-traitement-automatique.md) | Collisions d'identifiants de joueurs : exclusion automatique au chargement, YAML pour les exceptions | **proposée** | 2026-09-29 | M7 (révision de l'ADR-0008) |
| [0016](ADR-0016-profils-cibles.md) | Profils ciblés : titulaires sans date de naissance, top 5 puis D2 puis P3 | acceptée | 2026-09-29 | M7 (ADR-0008) |
| [0017](ADR-0017-journal-t60.md) | Journal T-60 fait du 9 au 18 octobre 2026, par tâches planifiées | acceptée | 2026-09-29 | M9 (ADR-0010) |
| [0018](ADR-0018-exploitation-collecte.md) | Exploitation jusqu'au gel : verrou de collecte obligatoire et tâches planifiées | acceptée | 2026-09-29 | M5, M6 |
| [0019](ADR-0019-palier-p4.md) | Palier P4 : classements du top 5 et des D2, indisponibilités des titulaires du top 5 | acceptée | 2026-09-29 | M2 (ADR-0002) |

**Décisions encore ouvertes** :

- **ADR-0015** (proposée) : traitement des 81 collisions d'identifiants de joueurs, critère de révision de l'ADR-0008 dépassé. À trancher avant le jalon J3.
- Renouvellement automatique de l'abonnement API-FOOTBALL (ADR-0005) : à vérifier dans le tableau de bord, et à couper au gel.

Rapport, partie M :

- 13 à 22 : importantes, non bloquantes. Les plus liées aux ADR ci-dessus :
  - 17 : Understat, qui conditionne l'xG en live (ADR-0011) ;
  - 16 : variante de stabilité ;
  - 19 : restructuration de la documentation, première passe faite (ADR-0014).
- 23 à 28 et 30 : reportables. La décision 29 (données dérivées de Transfermarkt) est confirmée par l'ADR-0013.
