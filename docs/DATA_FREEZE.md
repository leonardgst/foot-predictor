# Gel des données API-FOOTBALL (octobre 2026)

> **Gel du 2026-10-19** : brouillon généré à 07:42 UTC (09:42 heure de Paris) par la commande `freeze`, relu et complété à la main le même jour. Le tag `data-freeze-2026-10` se pose sur `main` après la fusion de ce fichier.

Décisions : ADR-0002 (périmètre), ADR-0003 (format), ADR-0005 (calendrier), ADR-0006 (sauvegarde), ADR-0008 (identifiants), ADR-0012 (scellé). Ce document ne contient que des nombres : aucun nom, aucun identifiant de joueur, aucun résultat de match.

## Périmètre

| Palier | Bloc | Compétitions | Saisons | Types |
|---|---|---|---|---|
| P1 | top5 | 39, 140, 78, 135, 61 | 2015 → 2026 | fixtures_list, fixtures_detail, teams, injuries, players, coachs, transfers |
| P1 | d2 | 40, 141, 79, 136, 62 | 2015 → 2026 | fixtures_list, fixtures_detail, teams, injuries, players, coachs, transfers |
| P1 | coupes_europe | 2, 3, 848 | 2015 → 2026 | fixtures_list, fixtures_detail |
| P1 | coupes_nationales | 45, 48, 143, 81, 137, 66 | 2015 → 2026 | fixtures_list, fixtures_detail |
| P2 | top5_d2_historique | 39, 140, 78, 135, 61, 40, 141, 79, 136, 62 | … → 2014 (si fixtures.lineups) | fixtures_list, fixtures_detail |
| P3 | autres_championnats | 88, 94, 144, 179, 203, 218, 207, 119, 71, 128, 253 | 2015 → 2026 | fixtures_list, fixtures_detail, players |
| P4 | classements_top5_d2 | 39, 140, 78, 135, 61, 40, 141, 79, 136, 62 | 2010 → 2025 | standings |

Hors YAML : profils ciblés (`player_profiles`, ADR-0008) et journal T-60 (`daily`, ADR-0010).

## Volumes

- Fichiers bruts : **17336**, 306.0 Mo compressés.
- Lignes du journal de requêtes : 17336.
- Matchs terminés avec détail : **102554 / 102554**.
- Profils joueurs lus : 47377 ; titulaires sans date de naissance : 462.

| Type de requête | Fichiers | Taille |
|---|---|---|
| coachs | 305 | 0.3 Mo |
| daily | 183 | 0.7 Mo |
| fixtures_detail | 5310 | 260.5 Mo |
| fixtures_list | 472 | 6.7 Mo |
| injuries | 65 | 2.5 Mo |
| leagues | 1 | 0.1 Mo |
| player_profiles | 925 | 0.4 Mo |
| players | 9071 | 29.1 Mo |
| sidelined | 396 | 0.7 Mo |
| standings | 146 | 0.3 Mo |
| status | 16 | 0.0 Mo |
| teams | 148 | 0.3 Mo |
| transfers | 298 | 4.5 Mo |

| Palier | Tâches done | failed | suspect | pending |
|---|---|---|---|---|
| P1 | 8385 | 0 | 7 | 0 |
| P2 | 769 | 0 | 0 | 0 |
| P3 | 7290 | 0 | 0 | 0 |
| P4 | 542 | 0 | 0 | 0 |

## Contrôle du brut

Verdict `raw_check` (tous les paliers) : **À REGARDER**. Résumé versionné : `reports/data_quality/raw_check_tous_2026-10-19.md`.

