# Contrôle du référentiel (J3) — 2026-09-30

Produit par `python -m foot_predictor.ingestion check-referentiel`. Chiffres seulement : aucun nom ni identifiant de joueur, aucun score (ADR-0012). Décisions : ADR-0008, ADR-0009, ADR-0020, ADR-0023.

## 1. Dernier chargement

- `ops.load_run` n° 5, 2026-09-30 07:22 UTC, commit `f2db877`, durée 777.8 s.

| Table | Lignes |
|---|---|
| coach | 3 622 |
| coach_source_mapping | 0 |
| competition | 30 |
| competition_source_mapping | 10 |
| lineup | 3 984 757 |
| match | 167 876 |
| match_odds | 120 983 |
| match_source_mapping | 102 397 |
| player | 67 012 |
| player_injury | 0 |
| player_match_stats | 2 831 343 |
| player_source_mapping | 0 |
| season | 498 |
| team | 3 267 |
| team_match | 335 752 |
| team_match_stats | 168 640 |
| team_match_stats_external | 204 794 |
| team_source_mapping | 387 |

## 2. Identité des joueurs (ADR-0008, règle 1)

- Verdict : **OK** — chaque joueur de composition correspond à une seule entité interne, créée depuis un identifiant API.
- Joueurs : 67012 ; identifiants API distincts : 67012 ; sans identifiant API : 0.
- (match, joueur) en double dans les compositions : 0 ; joueur chez deux équipes dans un même match : 0.
- Entrées sans identifiant (0 ou absent), non créées : 1007 (compositions), 1680 (statistiques).

## 3. Appariement football-data (ADR-0008, règle 2)

- Période couverte par l'API : **56715 / 56729 lignes appariées (99.98 %)** ; seuil 99.5 % : **OK**.
- Hors couverture API : 45682 matchs créés par football-data ; 80 équipes « hors_api ».
- Écarts de score entre sources (avant le 1er juillet 2025 seulement) : 4 sur 52367 comparés.

| Division | Appariées | Lignes | Taux |
|---|---|---|---|
| D1 | 4932 | 4932 | 100.00 % |
| D2 | 4640 | 4644 | 99.91 % |
| E0 | 6130 | 6130 | 100.00 % |
| E1 | 8375 | 8375 | 100.00 % |
| F1 | 5802 | 5802 | 100.00 % |
| F2 | 5884 | 5894 | 99.83 % |
| I1 | 6130 | 6130 | 100.00 % |
| I2 | 3976 | 3976 | 100.00 % |
| SP1 | 6149 | 6149 | 100.00 % |
| SP2 | 4697 | 4697 | 100.00 % |

Saisons sous 100 % :

| Division:saison | Appariées | Lignes |
|---|---|---|
| D2:2012 | 302 | 306 |
| F2:2010 | 370 | 380 |

Matchs football-data non appariés : 14 avant le scellé (listés), 0 après (décompte seul).

| Division | Saison | Date | Domicile | Extérieur | Raison |
|---|---|---|---|---|---|
| D2 | 2012 | 2012-08-31 | FC Koln | Cottbus | aucun match API à ± 1 jour |
| D2 | 2012 | 2012-09-01 | St Pauli | Sandhausen | aucun match API à ± 1 jour |
| D2 | 2012 | 2012-10-26 | Ingolstadt | Aalen | aucun match API à ± 1 jour |
| D2 | 2012 | 2012-11-16 | Munich 1860 | FC Koln | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Angers | Dijon | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Clermont | Boulogne | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Evian Thonon Gaillard | Metz | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Istres | Chateauroux | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Laval | Reims | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Le Havre | Grenoble | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Le Mans | Nantes | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Nimes | Ajaccio | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Sedan | Tours | aucun match API à ± 1 jour |
| F2 | 2010 | 2011-05-27 | Troyes | Vannes | aucun match API à ± 1 jour |

## 4. Collisions : entrées exclues (ADR-0020)

- Entrées exclues : 809 dans les compositions, 926 dans les statistiques ; résolues par le numéro de la composition (2b) : 38.
- Identifiants en collision « même jour » : 26 ; « deux naissances » : 3.
- **Critères de révision** :
  - matchs de championnat du top 5 avec au moins une entrée de composition exclue : 41 sur 29170 (0.14 % ; seuil : 1 %) ;
  - joueur-saisons du top 5 (au moins 10 titularisations) qui perdent plus de 10 % de leurs titularisations : 4 (au plus 25.0 %) ; à réexaminer au J9 (ADR-0020).

