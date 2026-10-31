# ADR-0047 — Horizon H2 : périmètre, protocole pré-enregistré et test scellé de la version intermédiaire

- **Statut** : acceptée
- **Date** : 2026-10-31
- **Référence** : `docs/cadrage/cadrage_partie-6_h2_2026-10-31.md` ; rapport de cadrage, E.2, H.3 à H.8, I.3, I.4, I.7, L (J9) ; ADR-0010, ADR-0012 (règle 5 b), ADR-0013, ADR-0020, ADR-0027, ADR-0028, ADR-0037, ADR-0038, ADR-0039, ADR-0040, ADR-0043, ADR-0044, ADR-0045

## Contexte

- **Le MVP est terminé** (tag `v1.0.0`). Le modèle H1 (M3 sur G0 + G1 + G2) est figé (ADR-0039, ADR-0044). L'ADR-0012 prévoit un **second et dernier** test sur les matchs scellés, pour la version intermédiaire : il mesure l'écart entre H2 et le modèle H1 figé.
- **L'ADR-0037 a figé le protocole** avant toute évaluation, mais pour les groupes G0 à G3 seulement. Elle ne dit rien de l'ordre des groupes G4 à G6, des variantes de stabilité ni de la référence du second test. Il faut l'écrire **avant** de calculer la moindre variable H2 sur les plis, pour la même raison qu'en partie 4 : sans règle écrite d'avance, on choisit après coup ce qui arrange.
- **Données** (décomptes du 2026-10-31, cadrage, section 3) :
  - titulaires du top 5 présents depuis 2010 ;
  - notes et minutes à partir de 2015-16 ;
  - entraîneur et formation à partir de 2016-17 (absents en 2015-16) ;
  - collisions de l'ADR-0020 : 0 % sur les quatre saisons de validation ;
  - matchs scellés : tous ont une composition.
- **H2 ne fonctionne qu'en rejeu** : l'abonnement est terminé, et football-data ne publie pas les compositions (ADR-0010, ADR-0011).
- **Puissance** : sur environ 2 100 matchs scellés, un intervalle est environ 1,85 fois plus large qu'en validation (7 156 matchs). Un gain inférieur à environ 0,007 de log-loss sortira probablement non significatif sur le scellé.

## Options envisagées

Le détail des options, décision par décision, est dans le cadrage (section 9). Pour l'ensemble :

1. **Appliquer l'ADR-0037 telle quelle, sans précision** : l'ordre des groupes, les variantes et la référence du second test se décideraient au fil des résultats.
2. **Compléter l'ADR-0037 par une extension pré-enregistrée pour H2**, sans changer aucune de ses règles : base, ordre, variantes, rodage, structures, test scellé.

## Décision

Option 2, avec les recommandations D1 à D10 du cadrage, toutes choisies par l'utilisateur le 2026-10-31. Rien de l'ADR-0037 ne change : plis, métriques, bootstrap par blocs, règle de décision à trois conditions, intersection des matchs, aucun remplissage silencieux. On ajoute :

1. **Base** : le modèle H1 retenu (M3, G0 + G1 + G2, top 5, demi-vie de G2 par validation interne).
2. **Groupes H2, au plus 3 variables par équipe chacun** :
   - **G6 stabilité** (rapport H.7) : titulaires communs avec le match précédent de l'équipe ; cohésion par paires à décroissance exponentielle par rang de match, sans remise à zéro, limitée au club ; nombre de titulaires récents ;
   - **G5 qualité du XI** (ADR-0013, règle 3) : note moyenne des titulaires, rétrécie vers la moyenne du poste ; part des titulaires habituels absents ; âge moyen ;
   - **G4 entraîneur**, à l'horizon H2 (entraîneur de la feuille de match) : ancienneté plafonnée à 365 jours ; indicateur « nouvel entraîneur » (moins de 5 matchs).