| Contrôle | Statut | Détail |
|---|---|---|
| Matchs listés contre attendu | À REGARDER | 530/530 listes présentes ; 379/416 championnats au nombre attendu |
| Matchs terminés ayant un détail | OK | 102554/102554 (100.0 %) |
| Compositions : 2 par match, 11 titulaires et 1 gardien par équipe | À REGARDER | 2 compos 99.8 % ; 11 titulaires 100.0 % ; 1 gardien 83.1 % ; 147 championnat-saison(s) sous 99 % ; 34895 anomalie(s) listée(s) |
| players et events non vides | À REGARDER | players 96.0 % ; events 99.9 % ; 91 championnat-saison(s) sous 99 % ; 3364 anomalie(s) listée(s) |
| Buts dans events = score | À REGARDER | 102183/102415 matchs conformes |
| player.id présent partout | À REGARDER | 3099 entrée(s) sans identifiant |
| Titulaires présents dans les profils | À REGARDER | 1897 titulaire(s) sans profil, sur 249 championnat-saison(s) aux profils complets |
| Titulaires sans date de naissance (tous profils confondus) | À REGARDER | 462 titulaire(s) (P1 231, P3 231) ; profils ciblés lus : 925 |
| Un identifiant, un seul joueur | À REGARDER | 1748 identifiant(s) aux noms incompatibles ; 48551 avec des variantes tolérées, sur 70660 joueurs |
| Doublons probables (même nom, même naissance) | À REGARDER | 97 groupe(s), sur 47377 profils ; dont 0 inter-paliers |
| Collisions : deux équipes le même jour | À REGARDER | 26 identifiant(s), 143 cas, sur 4015379 présences (joueur, match) |
| Collisions : deux fois dans un même match | À REGARDER | 63 identifiant(s), 314 cas ; chez les deux équipes : 13, deux numéros dans la même équipe : 50 ; faux positifs écartés : 1397 cas |
| Collisions : deux dates de naissance | À REGARDER | 3 identifiant(s), 3 cas ; 3 date(s) corrigée(s) d'une saison à l'autre, classée(s) à part |
| Minutes entre 0 et 130 | À REGARDER | 23 anomalie(s) |
| Note entre 3 et 10 | À REGARDER | 6888 anomalie(s) |
| Intégrité des fichiers (sha256) | OK | 17336 conformes ; 0 sha256 différent(s) ; 0 absent(s) ; 0 illisible(s) ; 0 hors journal |
| Tâches de la file (failed, suspect) | À REGARDER | done 16986, pending 0, failed 0, suspect 7 |

## Trous connus

Rien n'est recollecté après le gel. Les points ci-dessous sont des données telles que l'API les fournit.

