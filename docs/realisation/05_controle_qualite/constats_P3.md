# Constats du contrôle qualité — palier P3 (2026-09-29)

Lecture du résumé `reports/data_quality/raw_check_P3_2026-09-29.md` et de son fichier de détails (local, non versionné). **Aucun point bloquant** : aucune tâche en échec, aucun fichier corrompu, tous les matchs terminés ont leur détail. Les points « à regarder » sont, comme pour P1 et P2 (`constats_P1_P2.md`), des particularités des données de l'API, à traiter au **chargement vers staging** (jalon J3, ADR-0008).

**Scellé (ADR-0012).** Ce document classe des anomalies de **complétude** (listes, compositions, identifiants, profils). Il ne contient aucune analyse des résultats (scores, buts, performances) des matchs joués à partir du 1er juillet 2025. Ce document est versionné : il ne cite que des nombres et des libellés de championnat-saison, aucun nom ni identifiant de joueur.

## Volumes collectés

P3 couvre 11 championnats hors du top 5 et des D2, de 2015 à 2026 (Suisse à partir de 2016), avec les profils joueurs : Eredivisie, Primeira Liga, Jupiler Pro League, Premiership écossaise, Süper Lig, Bundesliga autrichienne, Super League suisse, Superliga danoise, Serie A brésilienne, Liga Profesional argentine et MLS.

| Palier | Listes | Matchs terminés avec détail | Fichiers bruts (sha256 conformes) | Tâches |
|---|---|---|---|---|
| P1 | 215 / 215 | 50 105 / 50 105 (100 %) | 8 117 | 8 097 done, 7 suspect |
| P2 | 38 / 38 | 14 468 / 14 468 (100 %) | 8 887 (cumul P1 + P2) | 769 done |
| **P3** | **131 / 131** | **37 516 / 37 516 (100 %)** | **15 494 (cumul P1 à P3)** | **6 605 done, 0 failed, 0 suspect** |
| **Total P1 à P3** | 384 | **102 089** | 15 494 | — |

- Collecte en deux runs (28 et 29 septembre), contrôle le 29 septembre.
- Copie intermédiaire de `data/raw` sur le disque externe le 29 septembre, 15 494 fichiers aux sha256 vérifiés. Complément ponctuel à l'ADR-0006 : la sauvegarde du gel (19 octobre) et son test de restauration restent prévus.

## Comparaison P1 / P2 / P3

| Indicateur | P1 | P2 | P3 |
|---|---|---|---|
| Un seul gardien titulaire identifié (par équipe) | 96,2 % | 5,2 % | 95,3 % |
| Statistiques joueurs (`players`) non vides | 95,9 % | 0,8 % | 97,3 % |
| Entrées sans identifiant de joueur | 1 098 | 53 | 1 501 |
| Titulaires sans profil `/players` | 335 | sans objet (pas de profils en P2) | 1 503 |
| Identifiants aux noms incompatibles | 1 017 sur 47 531 joueurs (2,1 %) | 101 sur 9 265 (1,1 %) | 808 sur 30 236 (2,7 %) |
| Doublons probables (groupes) | 33 sur 24 084 profils | sans objet (pas de profils) | 61 sur 29 032 profils |
| Notes hors de 3 à 10 | 1 154 | 0 (pas de statistiques) | 933 |

