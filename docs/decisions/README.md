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
| [0015](ADR-0015-collisions-traitement-automatique.md) | Collisions d'identifiants de joueurs : exclusion automatique au chargement, YAML pour les exceptions | remplacée par 0020 | 2026-09-29 | M7 (révision de l'ADR-0008) |
| [0016](ADR-0016-profils-cibles.md) | Profils ciblés : titulaires sans date de naissance, top 5 puis D2 puis P3 | acceptée | 2026-09-29 | M7 (ADR-0008) |
| [0017](ADR-0017-journal-t60.md) | Journal T-60 fait du 9 au 18 octobre 2026, par tâches planifiées | acceptée | 2026-09-29 | M9 (ADR-0010) |
| [0018](ADR-0018-exploitation-collecte.md) | Exploitation jusqu'au gel : verrou de collecte obligatoire et tâches planifiées | acceptée, complétée par 0021 | 2026-09-29 | M5, M6 |
| [0019](ADR-0019-palier-p4.md) | Palier P4 : classements du top 5 et des D2, indisponibilités des titulaires du top 5 | acceptée | 2026-09-29 | M2 (ADR-0002) |
| [0020](ADR-0020-collisions-numero-composition.md) | Collisions : exclusion automatique au chargement, numéro de la composition pour « deux numéros dans la même équipe » | acceptée | 2026-09-29 | M7 (remplace 0015) |
| [0021](ADR-0021-code-gel-tag-v0.2.0.md) | Session de gel : code du tag `v0.2.0`, pas de mise à jour du checkout principal avant le tag du gel | acceptée | 2026-09-29 | M5 (complète 0018) |
| [0022](ADR-0022-workflow-git.md) | Workflow Git : `main` et branches courtes, PR pour tout, merge commit, tags, hooks | acceptée | 2026-09-29 | M15 |
| [0023](ADR-0023-sources-externes-understat.md) | Sources externes : football-data retenu, Understat écarté (`robots.txt`), xG d'API-FOOTBALL seulement | acceptée | 2026-09-29 | M17 |
| [0024](ADR-0024-bruts-externes.md) | Bruts externes : dossier racine séparé jusqu'au gel, CSV octet pour octet, même journal que l'API | acceptée | 2026-09-29 | M3 (ADR-0003) |
| [0025](ADR-0025-bases-de-donnees.md) | Bases : base de travail reconstructible, base de test éphémère, ancienne base dev intacte, rôle dédié au worktree | acceptée | 2026-09-29 | M14 |
| [0026](ADR-0026-environnement-windows.md) | Environnement : Windows natif et Git Bash ; WSL2 étudié après le gel | acceptée | 2026-09-29 | M13 |
| [0027](ADR-0027-perimetre-chargeurs.md) | Périmètre des chargeurs du référentiel : MVP et H2 ; transferts, classements, indisponibilités, cotes reportés | acceptée, révisée en partie par 0029 et 0036 | 2026-09-29 | M7 (ADR-0008) |
| [0028](ADR-0028-scelle-technique.md) | Scellé technique : date unique, porte unique de lecture des matchs (`features/sources.py`), journal des tests scellés | acceptée | 2026-09-29 | M11 (ADR-0012) |
| [0029](ADR-0029-tirs-football-data.md) | Tirs et tirs cadrés chargés depuis football-data (révision partielle de l'ADR-0027) ; rupture de série de la Serie A 2018-19 à 2020-21 constatée | acceptée, complétée par 0035 | 2026-09-29 | M7 (ADR-0027) |
| [0030](ADR-0030-jeu-de-donnees.md) | Jeu de données : instantané Parquet versionné, traçabilité en base (`features.dataset_version`), une ligne par (match, équipe), registre des variables | acceptée | 2026-09-29 | F.2, I.3 |
| [0031](ADR-0031-elo.md) | Elo maison (G1) : une échelle par pays, mise à jour par jour, paramètres réglés sur 2005-06 à 2014-15 puis figés | acceptée | 2026-09-29 | I.3, M17 (ADR-0012) |
| [0032](ADR-0032-glissants-xg-proxy.md) | Glissants (G2) à décroissance en jours et retrait vers le championnat ; `xg_proxy` (tirs cadrés, coefficients positifs) à la place de l'xG avant 2022-23 | acceptée, complétée par 0035 | 2026-09-29 | H.4, I.3 (ADR-0023) |
| [0033](ADR-0033-calendrier-huis-clos.md) | Calendrier (G3) rétrospectif avec indicateur de fiabilité par pays ; huis clos (G0) par périodes sourcées, `incertain` exclu | acceptée | 2026-09-29 | I.3, I.5 (ADR-0011) |
| [0034](ADR-0034-notebooks-latex.md) | Notebooks d'exploration sans sorties (`nbstripout`, groupe `explo`, porte unique) ; chapitres LaTeX versionnés, compilés sur Overleaf | acceptée | 2026-09-29 | L (J4), M26 |
| [0035](ADR-0035-source-des-tirs.md) | Source des tirs de l'`xg_proxy` : API-FOOTBALL depuis 2015-16 quand elle est complète, sinon football-data ; `xg_proxy` réestimé ; `round` et `shots_source` au jeu | acceptée | 2026-09-30 | M7, I.3 (complète 0029 et 0032) |
| [0036](ADR-0036-cotes-reference-marche.md) | Cotes plus/moins 2,5 de football-data : référence de marché (avant clôture pour H1, clôture en borne haute), jamais une variable ; migration 0007 et ordre de priorité des colonnes | acceptée | 2026-09-30 | M18, I.6 (révise en partie 0027) |
| [0037](ADR-0037-protocole-evaluation.md) | Protocole d'évaluation et règle de décision, pré-enregistrés avant toute évaluation de modèle (tag `protocole-v1`) | acceptée | 2026-09-30 | I.5 à I.8, E.1 (complète 0009 et 0012) |

**Décisions encore ouvertes** :

- Renouvellement automatique de l'abonnement API-FOOTBALL (ADR-0005) : à vérifier dans le tableau de bord, et à couper au gel.

Rapport, partie M :

- 13 à 15 et 17 : tranchées en partie 2 (ADR-0026, ADR-0025, ADR-0022, ADR-0023).
- 16, 18 et 20 à 22 : importantes, non bloquantes, encore ouvertes. Les plus liées aux ADR ci-dessus :
  - 16 : variante de stabilité (partie 3) ;
  - 22 : orchestration et planification (après le gel ; WSL2 étudié, ADR-0026).
- 19 : restructuration de la documentation, première passe faite (ADR-0014).
- 23 à 28 et 30 : reportables. La décision 29 (données dérivées de Transfermarkt) est confirmée par l'ADR-0013.