3. **Ordre des ajouts cumulatifs (D1)** : **G6, puis G5, puis G4**. Chaque groupe s'ajoute au modèle retenu juste avant lui ; la règle de l'ADR-0037 décide. En diagnostic, sans pouvoir de décision : chaque groupe ajouté seul à la base.
4. **Variantes de stabilité (D2)** : la demi-vie de la cohésion (3, 5, 10, 20 matchs ou ∞) se choisit par validation interne du pli, comme celle de G2. Les variantes H.8 (remise à zéro, historique intégral, fenêtre de 10) sont mesurées et publiées en diagnostic, jamais choisies sur les plis de test.
5. **Rodage (D3)** : 2015-16 sert de rodage aux variables de G5 (apprentissage à partir de 2016-17) ; G4 apprend à partir de 2017-18. Les lignes exclues sont comptées et publiées.
6. **Structures (D4)** : après les groupes, M3 contre M6 (ridge), puis le retenu contre M7 (boosting à perte de Poisson, scikit-learn). Une comparaison pré-enregistrée chacune.
7. **Notes venues d'un championnat hors du périmètre (D9)** : moyenne du poste, et le nombre de cas est publié. Si plus de 10 % des titulaires sont concernés, une variante corrigée par championnat est mesurée en diagnostic.
8. **Collisions (D7)** : pas de scission manuelle ; l'exclusion de l'ADR-0020 est conservée.
9. **Test scellé H2 (D5)** :
   - référence : la **procédure H1 du premier test** (`experiments/scelle_h1.yaml` : apprentissage sur 2015-16 à 2024-25, validation interne sur 2024-25), et non le modèle final H1, qui a appris sur les matchs scellés ;
   - H2 suit la même procédure ;
   - seule comparaison de décision : `[M3_G0G2, H2]` ; B1 et le marché avant clôture publiés en contexte ;
   - préventions d'E-059 et d'E-060, puis tag `pre-scelle-h2` et gel de `modeling/`, `features/`, `experiments/` jusqu'au test ;
   - un seul lancement, résultat publié tel quel. La conclusion principale reste celle de la validation glissante (puissance, ci-dessus).
10. **Pas de modèle final H2 appris avec les matchs scellés (D6)** : il n'y a pas de live H2. En rejeu des saisons scellées, le modèle de 2025-26 et 2026-27 est celui du test.
11. **Architecture** : H1 ne change pas. Une fonction de la porte (`features/sources.py`) lit les compositions et les statistiques joueurs, et filtre le scellé en SQL. Les variables H2 sont des fonctions pures calculées à part, puis jointes. Les colonnes H1 d'un nouveau jeu sont contrôlées identiques à `ds-2026-10-22-bf786ef1`. Le registre accepte H2 ; un modèle d'horizon H1 refuse toute variable H2.

## Conséquences

- **Plan** : sous-étapes 6.0 à 6.14 du cadrage (section 8), environ 118 heures. Phase A sans aucun accès au scellé ; phase B pour le test (6.12) et l'ouverture du rejeu (6.13).
- **Code** : `features/sources.py` (nouvelle lecture), nouveaux modules de variables, `registry.py` et `registry.yaml`, tests d'architecture, `inference/` et `api/` (H2 en rejeu, « indisponible » en live). Aucune nouvelle dépendance. Aucun `load`.
- **Garde H1** : toute PR qui touche `modeling/models/` ou `features/` montre que les prédictions du modèle final H1 et les colonnes H1 du jeu sont inchangées (ADR-0044).
- **Hors périmètre** : blessures (G7), Dixon-Coles dynamique (M8), onze probable. Compose et planification en option à la fin de la partie (D8) ; une planification de collecte demandera sa propre ADR (autorisation durable).
- **Après le test H2** : nouvelle ADR qui ouvre le rejeu des saisons scellées (ADR-0045) et l'évaluation du journal prospectif H1.
- **Critères de révision** :
  - si une variable H2 se révèle incalculable sur plus de 10 % des lignes d'un pli de validation, le groupe est revu avant toute expérience, dans une nouvelle ADR qui dit ce qui avait déjà été évalué ;
  - si le test scellé montre H2 significativement **moins bon** que H1, le constat est publié tel quel, et le modèle retenu en rejeu reste H1.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