Championnats du top 5 : saisons avec au moins une entrée exclue ou un titulaire inconnu, puis total par championnat (toutes saisons).

| Championnat | Saison | Matchs | Matchs avec exclusion | Entrées exclues | Titulaires inconnus |
|---|---|---|---|---|---|
| Premier League | 2018 | 380 | 4 | 8 | 0 |
| Premier League | 2019 | 380 | 1 | 2 | 0 |
| Premier League | 2025 | 380 | 1 | 4 | 0 |
| Ligue 1 | 2017 | 380 | 1 | 2 | 0 |
| Ligue 1 | 2018 | 380 | 2 | 4 | 0 |
| Ligue 1 | 2019 | 380 | 1 | 1 | 0 |
| Bundesliga | 2018 | 308 | 3 | 3 | 0 |
| Serie A | 2016 | 380 | 12 | 23 | 0 |
| Serie A | 2018 | 380 | 8 | 16 | 0 |
| Serie A | 2019 | 380 | 4 | 8 | 0 |
| La Liga | 2018 | 380 | 4 | 6 | 0 |
| La Liga | 2019 | 380 | 0 | 0 | 1 |
| La Liga | 2020 | 380 | 3 | 3 | 0 |
| La Liga | 2025 | 380 | 2 | 3 | 0 |
| **Premier League** | total | 10260 | 6 | 14 | 0 |
| **Ligue 1** | total | 9826 | 4 | 7 | 0 |
| **Bundesliga** | total | 8278 | 3 | 3 | 0 |
| **Serie A** | total | 9965 | 24 | 47 | 0 |
| **La Liga** | total | 10260 | 9 | 12 | 1 |

## 5. Par compétition : titulaires inconnus, matchs sans composition, exclusions (ADR-0009)