- Le taux de `players` de P3 exclut les saisons que `/leagues` déclare non couvertes (voir plus bas).
- **Les comptes sont faits palier par palier.** Un doublon ou une collision entre deux paliers (un joueur passé d'un championnat de P3 au top 5, par exemple) n'apparaît que si les paliers sont contrôlés ensemble.

## Championnat-saisons au nombre de matchs inattendu : 33 sur 114

Le contrôle attend n × (n - 1) matchs de saison régulière pour n équipes (aller-retour). 114 des 131 championnat-saisons ont des matchs nommés « Regular Season » et sont contrôlés. Les 17 autres (Écosse 2015 à 2018 et 2020 à 2025, Argentine 2020 à 2026) n'ont pas ce libellé : leur nombre de matchs n'est pas vérifié.

Les 33 écarts se classent ainsi : 30 formats particuliers, 2 saisons interrompues, 1 trou possible.

### a) Format particulier : 30 cas, rien à faire

| Championnat | Saisons | Cas | Format |
|---|---|---|---|
| Premiership (Écosse, 179) | 2026 | 1 | 12 équipes, 33 journées (trois tours) avant la scission en deux groupes : 198 matchs |
| Bundesliga (Autriche, 218) | 2015 à 2017 | 3 | 10 équipes, quatre tours (36 journées) : 180 matchs |
| Super League (Suisse, 207) | 2016 à 2022 | 7 | 10 équipes, quatre tours : 180 matchs ; de 2019 à 2022, 2 matchs hors saison régulière en plus |
| Super League (Suisse, 207) | 2023 à 2025 | 3 | 12 équipes, 33 journées (198 matchs), puis 32 matchs hors saison régulière (seconde phase) |
| Superliga (Danemark, 119) | 2015 | 1 | 12 équipes, 33 journées : 198 matchs |
| Liga Profesional (Argentine, 128) | 2015 à 2019 | 5 | Aller simple. 2017 à 2019 : exactement n × (n - 1) / 2. 2015 et 2016 : 30 journées pour 30 équipes, soit une journée de plus que l'aller simple (450 matchs) |
| MLS (253) | 2015, 2016, 2018, 2019, 2021 à 2026 | 10 | Calendrier déséquilibré par conférences : 34 matchs par équipe, soit exactement n × 34 / 2 |

### b) Saison interrompue ou équipe retirée : 2 cas, rien à recollecter

| Championnat-saison | Constat | Explication |
|---|---|---|
| Premiership (Écosse, 179) 2019 | 198 matchs listés (format à 33 journées), 179 joués, 19 annulés (`CANC`) | Saison arrêtée au printemps 2020 (COVID-19) |
| MLS (253) 2020 | 265 matchs de saison régulière pour 26 équipes (20 à 23 par équipe) ; la liste compte 8 matchs annulés (`CANC` et `Canc`) et 1 reporté (`PST`) ; s'y ajoute un tournoi d'été en groupes et élimination directe (51 matchs) | Saison réduite (COVID-19) |

Deux autres saisons interrompues ont une liste au nombre attendu et ne figurent donc pas parmi les 33 : **Eredivisie 2019** (306 listés, 232 joués) et **Jupiler Pro League 2019** (240 listés, 232 joués). Leurs matchs annulés sont à marquer au chargement, comme la Ligue 1 2019-20 en P1.

### c) Trou possible : 1 cas, décision à prendre

Au sens strict (championnat aller-retour classique avec moins de matchs listés que prévu), **aucun cas**. Un seul écart reste sans explication ; il est classé ici par prudence :

| Championnat-saison | Constat | Coût d'une nouvelle demande |
|---|---|---|
| MLS (253) 2017 | 373 matchs de saison régulière pour 22 équipes. 20 équipes en ont 34, deux en ont 33. La liste ne contient aucun match annulé ni reporté : il manque probablement un match entre ces deux équipes. | 1 requête (`/fixtures?league=253&season=2017`). Si le match apparaît : 1 requête de plus pour son détail. |

- Enjeu faible : la MLS ne fait pas partie de la population d'évaluation (top 5, ADR-0012). Elle ne sert qu'à l'historique des joueurs et aux expériences sur les données d'apprentissage.

**Suite donnée (2026-09-29, ADR-0019)** : la liste a été redemandée seule (`refresh --season 2017 --palier P3 --league 253`), pour 2 requêtes (`/status` et la liste). La nouvelle version est **identique** à l'ancienne : 390 matchs, dont 373 de saison régulière, les mêmes identifiants, deux équipes à 33 matchs. L'API ne connaît pas le match manquant. C'est un **trou de la source**, à consigner dans `DATA_FREEZE.md` ; aucun lot de détails n'a été créé.

## Points à reprendre au chargement (J3)

| Constat | Ampleur en P3 | Explication probable | Traitement envisagé |
|---|---|---|---|
| Joueurs sans identifiant | 1 501 entrées, dont 928 (62 %) sur deux championnat-saisons : MLS 2019 (560) et Jupiler Pro League 2018 (368) | Joueurs inconnus de l'API, ou saisons mal renseignées | « Inconnus », comptés 0 (ADR-0008, règle 1) |
| Titulaires sans profil `/players` | 1 503 : Argentine 667, Écosse 245, MLS 221, Eredivisie 144, Suisse 94, Belgique 64, autres 68 | Pages de profils incomplètes | Âge manquant ; voir « ADR-0008 » ci-dessous |
| Identifiants aux noms incompatibles | 808 | Surtout des variantes de nom (ADR-0008) | Pas d'examen un par un : seules les collisions comptent |
| Doublons probables | 61 groupes | Même joueur sous deux identifiants | YAML d'alias versionné (ADR-0008, règle 3) |
| Un seul gardien titulaire identifié | 95,3 % ; très bas en 2015 pour la Belgique (4,4 %), l'Écosse (0,9 %) et le Danemark (9,6 %), entre 54 et 81 % pour l'Écosse et le Danemark de 2016 à 2018 | Poste (`pos`) non renseigné | Déduire le poste des statistiques joueurs ou des saisons suivantes, comme pour P2 |
| Statistiques joueurs absentes | Non couvertes d'après `/leagues` : Belgique et Écosse 2015 à 2019, Suisse 2016 à 2018, Danemark 2015 à 2018, Argentine 2015. Partielles : Belgique 2020 (26,5 %), Brésil 2015 (46,6 %), Portugal 2015 (73,5 %), Argentine 2016 (76,4 %) | Couverture de l'API | Historique de notes plus court pour les recrues venues de ces championnats : elles reçoivent la moyenne de leur poste (ADR-0013) |
| Compositions absentes | Süper Lig 2022 : 91,8 % des matchs avec deux compositions (28 anomalies) | Trou de l'API | Titulaires inconnus pour ces matchs |
| Buts des événements ≠ score | 37 matchs sur 37 484 | Comme en P1 et P2 | Le score officiel fait foi (ADR-0009). Pas d'analyse plus poussée : une partie de ces matchs est sous scellés (ADR-0012) |
| Notes hors de 3 à 10 | 933, toutes dans les saisons 2026 | Notes vides ou nulles | Filtrer au calcul de la qualité du onze (ADR-0013) |
| Minutes hors de 0 à 130 | 1 | Anomalie de source | Écarter |
| Nombre de matchs inattendu | 33 sur 114 | Voir le classement ci-dessus | Formats et saisons interrompues documentés ; MLS 2017 selon la décision |
| Nombre de matchs non vérifié | 17 championnat-saisons (Écosse, Argentine) | Pas de libellé « Regular Season » | Vérifier au chargement à partir des libellés de journée |

## Mise à jour du 2026-09-29 : profils ciblés (ADR-0016)

Le compte « titulaires sans profil » ci-dessus (1 503 en P3, 335 en P1) ne regarde que les pages `/players` du **même** championnat-saison. Il surestime le manque : un joueur peut avoir son profil dans une autre saison ou un autre palier. Le nouvel indicateur de `raw_check`, « titulaires sans date de naissance (tous profils confondus) », regarde tous les profils du brut.

| Bloc | Titulaires distincts | Sans date avant | Profils ciblés demandés | Sans date après |
|---|---|---|---|---|
| P1 top 5 | 7 915 | 72 | 72 | **61** |
| P1 D2 | 11 887 | 192 | 192 | **157** |
| P3 | 19 802 | 661 | 661 | **211** |
| **Total** | — | **925** | **925** | **429** |

- Coût : 927 requêtes (`/players/profiles?player=`, une par joueur, plus 2 `/status`). Toutes les tâches sont `done` : l'API connaît chacun de ces joueurs.
- Rendement : 496 dates obtenues. Il est faible pour P1 (46 sur 264) : ces joueurs ont un profil, mais sans date de naissance. Il est élevé pour P3 (450 sur 661).
- Les nouveaux profils révèlent 3 groupes de doublons de plus (97 au lieu de 94) ; aucune nouvelle collision.
- Résumé : `reports/data_quality/raw_check_P1-P2-P3_2026-09-29.md` (régénéré après les profils ciblés).

## Conséquences pour les décisions

- **ADR-0008, identifiants.**
  - Les **1 503 titulaires sans profil** et les **61 groupes de doublons** relèvent des deux actions prévues avant le gel. La décision sur les **requêtes ciblées** (profils) se prend **après le test de collision** : ce test donne le vrai nombre de cas, sans quota.
  - Le test de collision est à lancer sur P1 à P3 **ensemble**, pour voir aussi les collisions et doublons entre paliers.
  - Les doublons se traitent par YAML d'alias, sans requête.
  - Critère de révision de l'ADR-0008 (plus d'environ 50 collisions réelles) : à évaluer sur le résultat du test.
