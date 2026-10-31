# Cadrage de la partie 6 — Version intermédiaire (J9) : horizon H2 « avec composition »

- **Date** : 2026-10-31
- **Statut** : décisions D1 à D10 (section 9) toutes retenues telles que recommandées par l'utilisateur le 2026-10-31 ; elles font foi dans l'ADR-0047
- **Fait foi** : ADR-0010 (horizons), ADR-0012 (plis, scellé, test une fois par version), ADR-0013 (qualité du XI), ADR-0020 (collisions), ADR-0028 (porte unique), ADR-0037 (protocole figé), ADR-0039 et ADR-0044 (modèle H1), ADR-0040 (même fonction), ADR-0045 (scellé ouvert à l'inférence seulement)
- **Rapport de cadrage** (instantané, non modifié) : E.2, H (stabilité), I.3 (groupes G4 à G7), I.4 (M6 à M8), I.7, L (jalon J9)

Comme le rapport du 2026-09-24, ce document est un **instantané** : on ne le réécrit pas. Ce qui change ensuite passe par les ADR et `ETAT_PROJET.md`.

## 1. Ce qu'on cherche à savoir

**Question de la partie 6** : *que rapporte la composition officielle (le onze, l'entraîneur sur la feuille de match), au-delà du modèle H1 ?*

La réponse attendue est un chiffre avec son intervalle, publié même s'il est nul. Le rapport (E.2) en fixe les critères de réussite :

1. chaque groupe de variables a un apport mesuré (gain et intervalle), publié dans `docs/` ;
2. une décision argumentée sur la stabilité : variante retenue, ou abandon ;
3. des prédictions live journalisées avant le coup d'envoi pendant au moins 8 journées.

## 2. Point de départ (2026-10-31)

| Élément | État | Source |
|---|---|---|
| Modèle H1 | M3 (Poisson par équipe) sur G0 + G1 + G2, appris sur le top 5 ; **figé** | ADR-0039, ADR-0044 |
| Gain de H1 sur B1 | validation : +0,0179 [+0,0133 ; +0,0226] ; scellé : +0,0189 [+0,0102 ; +0,0282], sur 2 092 matchs | `docs/resultats/test_scelle_h1.md` |
| Protocole | 4 plis 2021-22 à 2024-25, règle de décision mécanique, **inchangé** | ADR-0037, tag `protocole-v1` |
| Scellé | matchs à partir du 2025-07-01, ouverts à `inference/` seulement ; **un second et dernier test** prévu pour H2 | ADR-0012 (règle 5 b), ADR-0045 |
| Hypothèse « onze du détail = onze annoncé à T-60 » | vérifiée : 0,05 % de titulaires différents sur 91 matchs (seuil 2 %) | `docs/DATA_FREEZE.md`, ADR-0017 |
| Live avec composition | **impossible** : l'abonnement est terminé, football-data ne publie pas les compositions | ADR-0010, ADR-0011 |
| Essais d'expériences | 10, dont 0 en échec | `reports/experiments/INDEX.md` |
| Journal prospectif (H1) | 89 prédictions live, non évaluées : leurs scores sont des matchs scellés | ADR-0045 |
| Tests | 688 sans base, 2 ignorés (CI verte, fusion #94) | — |

**Conséquence directe** : **H2 est un horizon de rejeu**. En live, l'application affichera H2 « indisponible : compositions non fournies après la fin de l'abonnement » (ADR-0010).

## 3. Données : couverture mesurée

Décomptes du 2026-10-31 sur la base de travail, en lecture seule. On compte les lignes (match, équipe) des matchs de championnat joués et non exclus, d'origine API. Avant le scellé, on mesure la couverture ; après le 1er juillet 2025, on ne compte que la présence d'une composition (CLAUDE.md).

**Top 5, avant le scellé** (pourcentages des lignes, ou des titulaires pour les quatre dernières colonnes) :

| Saison | Lignes | 11 titulaires | Entraîneur | Formation | Collision (ADR-0020) | Poste | Naissance | Minutes | Note |
|---|---|---|---|---|---|---|---|---|---|
| 2010-11 à 2013-14 | 14 606 | 99,4 à 100 | 0 | 0 | 0 | 0 | 71 à 94 | 0 | 0 |
| 2014-15 | 3 652 | 100 | 0 | 0 | 0 | 17,0 | 97,8 | 0,2 | 0,2 |
| **2015-16** | 3 652 | 100 | **0** | **0** | 0 | 98,2 | 99,9 | 99,9 | 99,8 |
| 2016-17 à 2020-21 | 18 074 | 99,6 à 100 | 98,3 à 99,9 | 99,9 à 100 | 0,03 à 0,57 | 99,0 à 100 | 99,7 à 100 | 99,8 à 100 | 99,7 à 100 |
| 2021-22 à 2024-25 (plis) | 14 342 | 100 | 99,7 à 100 | 99,7 à 100 | **0** | 99,9 à 100 | 100 | 100 | 99,9 à 100 |

**D2** : compositions présentes depuis 2010, mais notes et minutes **partielles jusqu'en 2018-19** (41 % en 2015-16, 68 % en 2016-17, 77 % en 2017-18, 83 % en 2018-19), puis 99 % et plus.

**Scellé (présence seulement)** : 1 755 matchs en 2025-26 et 341 en 2026-27, **tous** avec une composition.

**Ce que cela implique** :

- **Stabilité (G6)** : elle ne lit que les titulaires, présents depuis 2010. Cinq saisons d'historique avant la première ligne d'apprentissage : c'est le groupe le plus simple et le plus sûr.
- **Qualité du XI (G5)** : notes et minutes à partir de 2015-16 seulement. En 2015-16, aucun joueur n'a d'historique de notes : la variable vaudrait la moyenne du poste pour tout le monde. **2015-16 doit servir de rodage** pour G5 (décision D3). Pour un promu avant 2019-20, l'historique en D2 est lacunaire : on retombe sur la moyenne du poste (ADR-0013, règle 3), et on compte ces cas.
- **Entraîneur (G4)** : absent en 2015-16. L'ancienneté est donc **censurée à gauche** : un entraîneur en poste depuis 2010 paraît arrivé en août 2016. Il faut un plafond (par exemple 365 jours), et l'ancienneté n'est fiable qu'à partir de 2017-18 (décision D3).
- **Collisions (ADR-0020)** : 0 % sur les quatre saisons de validation, au plus 0,57 % avant. La scission manuelle, reportée au J9 par l'ADR-0020, n'est **pas nécessaire** (décision D7).

## 4. Périmètre proposé

**Dans la partie 6** :

| Bloc | Contenu | Rapport |
|---|---|---|
| Variables H2 | G6 stabilité (3 variables par équipe, H.7), G5 qualité du XI (3 variables, ADR-0013), G4 entraîneur (2 variables) | H.7, I.3, ADR-0013 |
| Protocole | Extension **pré-enregistrée** de l'ADR-0037 à H2, sans changer les règles : base, ordre des groupes, variantes, hyperparamètres | I.7, ADR-0037 |
| Structures | Poisson régularisé (M6) et boosting à perte de Poisson (M7), revus avec les variables H2 : une comparaison pré-enregistrée chacune | I.4, ADR-0038 (critère de révision) |
| Test scellé H2 | Une seule fois : écart entre H2 et la procédure H1 figée, sur les matchs scellés | ADR-0012, règle 5 b |
| Inférence | H2 en rejeu (API, interface : H1 et H2 côte à côte) ; H2 « indisponible » en live, avec la raison | E.2, ADR-0010, ADR-0040 |
| Après le test | Ouverture du rejeu des saisons scellées ; évaluation du journal prospectif H1 | ADR-0045 |
| Documentation | Résultats générés, chapitre mathématique « stabilité » (forme quadratique, H.3), rapport v2, tag de fin de jalon | E.2, K.2 |

**Hors partie 6, ou en option en fin de partie** (décision D8) :

- **G7 blessures** (`/injuries`) : chargeur reporté (ADR-0027) ; listes révisées après coup, donc risque de fuite ; couverture 2021+ seulement. Les « habituels absents » restent dans G5, calculés à partir des compositions (ADR-0013).
- **Dixon-Coles dynamique (M8)** : le Dixon-Coles statique n'a rien apporté (+0,00002, ADR-0039). Proposé en version avancée.
- **Planification et Compose à trois services** : objectifs pédagogiques du rapport (E.2, F.8), sans lien avec la question de H2. À placer en fin de partie, si le temps le permet.
- **Onze probable** : écarté (ADR-0010, rapport H.9).

## 5. Architecture proposée

Le principe : **ne rien changer à H1**. Le modèle final H1 relit les classes de `modeling/` à chaque chargement (ADR-0044), et les colonnes H1 du jeu de données doivent rester identiques au bit près.

1. **Porte** (ADR-0028) : `features/sources.py` gagne une fonction de lecture des compositions et des statistiques joueurs (`load_lineups`, nom indicatif). Elle filtre le scellé **dans la requête SQL**, par la date du match, comme `load_matches`. Le test d'architecture s'étend : aucun autre module ne lit `staging.lineup`, `staging.player_match_stats` ni `staging.player`.
2. **Variables** : un module de fonctions pures par groupe, sans base (`features/lineup_stability.py`, `features/xi_quality.py`, `features/coach.py`, noms indicatifs). Pour le match *m* : composition de *m* (connue à T-60) et historique **strictement antérieur au jour de m** (règle temporelle de l'ADR-0010).
3. **Jeu de données** : `build_frame` reste inchangé pour H1. Les colonnes H2 se calculent à part et se joignent sur (match, équipe). On contrôle que les colonnes H1 d'un nouveau jeu sont identiques à celles de `ds-2026-10-22-bf786ef1` (même méthode qu'en 3.11).
4. **Registre** : groupes G4 à G6 et horizon H2 acceptés (aujourd'hui, `registry.py` refuse toute variable non H1). **Garde** : un modèle d'horizon H1 refuse toute variable H2 (ADR-0010), testé.
5. **Inférence** (ADR-0040, « même fonction ») : en rejeu, les variables H2 d'un jour viennent des mêmes fonctions, appelées sur l'historique tronqué et la composition du match. L'API cesse de répondre 501 pour `horizon=H2` en rejeu ; en live, la réponse est « indisponible », avec la raison.
6. **Aucune nouvelle dépendance** : `HistGradientBoostingRegressor(loss="poisson")` et `PoissonRegressor` sont dans scikit-learn, déjà présent.
7. **Aucun `load`** n'est nécessaire : compositions, entraîneurs, formations, statistiques joueurs et profils sont déjà dans `staging` (ADR-0027).

## 6. Protocole de H2 (extension pré-enregistrée de l'ADR-0037)

L'ADR-0037 ne change pas : mêmes plis, métriques, bootstrap par blocs (10 000 rééchantillonnages, graine 20260930), règle de décision à trois conditions, intersection des matchs, aucun remplissage silencieux. L'ADR-0047 ajoute seulement ce que l'ADR-0037 ne pouvait pas prévoir, **avant tout calcul de variable H2 sur les plis** :

1. **Base** : le modèle H1 retenu (M3, G0 + G1 + G2, top 5, demi-vie de G2 par validation interne).
2. **Ajouts cumulatifs, dans un ordre fixé d'avance** (décision D1). Proposition : **G6 → G5 → G4**, du groupe le plus sûr au plus fragile (section 3). Chaque groupe s'ajoute au modèle retenu juste avant lui, et la règle de l'ADR-0037 s'applique telle quelle.
3. **Diagnostic, sans pouvoir de décision** : chaque groupe ajouté **seul** à la base. On sait ainsi si l'ordre a pesé.
4. **Variantes et hyperparamètres** (décision D2) : la demi-vie de la cohésion (H.7 : 3, 5, 10, 20 matchs ou ∞) se choisit par **validation interne** du pli, comme celle de G2. Les autres variantes de stabilité du rapport (H.8 : remise à zéro, historique intégral, fenêtre de 10) sont mesurées en **diagnostic publié**, sans choix sur les plis de test. On évite ainsi de choisir la meilleure de neuf variantes sur les plis qui servent à juger.
5. **Au plus 3 variables par équipe et par groupe** dans la première expérience (rapport H.6, ADR-0013).
6. **Diagnostics propres à H2** : gain par tranche de journées (tranches de l'ADR-0037 : 1-5, 6-10, 11-19, 20 et plus), qui vérifie l'intuition du rapport (H.4) ; corrélation des variables de stabilité entre elles (H.3 annonce plus de 0,9 entre paires et recouvrement) ; nombre de lignes à valeur manquante par groupe et par pli.
7. **Structures** (décision D4) : une fois les groupes choisis, deux comparaisons pré-enregistrées sur le jeu H2 retenu : M3 contre M6 (ridge), puis le retenu contre M7 (boosting). À gain non significatif, on garde le plus simple (ADR-0037).
8. **Tous les essais sont conservés** : la partie 6 part de 10 essais, et l'index en donnera le nombre final.

## 7. Test scellé H2 (ADR-0012, règle 5 b)

**Ce qu'il mesure** : uniquement l'écart entre H2 et le **modèle H1 déjà figé**, sur les matchs de championnat du top 5 joués entre le 1er juillet 2025 et le gel.

**Points à trancher avant le tag de la liste** (décision D5) :

1. **Quel « H1 figé » ?** Le modèle final H1 (`…-avec-scelle`, ADR-0044) a appris sur les matchs scellés : il ne peut pas servir de référence sur ces mêmes matchs. La référence est donc la **procédure H1 du premier test** (`experiments/scelle_h1.yaml` : apprentissage sur 2015-16 à 2024-25, validation interne sur 2024-25). Sa reproduction a déjà été vérifiée : le sha256 des prédictions était identique entre les deux lancements (ADR-0043). H2 suit la même procédure.
2. **Liste** : `[M3_G0G2, H2]` comme **seule comparaison de décision** ; B1 et le marché avant clôture publiés en contexte, sans décision.
3. **Puissance, dite d'avance** : sur environ 2 100 matchs, un intervalle est à peu près 1,85 fois plus large que sur les 7 156 matchs de validation (√(7 156 / 2 096)). Un gain de la taille de celui de G2 (+0,0092 ± 0,0035 en validation) aurait environ ± 0,0065 sur le scellé. **Un gain H2 inférieur à environ 0,007 sortira probablement non significatif sur le scellé**, même s'il est réel. Le résultat sera publié tel quel ; la conclusion principale viendra de la validation glissante (7 156 matchs), le scellé la confirmant ou non.
4. **Préventions d'E-059 et d'E-060** : chaque fichier d'expérience passe par l'encodeur du rapport, et le vrai fichier du test est répété sur données synthétiques avant le tag ; la ligne « règle de décision » est « non applicable » sous 3 plis (corrigé par la PR #92).
5. **Ce que l'utilisateur a vu des matchs scellés** (ADR-0045) : les variables du live, agrégées, et les métriques publiées du test H1. Aucun score match par match, aucune cote. L'ADR du test H2 le rappellera.
6. **Tag `pre-scelle-h2`**, puis gel des chemins `modeling/`, `features/`, `experiments/` jusqu'au test, comme pour H1.

**Après le test** :

- **Pas de modèle final H2 avec les matchs scellés** (décision D6) : sans live H2, il ne servirait à rien. En rejeu des saisons scellées, le modèle « du pli » de 2025-26 et 2026-27 est justement celui du test, appris jusqu'en 2024-25.
- **Nouvelle ADR** : ouverture du rejeu des saisons scellées (ADR-0045) et évaluation du journal prospectif H1 (89 prédictions et plus).

## 8. Plan en sous-étapes (proposition)

Rapport L : J9, environ 120 heures. Phase A sans aucun accès au scellé ; phase B pour le test.

| Étape | Contenu | Branche (indicative) | Heures |
|---|---|---|---|
| **6.0** | Ce cadrage ; ADR-0047 (protocole H2, ordre des groupes, test scellé H2) | `docs/06-cadrage-h2` | 4 |
| 6.1 | Porte des compositions et des statistiques joueurs ; registre G4 à G6 et H2 ; garde « modèle H1 sans variable H2 » ; tests d'architecture | `feat/06-porte-compositions` | 8 |
| 6.2 | G6 stabilité : `xi_overlap_prev`, `xi_cohesion_ewm`, `xi_new_starters` ; test « matrice = recouvrement » (H.3) ; tests anti-fuite (*m* − 1) | `feat/06-stabilite` | 12 |
| 6.3 | G5 qualité du XI : note rétrécie vers la moyenne du poste, habituels absents, âge moyen ; règle entre championnats (ADR-0013, règle 4) | `feat/06-qualite-xi` | 14 |
| 6.4 | G4 entraîneur : ancienneté plafonnée, « nouvel entraîneur » ; censure à gauche documentée | `feat/06-entraineur` | 6 |
| 6.5 | Jeu de données H2 versionné ; colonnes H1 identiques à `bf786ef1` ; `check --invariance` | `data/06-jeu-h2` | 6 |
| 6.6 | Exploration (notebook) : distributions, début de saison, corrélations entre variantes | `docs/07-exploration-h2` | 6 |
| 6.7 | Expériences : ablations H2 (D1), diagnostics « seul », variantes de stabilité (D2), tranches de journées | `exp/09-ablations-h2` | 12 |
| 6.8 | Structures M6 et M7 sur le jeu H2 (D4) | `exp/09-structures-h2` | 10 |
| 6.9 | Modèle H2 retenu (ADR) ; liste du test scellé ; répétition sur données synthétiques ; tag `pre-scelle-h2` | `docs/10-modele-h2` | 6 |
| 6.10 | Inférence H2 en rejeu : API (`horizon=H2`), interface (H1 et H2 côte à côte, page « apport des variables ») | `feat/11-h2-rejeu` | 14 |
| 6.11 | Clôture de la phase A (retour, état) | `docs/06-cloture-partie-6a` | 2 |
| **Phase B** | | | |
| 6.12 | Test scellé H2, une fois ; publication telle quelle | `exp/10-test-scelle-h2` | 4 |
| 6.13 | ADR d'ouverture du rejeu des saisons scellées ; évaluation du journal prospectif | `feat/11-ouverture-rejeu` | 6 |
| 6.14 | Documents LaTeX (stabilité, qualité du XI, résultats H2), rapport v2 ; tag de fin de J9 | `docs/16-rapport-v2` | 8 |
| Option | Compose à trois services, planification du live (D8) | — | 10 à 15 |

Total hors option : **environ 118 heures**, cohérent avec le rapport (L).

## 9. Décisions à prendre

Chaque décision a une recommandation ; les choix retenus vont dans l'ADR-0047.

| N° | Question | Options | Recommandation |
|---|---|---|---|
| **D1** | Ordre des ajouts cumulatifs | a. G6 → G5 → G4 (du plus sûr au plus fragile) ; b. G4 → G5 → G6 (numérotation du rapport) ; c. un seul bloc « composition » (G5 + G6) | **a**, avec le diagnostic « chaque groupe seul » |
| **D2** | Variantes de stabilité (H.8) | a. demi-vie par validation interne, autres variantes en diagnostic ; b. expérience H.8 complète, avec la règle « la plus simple, pas significativement moins bonne que la meilleure », sur les plis | **a** : neuf variantes jugées sur les plis de test donneraient un gain optimiste |
| **D3** | Rodage des groupes à historique court | a. G5 : 2015-16 en rodage (apprentissage à partir de 2016-17) ; G4 : ancienneté plafonnée à 365 jours, apprentissage à partir de 2017-18 ; b. pas de rodage, lignes exclues et comptées seulement | **a**, annoncé avant le calcul |
| **D4** | Structures avec H2 | a. M6 puis M7, une comparaison chacune ; b. M6 seul ; c. aucune | **a** : objectif pédagogique d'E.2, sans nouvelle dépendance |
| **D5** | Référence du test scellé H2 | a. procédure H1 du premier test (2015-16 à 2024-25), seule comparaison de décision ; b. modèle final H1 (impossible : il a vu ces matchs) | **a** |
| **D6** | Modèle final H2 appris avec les matchs scellés | a. non (pas de live H2) ; b. oui, par symétrie avec H1 | **a** |
| **D7** | Scission des collisions (ADR-0020, reportée au J9) | a. non : 0 % sur les plis de validation ; b. oui, pour les joueurs à fort temps de jeu | **a** |
| **D8** | Compose et planification | a. en option, à la fin de la partie 6 ; b. dans la phase A ; c. reportés à la version avancée | **a**. La planification d'une collecte demande une autorisation durable de ta part, à écrire dans une ADR, alors qu'aujourd'hui tu donnes ton accord à chaque collecte |
| **D9** | Notes des joueurs venus d'un championnat hors du périmètre (ADR-0013, règle 4) | a. moyenne du poste, comptée ; b. notes du championnat d'origine, corrigées d'un écart moyen par championnat | **a** pour la première expérience ; b en diagnostic si plus de 10 % des titulaires sont concernés |
| **D10** | Allègement de `CLAUDE.md` (consignes de la partie 5 sur les chemins figés, sans objet depuis `v0.5.0`) | a. PR de documentation au début de la partie 6 ; b. plus tard | **a**, dans une PR séparée : les consignes « chemins figés » reviendront avec `pre-scelle-h2` |

## 10. Risques et limites, dits d'avance

- **Gain probablement petit** : l'Elo et les moyennes glissantes résument déjà la force des équipes. Le rapport (H.3) prévoit que les variantes de stabilité seront très corrélées entre elles. Un résultat nul est un résultat, et il sera publié (ADR-0013, règle 5).
- **Puissance du test scellé** limitée (section 7).
- **Rejeu seulement** : H2 ne sert jamais en live sans réabonnement (décision M28, reportée). Sa valeur est d'**expliquer** : ce que la composition change, match par match.
- **Notes API** : calculées après le match par le fournisseur, selon une formule inconnue et peut-être révisée ; on n'utilise que les notes de matchs antérieurs, mais leur stabilité dans le temps n'est pas vérifiable (rapport I.8).
- **Censure de l'ancienneté** de l'entraîneur avant 2016-17 (section 3).
- **Comparaisons multiples** : l'ordre fixé, la validation interne et le nombre d'essais publié les limitent, sans les supprimer.