- Tâche suspect : P1 coachs {'team': 3006} (results = 0 alors que des données sont attendues)
- Tâche suspect : P1 coachs {'team': 860} (results = 0 alors que des données sont attendues)
- Tâche suspect : P1 coachs {'team': 803} (results = 0 alors que des données sont attendues)
- Tâche suspect : P1 coachs {'team': 729} (results = 0 alors que des données sont attendues)
- Tâche suspect : P1 coachs {'team': 491} (results = 0 alors que des données sont attendues)
- Tâche suspect : P1 coachs {'team': 490} (results = 0 alors que des données sont attendues)
- Tâche suspect : P1 coachs {'team': 62} (results = 0 alors que des données sont attendues)
- Matchs non terminaux au gel : 5185 (NS 4827, CANC 345, Canc 7, PST 5, ABD 1).
- Constats détaillés : `docs/realisation/05_controle_qualite/constats_P1_P2.md`, `constats_P3.md`, `constats_collisions.md`.
- **MLS 2017** (253) : la liste de saison régulière compte 373 matchs au lieu de 374 pour 22 équipes ; deux équipes ont 33 matchs au lieu de 34. La liste redemandée le 2026-09-29 (ADR-0019) est identique : l'API ne connaît pas le match. **Trou de la source**, non recollectable ; la MLS n'est pas dans la population d'évaluation.
- **Sept tâches `coachs` en `suspect`** (équipes 62, 490, 491, 729, 803, 860, 3006) : réponse vide (`results = 0`), connue depuis le 5 octobre, jugée plausible. Elles ne sont pas remises en file : ces sept équipes n'ont pas de fichier `coachs` utilisable dans le brut.
- **Journaux T-60** : aucun trou. Les sept journaux (9, 10, 11, 12, 16, 17 et 18 octobre) ont leur ligne de fin, soit 92 matchs suivis et 92 compositions obtenues avant le coup d'envoi, aucun match « coup d'envoi atteint sans compositions ».
- **Un match annoncé sans détail** au gel (`t60-report`) : le bilan T-60 le laisse de côté. Tous les matchs terminés ont leur détail (102 554 / 102 554), donc ce match n'est pas terminé ; le décompte des non-terminaux compte un match abandonné (ABD) et cinq reportés (PST). Cause non vérifiée match par match (on ne lit aucune valeur au-delà du 1er juillet 2025, ADR-0012).
- **Écarts du contrôle de complétude** (37 championnat-saisons sur 416 hors du nombre attendu ; la comparaison « listés / attendu » ne modélise ni les barrages ni les formats à phases) : listes plus longues que n × (n − 1) (matchs de barrage ou de phase finale : Bundesliga, Championship, Serie B…), listes plus courtes (Ligue 2 2010 : 370 matchs listés sur 380 ; 2. Bundesliga 2012 : 302 sur 306, listes telles que l'API les fournit, non redemandées), saisons dont moins de matchs sont terminés que listés (2019-20 de la Ligue 1 et de la Ligue 2 : 279 et 280 terminés sur 380 listés ; Eredivisie et Jupiler Pro League 2019-20 : 232 terminés), et ligues à formats particuliers (MLS, Argentine, Écosse, Danemark, Autriche, Suisse), documentées dans `constats_P3.md`. Dans tous les cas, **chaque match terminé a son détail**.

## Quota consommé

Requêtes journalisées : **17336**, du 2026-09-27 au 2026-10-19 (UTC).

| Jour (UTC) | Requêtes |
|---|---|
| 2026-09-27 | 7123 |
| 2026-09-28 | 7058 |
| 2026-09-29 | 2786 |
| 2026-10-05 | 50 |
| 2026-10-09 | 10 |
| 2026-10-10 | 35 |
| 2026-10-11 | 37 |
| 2026-10-12 | 77 |
| 2026-10-16 | 10 |
| 2026-10-17 | 42 |
| 2026-10-18 | 38 |
| 2026-10-19 | 70 |

## Journal et sauvegarde

- Journal : `_manifest/api_football.jsonl`, sha256 `38c111a0e2491b1955a44ac8f6a821c02248de04d072ccc131197b02bc9c3143`.
- Sauvegarde : `D:/foot-predictor/data-freeze-2026-10/raw`, 17336 fichiers aux sha256 conformes (0 hors journal).
- Test de restauration : `C:/fp_restauration/raw`, 17336 fichiers conformes.
- Durées : raw_check 201 s, sauvegarde 628 s, restauration 311 s.

## Dernier rafraîchissement du 19 octobre et quota du jour

- Séquence : remise en file de la liste de la Liga (`requeue`), `refresh --season 2026`, puis `run --max-requests 300`. Coût simulé : au plus 70 requêtes ; **70 requêtes envoyées**, 24 tâches dérivées (lots de détails) ajoutées et traitées pendant le `run`.
- Quota du jour : 70 requêtes sur le plafond de 450 fixé pour la session. Le compteur de quota renvoyé par l'API n'est pas monotone pendant le `run` (7 451 puis 7 499, 7 479 à la fin) : le nombre de référence est celui du journal de requêtes.
- À la fin : 0 tâche `pending`, 0 `failed`, 7 `suspect` (les `coachs` ci-dessus).

## Incident de la liste de la Liga

- **12 octobre** : la liste de matchs de la Liga 2026 (tâche n° 83, `fixtures_list`, championnat 140) a échoué avec une erreur 5xx côté API-FOOTBALL (« This is on our side »). `refresh` ignore les tâches `failed`, donc cette liste est restée celle d'avant jusqu'au 19.
- **19 octobre** : remise en file par `requeue --status failed --type fixtures_list`, puis réussite au premier essai (380 résultats). Aucun des trois essais espacés prévus n'a été nécessaire. Le gel n'a donc pas de trou sur la Liga : la liste est à jour et les 87 matchs terminés de la saison 2026 ont leur détail.

## Journal T-60 (ADR-0010, ADR-0017)

Bilan de `t60-report`, lancé après le dernier `refresh`, qui ne lit que les compositions :

| Mesure | Valeur |
|---|---|
| Matchs annoncés et détaillés après coup | 91 (annoncés sans détail : 1) |
| Titulaires comparés | 1 998 |
| Titulaires identiques | 1 997 (99,95 %) |
| Matchs avec au moins un titulaire différent | 1 |

Par championnat : Premier League 418/418, Ligue 1 392/392, Bundesliga 396/396, Serie A 395/396, Liga 396/396.

Critère de l'ADR-0010 (révision si plus de 2 % de titulaires différents) et de l'ADR-0017 (échantillon inutilisable sous 50 matchs) : **non atteint**, avec 0,05 % de titulaires différents et 91 matchs comparés. Aucune limite à signaler de ce chef pour l'évaluation H2. L'échantillon reste petit et n'a pas d'autre usage (ADR-0017).

## Incidents d'exploitation

- Windows a redémarré dans la nuit du 14 octobre (02:21) ; aucune tâche n'était prévue ce jour-là et aucun journal n'est coupé.
- Le `refresh` du 5 octobre a démarré à 08:53 au lieu de 08:00 (cause non établie) ; il s'est terminé normalement.
- Les journaux T-60 contiennent des avertissements `ConnectionError` ou `ReadTimeout` récupérés par la nouvelle tentative automatique ; aucun n'a laissé un match sans composition.
- Toutes les tâches `FootPredictor_*` : dernier résultat 0.

## Compléments du gel

- **Date et heure** : 2026-10-19, résumé `raw_check` généré à 07:42 UTC (09:42 heure de Paris) ; `freeze` a duré 1 160 s au total. Tag : `data-freeze-2026-10`, posé sur `main` après la fusion de ce fichier.
- **Renouvellement automatique de l'abonnement** : à couper par l'utilisateur, action manuelle non vérifiable. L'abonnement se termine le 2026-10-22 à 07:56:53 UTC (ADR-0005).
- **Seconde copie hors de la maison** (facultative, ADR-0006) : non faite.
- **Tâches planifiées** (`creer_taches.py --delete`) : suppression prévue après la pose du tag ; l'état réel est consigné dans `docs/realisation/03_collecte/gel.md` et dans le retour de la session.