- **Priorité proposée pour les requêtes ciblées**, si elles sont décidées. L'évaluation porte sur le top 5 (ADR-0012), donc P1 d'abord :
  1. P1, top 5 : 167 titulaires sans profil ;
  2. P1, D2 : 168 titulaires sans profil ;
  3. P3 : 1 503 titulaires sans profil, seulement s'il reste du quota. Ils ne servent qu'à l'âge des recrues dans la qualité du onze (horizon H2, ADR-0013).

  Le point d'accès exact et son coût restent à vérifier (ADR-0008) ; accord explicite requis.
- **ADR-0012, évaluation.** Aucun championnat de P3 n'entre dans la population d'évaluation. Les anomalies de P3 touchent les variables (historique des joueurs) et les expériences sur les données d'apprentissage, jamais le test.
- **ADR-0013, qualité du onze.** Les statistiques joueurs manquent jusqu'en 2018-19 pour la Suisse et le Danemark, jusqu'en 2019-20 pour la Belgique et l'Écosse. La règle de repli (moyenne du poste pour une recrue) couvre ce cas ; la règle de comparaison des notes entre championnats reste à définir au jalon J9.
- **ADR-0002, paliers.** P3 est collecté et contrôlé : le palier facultatif P4 peut être planifié, après les actions de l'ADR-0008 et les `refresh`.
