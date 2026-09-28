# Constats du contrôle qualité — paliers P1 et P2 (2026-09-28)

Lecture des résumés `reports/data_quality/raw_check_P1_2026-09-28.md` et `raw_check_P2_2026-09-28.md`. **Aucun point bloquant** : rien n'est à recollecter. Les points « à regarder » sont des particularités des données de l'API, à traiter au **chargement vers staging** (jalon J3, décision M7).

## Volumes collectés

| Palier | Listes | Matchs terminés avec détail | Fichiers bruts (sha256 conformes) | Tâches |
|---|---|---|---|---|
| P1 | 215 / 215 | 50 105 / 50 105 (100 %) | 8 117 | 8 097 done, 7 suspect |
| P2 | 38 / 38 | 14 468 / 14 468 (100 %) | 8 887 (cumul P1 + P2) | 769 done |

- P2 : 38 championnat-saisons antérieures à 2015 déclarent des compositions (`coverage.fixtures.lineups`).
- Les 7 tâches `suspect` de P1 sont des entraîneurs (`/coachs?team=`) renvoyés vides deux fois (équipes 62, 490, 491, 729, 803, 860, 3006) : trou de l'API, accepté. L'entraîneur de chaque match reste disponible dans sa composition.
- Matchs non terminaux mis de côté à la fin de P1 : 3 852 (NS 3 618 = saison 2026-27 à venir ; CANC 227 + « Canc » 4 = matchs annulés, dont la fin de la Ligue 1 2019-20 ; PST 2 ; 2H 1). Repris par `refresh` (5, 12 et 19 octobre).

## Points à reprendre au chargement (J3)

| Constat | Palier | Ampleur | Explication probable | Traitement envisagé |
|---|---|---|---|---|
| **Identifiants associés à des noms incompatibles** | P1, P2 | 1 017 (P1) et 101 (P2) | Translittérations, changements de nom, ou vraies erreurs de l'API | **Examiner avant tout calcul de stabilité** : l'indicateur repose sur ces identifiants |
| Doublons probables (même nom, même date de naissance) | P1 | 33 groupes | Même joueur sous deux identifiants | Table de correspondance versionnée (YAML), jamais de correction manuelle en base |
| Joueurs sans identifiant dans les compositions | P1, P2 | 1 098 (P1), 53 (P2) | Joueurs inconnus de l'API | Garder comme « inconnus » (ils comptent 0 dans la stabilité) |
| Titulaires sans profil `/players` | P1 | 335 | Joueurs absents des pages de profils | Âge manquant pour ces joueurs |
| Un seul gardien titulaire identifié | P1 : 96,2 % ; **P2 : 5,2 %** | — | Poste (`pos`) non renseigné, surtout avant 2015 | Déduire le poste des statistiques joueurs ou des saisons suivantes (même identifiant) |
| Statistiques joueurs présentes | P1 : 95,9 % ; **P2 : 0,8 %** | — | Avant 2015, l'API ne fournit que les compositions | **La qualité du onze (notes, minutes) n'est calculable qu'à partir de 2015** ; P2 sert à amorcer la stabilité |
| Buts des événements ≠ score | P1 : 162 ; P2 : 33 | < 0,5 % | Buts contre son camp, matchs sur tapis vert, tirs au but | Le score officiel fait foi ; les événements servent au détail |
| Notes hors de 3 à 10 | P1 | 1 154 | Notes nulles ou vides (entrées en fin de match) | Filtrer au calcul de la qualité du onze |
| Minutes hors de 0 à 130 | P1 | 22 | Anomalies de source | Écarter |
| Championnat-saisons au nombre de matchs inattendu | P2 | 2 / 38 | Format particulier ou trou de l'API | Identifier dans les listes détaillées au chargement |
| Statut « Canc » en plus de « CANC » | P1 | 4 | Orthographe de l'API | Normaliser au chargement |

## Conséquences pour les décisions à venir

- **M7 (référentiel)** : les identifiants API sont utilisables comme référentiel maître, à condition de traiter les 1 017 + 101 identifiants aux noms incompatibles et les 33 doublons **avant** de construire la stabilité.
- **Stabilité (H.7)** : l'historique antérieur à 2015 (P2) permet d'amorcer une décroissance sans remise à zéro dès 2015-16. La stabilité par ligne dépendra de la reconstitution des postes.
- **Qualité du onze (G.12)** : période utilisable à partir de 2015-16 uniquement.

## Suite donnée (2026-09-28)

- **ADR-0008** : les 1 118 identifiants « aux noms incompatibles » ne sont pas à examiner un par un ; ce sont surtout des variantes de nom. Seules les **collisions** (un identifiant, deux personnes) et les 33 doublons sont traités, par YAML versionné. Un test de collision est ajouté à `raw_check.py` avant le gel.
- **ADR-0009** : le score officiel au temps réglementaire fait foi ; les événements servent au détail.
- **ADR-0013** : la qualité du onze, calculable à partir de 2015-16, relève de la version intermédiaire (horizon H2).