Matchs terminés sans composition : attendu dans les coupes (seuls les matchs d'une équipe suivie ont un détail) et dans les saisons anciennes sans compositions.

| Compétition (league.id) | Type | Matchs | dont hors API | Terminés (API) | Terminés sans composition | Titulaires inconnus | Entrées exclues | Matchs exclus (ADR-0009) |
|---|---|---|---|---|---|---|---|---|
| UEFA Champions League (2) | cup | 2697 | 0 | 2571 | 1185 | 0 | 0 | 0 |
| UEFA Europa League (3) | cup | 4100 | 0 | 3971 | 2623 | 7 | 2 | 3 |
| Premier League (39) | league | 10260 | 3800 | 6130 | 10 | 0 | 14 | 0 |
| Championship (40) | league | 14980 | 6072 | 8450 | 1 | 0 | 6 | 1 |
| FA Cup (45) | cup | 7623 | 0 | 7560 | 6818 | 0 | 0 | 19 |
| League Cup (48) | cup | 1105 | 0 | 1094 | 241 | 0 | 3 | 3 |
| Ligue 1 (61) | league | 9826 | 3652 | 5810 | 1 | 0 | 7 | 103 |
| Ligue 2 (62) | league | 10048 | 3800 | 5903 | 94 | 60 | 4 | 102 |
| Coupe de France (66) | cup | 2132 | 0 | 2131 | 1304 | 48 | 4 | 1 |
| Serie A (71) | league | 4560 | 0 | 4456 | 0 | 0 | 740 | 1 |
| Bundesliga (78) | league | 8278 | 3060 | 4948 | 0 | 0 | 3 | 0 |
| 2. Bundesliga (79) | league | 8272 | 3366 | 4654 | 0 | 0 | 28 | 0 |
| DFB Pokal (81) | cup | 741 | 0 | 725 | 0 | 0 | 13 | 0 |
| Eredivisie (88) | league | 3774 | 0 | 3457 | 0 | 0 | 25 | 74 |
| Primeira Liga (94) | league | 3684 | 0 | 3440 | 0 | 0 | 27 | 0 |
| Superliga (119) | league | 2460 | 0 | 2382 | 0 | 1 | 0 | 0 |
| Liga Profesional Argentina (128) | league | 4874 | 0 | 4784 | 0 | 0 | 296 | 0 |
| Serie A (135) | league | 9965 | 3504 | 6131 | 1 | 0 | 47 | 0 |
| Serie B (136) | league | 11628 | 7236 | 4061 | 1 | 0 | 11 | 1 |
| Coppa Italia (137) | cup | 638 | 0 | 630 | 106 | 4 | 7 | 0 |
| La Liga (140) | league | 10260 | 3800 | 6149 | 0 | 1 | 12 | 0 |
| Segunda División (141) | league | 12532 | 7392 | 4750 | 21 | 1 | 368 | 0 |
| Copa del Rey (143) | cup | 1029 | 0 | 1014 | 251 | 0 | 19 | 0 |
| Jupiler Pro League (144) | league | 3600 | 0 | 3346 | 2 | 58 | 0 | 11 |
| Premiership (179) | league | 2712 | 0 | 2537 | 0 | 1 | 7 | 19 |
| Süper Lig (203) | league | 4006 | 0 | 3753 | 28 | 0 | 12 | 0 |
| Super League (207) | league | 2090 | 0 | 2012 | 0 | 0 | 22 | 0 |
| Bundesliga (218) | league | 2234 | 0 | 2144 | 0 | 0 | 0 | 0 |
| Major League Soccer (253) | league | 5329 | 0 | 5203 | 0 | 141 | 50 | 15 |
| UEFA Europa Conference League (848) | cup | 2439 | 0 | 2331 | 2038 | 0 | 8 | 0 |

Matchs exclus par motif : annule 345, tapis_vert 8.


## 6. Tirs de football-data et d'API-FOOTBALL (ADR-0029)

Matchs de championnat terminés, non exclus, rattachés à football-data, **avant le 01/07/2025** (scellé, ADR-0012). « Complet » : tirs et tirs cadrés des deux équipes. Écart moyen absolu : par équipe et par match, sur les matchs communs.

| Championnat | Matchs | football-data complet | API complet | Communs | Identiques | Écart tirs | Écart cadrés |
|---|---|---|---|---|---|---|---|
| Premier League (39) | 9500 | 100.00 % | 40.02 % | 3802 | 90.93 % | 0.05 | 0.02 |
| Championship (40) | 13800 | 99.99 % | 39.63 % | 5469 | 86.73 % | 0.09 | 0.03 |
| Ligue 1 (61) | 9102 | 80.73 % | 39.00 % | 3550 | 80.90 % | 0.11 | 0.04 |
| Ligue 2 (62) | 9314 | 30.73 % | 34.66 % | 2862 | 66.39 % | 0.54 | 0.21 |
| Bundesliga (78) | 7650 | 83.99 % | 39.99 % | 3058 | 42.12 % | 0.45 | 0.16 |
| 2. Bundesliga (79) | 7646 | 41.87 % | 40.32 % | 2446 | 23.59 % | 0.70 | 0.23 |
| Serie A (135) | 9204 | 82.41 % | 41.26 % | 3798 | 56.24 % | 1.04 | 0.32 |
| Serie B (136) | 10782 | 28.58 % | 32.56 % | 3058 | 63.70 % | 0.75 | 0.27 |
| La Liga (140) | 9500 | 80.00 % | 40.16 % | 3815 | 83.98 % | 0.10 | 0.04 |
| Segunda División (141) | 11550 | 31.82 % | 35.78 % | 3672 | 61.90 % | 0.29 | 0.07 |

| Championnat | Matchs | football-data complet | API complet | Communs | Identiques | Écart tirs | Écart cadrés |
|---|---|---|---|---|---|---|---|
| Total | 98048 | 66.37 % | 38.19 % | 35530 | 68.67 % | 0.38 | 0.13 |

Première saison avec des tirs football-data : Premier League 2000-01, Championship 2000-01, Ligue 1 2005-06, Ligue 2 2017-18, Bundesliga 2000-01, 2. Bundesliga 2000-01, Serie A 2005-06, Serie B 2017-18, La Liga 2005-06, Segunda División 2017-18.

## 7. Cotes plus/moins 2,5 de football-data (ADR-0036)

Matchs de championnat du top 5 terminés et non exclus. Part des matchs avec une cote « avant clôture » (et, parmi eux, colonne retenue : moyenne de marché `Avg`, agrégat BetBrain `BbAv`, un bookmaker) et avec une cote de clôture. Après le 01/07/2025 : **présence seulement** (scellé, ADR-0012).

| Championnat | Saison | Matchs | Avant clôture | dont Avg | dont BbAv | dont un bookmaker | Clôture |
|---|---|---|---|---|---|---|---|
| Premier League (39) | 2000-01 | 380 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| Premier League (39) | 2001-02 | 380 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| Premier League (39) | 2002-03 | 380 | 99.74 % | 0 | 0 | 379 | 0.00 % |
| Premier League (39) | 2003-04 | 380 | 100.00 % | 0 | 0 | 380 | 0.00 % |
| Premier League (39) | 2004-05 | 380 | 99.74 % | 0 | 0 | 379 | 0.00 % |
| Premier League (39) | 2005-06 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2006-07 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2007-08 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2008-09 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2009-10 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2010-11 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2011-12 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2012-13 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2013-14 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2014-15 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2015-16 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2016-17 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2017-18 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2018-19 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Premier League (39) | 2019-20 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Premier League (39) | 2020-21 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Premier League (39) | 2021-22 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Premier League (39) | 2022-23 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Premier League (39) | 2023-24 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Premier League (39) | 2024-25 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Premier League (39) | 2025-26 (scellé) | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Premier League (39) | 2026-27 (scellé) | 50 | 100.00 % | 50 | 0 | 0 | 100.00 % |
| Ligue 1 (61) | 2000-01 | 306 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| Ligue 1 (61) | 2001-02 | 306 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| Ligue 1 (61) | 2002-03 | 380 | 96.84 % | 0 | 0 | 368 | 0.00 % |
| Ligue 1 (61) | 2003-04 | 380 | 95.79 % | 0 | 0 | 364 | 0.00 % |
| Ligue 1 (61) | 2004-05 | 380 | 97.89 % | 0 | 0 | 372 | 0.00 % |
| Ligue 1 (61) | 2005-06 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2006-07 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2007-08 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2008-09 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2009-10 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2010-11 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2011-12 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2012-13 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2013-14 | 379 | 100.00 % | 0 | 379 | 0 | 0.00 % |
| Ligue 1 (61) | 2014-15 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2015-16 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2016-17 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2017-18 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2018-19 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Ligue 1 (61) | 2019-20 | 279 | 100.00 % | 279 | 0 | 0 | 100.00 % |
| Ligue 1 (61) | 2020-21 | 382 | 99.48 % | 380 | 0 | 0 | 99.48 % |
| Ligue 1 (61) | 2021-22 | 382 | 99.48 % | 380 | 0 | 0 | 99.48 % |
| Ligue 1 (61) | 2022-23 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Ligue 1 (61) | 2023-24 | 308 | 99.35 % | 306 | 0 | 0 | 99.35 % |
| Ligue 1 (61) | 2024-25 | 308 | 99.35 % | 306 | 0 | 0 | 99.35 % |
| Ligue 1 (61) | 2025-26 (scellé) | 307 | 99.35 % | 305 | 0 | 0 | 99.35 % |
| Ligue 1 (61) | 2026-27 (scellé) | 45 | 100.00 % | 45 | 0 | 0 | 100.00 % |
| Bundesliga (78) | 2000-01 | 306 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| Bundesliga (78) | 2001-02 | 306 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| Bundesliga (78) | 2002-03 | 306 | 99.67 % | 0 | 0 | 305 | 0.00 % |
| Bundesliga (78) | 2003-04 | 306 | 97.06 % | 0 | 0 | 297 | 0.00 % |
| Bundesliga (78) | 2004-05 | 306 | 99.35 % | 0 | 0 | 304 | 0.00 % |
| Bundesliga (78) | 2005-06 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2006-07 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2007-08 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2008-09 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2009-10 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2010-11 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2011-12 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2012-13 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2013-14 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2014-15 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2015-16 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2016-17 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2017-18 | 306 | 100.00 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2018-19 | 308 | 99.35 % | 0 | 306 | 0 | 0.00 % |
| Bundesliga (78) | 2019-20 | 308 | 99.35 % | 306 | 0 | 0 | 99.35 % |
| Bundesliga (78) | 2020-21 | 308 | 99.35 % | 306 | 0 | 0 | 99.35 % |
| Bundesliga (78) | 2021-22 | 308 | 99.35 % | 306 | 0 | 0 | 99.35 % |
| Bundesliga (78) | 2022-23 | 308 | 99.35 % | 306 | 0 | 0 | 99.35 % |
| Bundesliga (78) | 2023-24 | 308 | 99.35 % | 306 | 0 | 0 | 99.35 % |
| Bundesliga (78) | 2024-25 | 308 | 99.35 % | 306 | 0 | 0 | 99.35 % |
| Bundesliga (78) | 2025-26 (scellé) | 308 | 99.35 % | 306 | 0 | 0 | 99.35 % |
| Bundesliga (78) | 2026-27 (scellé) | 36 | 100.00 % | 36 | 0 | 0 | 100.00 % |
| Serie A (135) | 2000-01 | 306 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| Serie A (135) | 2001-02 | 306 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| Serie A (135) | 2002-03 | 306 | 94.44 % | 0 | 0 | 289 | 0.00 % |
| Serie A (135) | 2003-04 | 306 | 95.10 % | 0 | 0 | 291 | 0.00 % |
| Serie A (135) | 2004-05 | 380 | 93.16 % | 0 | 0 | 354 | 0.00 % |
| Serie A (135) | 2005-06 | 380 | 99.74 % | 0 | 379 | 0 | 0.00 % |
| Serie A (135) | 2006-07 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2007-08 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2008-09 | 380 | 99.74 % | 0 | 379 | 0 | 0.00 % |
| Serie A (135) | 2009-10 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2010-11 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2011-12 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2012-13 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2013-14 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2014-15 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2015-16 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2016-17 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2017-18 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2018-19 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| Serie A (135) | 2019-20 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Serie A (135) | 2020-21 | 380 | 99.74 % | 379 | 0 | 0 | 100.00 % |
| Serie A (135) | 2021-22 | 380 | 99.74 % | 379 | 0 | 0 | 100.00 % |
| Serie A (135) | 2022-23 | 381 | 99.74 % | 380 | 0 | 0 | 99.74 % |
| Serie A (135) | 2023-24 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Serie A (135) | 2024-25 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Serie A (135) | 2025-26 (scellé) | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| Serie A (135) | 2026-27 (scellé) | 50 | 100.00 % | 50 | 0 | 0 | 100.00 % |
| La Liga (140) | 2000-01 | 380 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| La Liga (140) | 2001-02 | 380 | 0.00 % | 0 | 0 | 0 | 0.00 % |
| La Liga (140) | 2002-03 | 380 | 94.21 % | 0 | 0 | 358 | 0.00 % |
| La Liga (140) | 2003-04 | 380 | 96.58 % | 0 | 0 | 367 | 0.00 % |
| La Liga (140) | 2004-05 | 380 | 100.00 % | 0 | 0 | 380 | 0.00 % |
| La Liga (140) | 2005-06 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2006-07 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2007-08 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2008-09 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2009-10 | 380 | 99.74 % | 0 | 379 | 0 | 0.00 % |
| La Liga (140) | 2010-11 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2011-12 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2012-13 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2013-14 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2014-15 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2015-16 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2016-17 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2017-18 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2018-19 | 380 | 100.00 % | 0 | 380 | 0 | 0.00 % |
| La Liga (140) | 2019-20 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| La Liga (140) | 2020-21 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| La Liga (140) | 2021-22 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| La Liga (140) | 2022-23 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| La Liga (140) | 2023-24 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| La Liga (140) | 2024-25 | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| La Liga (140) | 2025-26 (scellé) | 380 | 100.00 % | 380 | 0 | 0 | 100.00 % |
| La Liga (140) | 2026-27 (scellé) | 69 | 100.00 % | 69 | 0 | 0 | 100.00 % |

Période d'apprentissage et de validation (2015-16 à 2024-25) : 18034 matchs ; avant clôture 99.86 %, clôture 59.37 %. Aucune cote de clôture avant 2019-20 dans les fichiers.
