# Horizon H2 : que rapporte la composition ? (jalon J9, sous-étape 6.7)

*2026-11-01. Spécification et liste des expériences écrites avant toute mesure : ADR-0048 (commit `402ffd0`). Protocole inchangé (ADR-0037, tag `protocole-v1`) : 4 plis 2021-22 à 2024-25, top 5, 10 000 rééchantillonnages, graine 20260930. Jeu `ds-2026-11-01-e0defb32`. Rapports : `reports/experiments/ablations-h2-20261101T123436.json` (décision) et `reports/experiments/stabilite-h2-20261101T123624.json` (diagnostic), tous deux sur arbre propre. Essais à cette date : **14**, 0 échec (dont quatre de H2 : une mesure de durée, un premier lancement avec des fichiers indexés non committés, aux chiffres identiques, et les deux lancements de référence).*

## Réponse en bref

La règle de l'ADR-0037, appliquée mécaniquement dans l'ordre G6, G5, G4 (ADR-0047, D1), donne ce chemin :

| Étape | Comparaison | Gain de log-loss du total [IC 95 %] | Plis gagnés | (i) | (ii) | (iii) | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | base H1 → + G6 (stabilité) | +0,00035 [−0,00022 ; +0,00091] | 3 sur 4 | non | oui | oui | **G6 non retenu** |
| 2 | base H1 → + G5 (qualité du XI), G6 n'étant pas retenu | +0,00078 [+0,00003 ; +0,00151] | 4 sur 4 | oui | oui | oui | **G5 retenu** |
| 3 | G5 → + G4 (entraîneur) | −0,00090 [−0,00158 ; −0,00022] | 1 sur 4 | non | non | oui | **G4 non retenu** |

**Le modèle H2 retenu est M3 sur G0 + G1 + G2 + G5** (la base H1 plus la qualité du XI), demi-vie de G2 choisie par validation interne (240 jours dans trois plis, 120 en 2022-23).

**À lire avec ce résultat** (tout est dans les tableaux générés plus bas) :

- **Le gain est minuscule** : +0,0008 nat par match sur un log-loss d'environ 1,88, soit 0,04 %. Le gain de H1 sur B1 était de +0,0179. Le RPS va dans le même sens (+0,00012 [+0,00001 ; +0,00023]).
- **Il passe la règle de justesse** : la borne basse de l'intervalle est à +0,00003, et le test de Diebold-Mariano donne p = 0,040. Un gain à ce niveau ne se distingue pas d'un hasard heureux avec certitude. La règle est celle qui a été écrite avant l'expérience et elle s'applique telle quelle ; le résultat se lit comme « G5 apporte peut-être un peu », pas comme une certitude.
- **À fenêtre d'apprentissage égale, il ne passe plus** : le modèle H1 appris dès 2016-17, comme G5 (`A2_depuis_2016`), est lui-même un peu meilleur que la base (+0,00017 [−0,00010 ; +0,00043]), et G5 contre ce témoin donne +0,00061 [−0,00010 ; +0,00130], 4 plis sur 4 mais intervalle contenant 0. Une partie du gain tient donc à la fenêtre.
- **Le gain se concentre au début de saison** : aux journées 1 à 5, +0,0021 [+0,0002 ; +0,0041] sur 967 matchs ; ailleurs, entre 0,0000 et +0,0007, intervalles contenant 0. C'est compatible avec l'idée que la qualité du onze compte surtout quand les moyennes glissantes sont encore peu informatives, mais c'est une lecture descriptive, hors de la règle.
- **Comparaisons multiples** : treize comparaisons dans l'expérience de décision (dont trois seulement décident), quinze en diagnostic, quatorze essais au total. Le protocole ne corrige pas ; il publie le nombre.
- **Puissance du test scellé H2** : l'ADR-0047 prévoit qu'un gain inférieur à environ 0,007 sortira probablement non significatif sur les quelque 2 100 matchs scellés. Le gain mesuré ici (0,0008) en est près de neuf fois plus petit : **le test scellé de H2 ne pourra presque sûrement pas le distinguer de zéro**. Le résultat sera publié tel quel, et la conclusion principale reste celle de la validation glissante.

## Groupe par groupe

### G6, stabilité du onze : pas d'apport (étape 1)

Base H1 contre + G6 : +0,00035 [−0,00022 ; +0,00091], 3 plis sur 4 (−0,0003 en 2021-22, puis +0,0000, +0,0007, +0,0010). L'intervalle contient 0 : G6 n'est pas retenu, et le résultat nul est publié (ADR-0013, règle 5). La variante de cohésion choisie par validation interne change d'un pli à l'autre (`hinf`, `hinf`, `h3`, `h3`), signe que le critère interne ne départage pas vraiment les variantes. Aux journées 1 à 5, + G6 est **moins bon** que la base : −0,0019 [−0,0036 ; −0,0002]. C'est le contraire de ce qu'on espérait, et ce n'est pas une preuve : c'est une tranche parmi quatre.

**Diagnostic des variantes (D2, `stabilite_h2.yaml`)** : aucune des huit variantes n'a un gain dont l'intervalle exclut 0 contre la base H1.

| Variante | Gain sur la base H1 [IC 95 %] | Plis gagnés |
|---|---|---|
| Fenêtre de 10 matchs | +0,00045 [−0,00038 ; +0,00126] | 3 sur 4 |
| Demi-vie 5 matchs | +0,00035 [−0,00030 ; +0,00100] | 3 sur 4 |
| Demi-vie 3 matchs | +0,00031 [−0,00036 ; +0,00097] | 3 sur 4 |
| Demi-vie 10 matchs | +0,00025 [−0,00035 ; +0,00083] | 3 sur 4 |
| Demi-vie 20 matchs | +0,00010 [−0,00043 ; +0,00064] | 2 sur 4 |
| Historique intégral (∞) | −0,00004 [−0,00053 ; +0,00045] | 2 sur 4 |
| Remise à zéro par saison | −0,00007 [−0,00080 ; +0,00063] | 2 sur 4 |
| Recouvrement seul | −0,00006 [−0,00037 ; +0,00025] | 2 sur 4 |

Les cohésions à décroissance rapide (3 à 10 matchs) et la fenêtre de 10 sont du bon côté de zéro, sans qu'aucune se distingue du recouvrement seul (écart au recouvrement : +0,0002 à +0,0005, intervalles contenant 0). L'historique intégral et la remise à zéro valent zéro, comme H.4 le laissait prévoir pour l'historique intégral (inerte), et la remise à zéro ne fait pas mieux que de ne pas en faire. La remise à zéro est vide au premier match de chaque saison : ces matchs (48 à 49 par pli) sortent de l'intersection de toute cette expérience. **Conclusion sur la stabilité** (critère de réussite n° 2 de la partie 6) : aucune variante ne se distingue ; selon le rapport (H.8, point 5), la stabilité est **abandonnée pour H2** et le résultat est documenté ici. L'annonce de H.3 (plus de 0,9 de corrélation entre paires et recouvrement) ne s'était déjà pas vérifiée en 6.6.

### G5, qualité du XI : un petit apport, fragile (étape 2)

Voir « Réponse en bref ». Le groupe compte trois variables par équipe (note rétrécie, habituels absents, âge moyen), pour l'équipe et pour l'adversaire. Le rodage (D3) écarte les 3 652 lignes de 2015-16 de l'apprentissage ; 646 à 688 lignes d'apprentissage de plus sont écartées pour valeur manquante selon le pli ; 21 matchs de test (11, 8, 2 et 0 par pli) n'ont pas de prédiction. La calibration ne se dégrade pas : écart moyen par décile 1,43 point contre 1,62 pour la base, pente 0,965. Comme `xi_quality` est corrélée à 0,83 avec l'Elo (6.6), ce que G5 apporte à Elo et glissants donnés est ce qui reste, soit presque rien.

### G4, entraîneur : pas d'apport (étape 3 et diagnostic)

Seul, contre la base : −0,00069 [−0,00146 ; +0,00009], 1 pli sur 4. À fenêtre égale (`A2_depuis_2017`) : −0,00039 [−0,00083 ; +0,00004]. Ajouté à G5 : −0,00090 [−0,00158 ; −0,00022], significativement moins bon, 1 pli sur 4. Les trois groupes ensemble contre la base : −0,00019 [−0,00128 ; +0,00092]. L'indicateur « nouvel entraîneur » et l'ancienneté plafonnée n'améliorent pas la prédiction du total, et quatre coefficients de plus, sans gain, coûtent un peu de log-loss.

## Ce qui a été écarté ou compté

| Quantité | Valeur |
|---|---|
| Matchs d'évaluation | 7 156 (1 826, 1 826, 1 752, 1 752) |
| Matchs écartés par l'intersection (décision) | 11, 19, 3 et 0 par pli, soit 33 (0,46 %), tous venant de valeurs G5 ou G4 manquantes à la veille du match |
| Matchs écartés par l'intersection (stabilité) | 49, 49, 48 et 48 (la remise à zéro est vide à la première journée) |
| Lignes de rodage écartées | G5 : 3 652 (2015-16) ; G4 : 7 304 (2015-16 et 2016-17) |
| Titulaires sans aucune note antérieure (D9) | 0,3 % sur les plis (lot 6.3) : la variante corrigée par championnat n'est pas déclenchée |

## Limites

- Un seul jeu de plis, quatre saisons : les intervalles sont larges devant des gains de cet ordre.
- Les variables H2 ne sont pas disponibles en live (compositions non fournies après la fin de l'abonnement) : ce modèle ne servira qu'en rejeu (ADR-0010, ADR-0011).
- Les résultats de la mesure de durée (200 rééchantillonnages) ont été vus avant le lancement de référence : seuls les intervalles diffèrent des estimations ponctuelles, qui sont identiques. La règle s'est appliquée aux 10 000 rééchantillonnages.
- La structure retenue (M3) n'est pas remise en cause ici : M6 (ridge) et M7 (boosting) sont comparés au modèle retenu en 6.8, et une régularisation pourrait changer le jugement sur les groupes qui se recoupent (G5 et Elo, G6 et habituels absents).

## Tableaux générés

Générés par `uv run python -m foot_predictor.modeling summary <rapport>` : ils ne sont pas recopiés à la main. Les verdicts « remplace » des lignes de décision sont ceux de la règle ; seuls ceux de l'étape 1, de l'étape 2 et de l'étape 3 qui suivent le chemin décident (ADR-0048).

### Expérience de décision : `ablations_h2.yaml`

Rapport `ablations-h2-20261101T123436` : jeu `ds-2026-11-01-e0defb32`, commit `cb4e15f`, graine 20260930, 10000 rééchantillonnages.

| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |
|---|---|---|---|---|---|
| 2021-22 | 1826 | 1815 | 11 | n. d. | A2_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 240}; G6 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'hinf', 'half_life': 240}; G5 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'half_life': 240}; G4 : {'groups': ['G0', 'G1', 'G2', 'G4'], 'half_life': 240}; G6_G5 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G5'], 'cohesion': 'h3', 'half_life': 240}; G6_G4 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G4'], 'cohesion': 'hinf', 'half_life': 240}; G5_G4 : {'groups': ['G0', 'G1', 'G2', 'G5', 'G4'], 'half_life': 240}; G6_G5_G4 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G5', 'G4'], 'cohesion': 'h3', 'half_life': 240}; A2_depuis_2016 : {'groups': ['G0', 'G1', 'G2'], 'train_from': 2016, 'half_life': 240}; A2_depuis_2017 : {'groups': ['G0', 'G1', 'G2'], 'train_from': 2017, 'half_life': 240} |
| 2022-23 | 1826 | 1807 | 19 | n. d. | A2_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 120}; G6 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'hinf', 'half_life': 120}; G5 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'half_life': 120}; G4 : {'groups': ['G0', 'G1', 'G2', 'G4'], 'half_life': 120}; G6_G5 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G5'], 'cohesion': 'hinf', 'half_life': 240}; G6_G4 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G4'], 'cohesion': 'hinf', 'half_life': 120}; G5_G4 : {'groups': ['G0', 'G1', 'G2', 'G5', 'G4'], 'half_life': 120}; G6_G5_G4 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G5', 'G4'], 'cohesion': 'hinf', 'half_life': 120}; A2_depuis_2016 : {'groups': ['G0', 'G1', 'G2'], 'train_from': 2016, 'half_life': 120}; A2_depuis_2017 : {'groups': ['G0', 'G1', 'G2'], 'train_from': 2017, 'half_life': 120} |
| 2023-24 | 1752 | 1749 | 3 | n. d. | A2_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 240}; G6 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h3', 'half_life': 240}; G5 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'half_life': 240}; G4 : {'groups': ['G0', 'G1', 'G2', 'G4'], 'half_life': 240}; G6_G5 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G5'], 'cohesion': 'h3', 'half_life': 240}; G6_G4 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G4'], 'cohesion': 'h3', 'half_life': 240}; G5_G4 : {'groups': ['G0', 'G1', 'G2', 'G5', 'G4'], 'half_life': 240}; G6_G5_G4 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G5', 'G4'], 'cohesion': 'h3', 'half_life': 240}; A2_depuis_2016 : {'groups': ['G0', 'G1', 'G2'], 'train_from': 2016, 'half_life': 240}; A2_depuis_2017 : {'groups': ['G0', 'G1', 'G2'], 'train_from': 2017, 'half_life': 240} |
| 2024-25 | 1752 | 1752 | 0 | n. d. | A2_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 240}; G6 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h3', 'half_life': 240}; G5 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'half_life': 240}; G4 : {'groups': ['G0', 'G1', 'G2', 'G4'], 'half_life': 240}; G6_G5 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G5'], 'cohesion': 'h5', 'half_life': 240}; G6_G4 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G4'], 'cohesion': 'h5', 'half_life': 240}; G5_G4 : {'groups': ['G0', 'G1', 'G2', 'G5', 'G4'], 'half_life': 240}; G6_G5_G4 : {'groups': ['G0', 'G1', 'G2', 'G6', 'G5', 'G4'], 'cohesion': 'hinf', 'half_life': 240}; A2_depuis_2016 : {'groups': ['G0', 'G1', 'G2'], 'train_from': 2016, 'half_life': 240}; A2_depuis_2017 : {'groups': ['G0', 'G1', 'G2'], 'train_from': 2017, 'half_life': 240} |

| Modèle | Pli | Log-loss | RPS | Brier P(T > 2,5) | Calibration : écart moyen | Pente | Couverture observée | Couverture annoncée | Log-loss score exact | Brier 1N2 | MAE E[T] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A2_G0G2 | 2021-22 | 1.8964 | 0.1316 | 0.2440 | 0.0395 | 0.87 | 87.1 % | 87.7 % | 2.9259 | 0.5912 | 1.346 |
| A2_G0G2 | 2022-23 | 1.8659 | 0.1266 | 0.2426 | 0.0201 | 1.02 | 87.7 % | 87.3 % | 2.9015 | 0.5867 | 1.295 |
| A2_G0G2 | 2023-24 | 1.8929 | 0.1300 | 0.2380 | 0.0335 | 1.16 | 87.3 % | 87.7 % | 2.9302 | 0.5832 | 1.324 |
| A2_G0G2 | 2024-25 | 1.8673 | 0.1268 | 0.2420 | 0.0339 | 0.84 | 89.2 % | 88.1 % | 2.9136 | 0.5862 | 1.305 |
| G6 | 2021-22 | 1.8967 | 0.1317 | 0.2442 | 0.0325 | 0.85 | 87.2 % | 87.7 % | 2.9251 | 0.5905 | 1.348 |
| G6 | 2022-23 | 1.8659 | 0.1266 | 0.2426 | 0.0154 | 1.02 | 87.8 % | 87.4 % | 2.9001 | 0.5860 | 1.296 |
| G6 | 2023-24 | 1.8922 | 0.1299 | 0.2377 | 0.0366 | 1.18 | 87.2 % | 87.7 % | 2.9268 | 0.5814 | 1.323 |
| G6 | 2024-25 | 1.8663 | 0.1266 | 0.2415 | 0.0332 | 0.85 | 89.0 % | 88.1 % | 2.9083 | 0.5834 | 1.303 |
| G5 | 2021-22 | 1.8963 | 0.1316 | 0.2441 | 0.0371 | 0.86 | 87.1 % | 87.7 % | 2.9217 | 0.5884 | 1.345 |
| G5 | 2022-23 | 1.8653 | 0.1264 | 0.2423 | 0.0180 | 1.03 | 87.8 % | 87.3 % | 2.8975 | 0.5845 | 1.293 |
| G5 | 2023-24 | 1.8918 | 0.1299 | 0.2377 | 0.0348 | 1.23 | 87.2 % | 87.6 % | 2.9271 | 0.5818 | 1.322 |
| G5 | 2024-25 | 1.8659 | 0.1266 | 0.2416 | 0.0208 | 0.86 | 89.4 % | 88.2 % | 2.9095 | 0.5851 | 1.302 |
| G4 | 2021-22 | 1.8992 | 0.1320 | 0.2447 | 0.0445 | 0.86 | 87.4 % | 87.7 % | 2.9288 | 0.5910 | 1.344 |
| G4 | 2022-23 | 1.8656 | 0.1265 | 0.2426 | 0.0173 | 1.03 | 87.8 % | 87.4 % | 2.9011 | 0.5872 | 1.292 |
| G4 | 2023-24 | 1.8930 | 0.1300 | 0.2378 | 0.0404 | 1.21 | 87.1 % | 87.6 % | 2.9303 | 0.5833 | 1.322 |
| G4 | 2024-25 | 1.8673 | 0.1268 | 0.2422 | 0.0216 | 0.83 | 89.3 % | 88.1 % | 2.9125 | 0.5860 | 1.303 |
| G6_G5 | 2021-22 | 1.8971 | 0.1317 | 0.2446 | 0.0383 | 0.82 | 87.1 % | 87.7 % | 2.9226 | 0.5886 | 1.348 |
| G6_G5 | 2022-23 | 1.8649 | 0.1264 | 0.2423 | 0.0187 | 1.03 | 87.8 % | 87.5 % | 2.8966 | 0.5845 | 1.294 |
| G6_G5 | 2023-24 | 1.8911 | 0.1298 | 0.2375 | 0.0356 | 1.22 | 87.1 % | 87.6 % | 2.9246 | 0.5804 | 1.321 |
| G6_G5 | 2024-25 | 1.8650 | 0.1264 | 0.2411 | 0.0261 | 0.87 | 89.0 % | 88.1 % | 2.9079 | 0.5845 | 1.300 |
| G6_G4 | 2021-22 | 1.8990 | 0.1320 | 0.2448 | 0.0370 | 0.84 | 87.1 % | 87.7 % | 2.9277 | 0.5904 | 1.346 |
| G6_G4 | 2022-23 | 1.8657 | 0.1265 | 0.2426 | 0.0228 | 1.03 | 87.7 % | 87.4 % | 2.8998 | 0.5864 | 1.294 |
| G6_G4 | 2023-24 | 1.8918 | 0.1299 | 0.2373 | 0.0355 | 1.24 | 87.1 % | 87.7 % | 2.9265 | 0.5816 | 1.321 |
| G6_G4 | 2024-25 | 1.8658 | 0.1265 | 0.2415 | 0.0238 | 0.86 | 89.3 % | 88.1 % | 2.9068 | 0.5831 | 1.300 |
| G5_G4 | 2021-22 | 1.8988 | 0.1319 | 0.2447 | 0.0370 | 0.86 | 87.4 % | 87.7 % | 2.9247 | 0.5886 | 1.345 |
| G5_G4 | 2022-23 | 1.8651 | 0.1264 | 0.2424 | 0.0155 | 1.05 | 87.8 % | 87.4 % | 2.8977 | 0.5851 | 1.291 |
| G5_G4 | 2023-24 | 1.8927 | 0.1300 | 0.2378 | 0.0445 | 1.25 | 87.2 % | 87.6 % | 2.9282 | 0.5821 | 1.322 |
| G5_G4 | 2024-25 | 1.8663 | 0.1266 | 0.2419 | 0.0188 | 0.85 | 89.4 % | 88.1 % | 2.9089 | 0.5847 | 1.301 |
| G6_G5_G4 | 2021-22 | 1.8992 | 0.1320 | 0.2451 | 0.0384 | 0.81 | 87.4 % | 87.7 % | 2.9250 | 0.5885 | 1.347 |
| G6_G5_G4 | 2022-23 | 1.8652 | 0.1264 | 0.2424 | 0.0194 | 1.04 | 87.9 % | 87.4 % | 2.8975 | 0.5848 | 1.293 |
| G6_G5_G4 | 2023-24 | 1.8918 | 0.1299 | 0.2375 | 0.0375 | 1.24 | 87.1 % | 87.6 % | 2.9258 | 0.5809 | 1.320 |
| G6_G5_G4 | 2024-25 | 1.8669 | 0.1267 | 0.2420 | 0.0194 | 0.84 | 89.3 % | 88.1 % | 2.9100 | 0.5850 | 1.306 |
| A2_depuis_2016 | 2021-22 | 1.8966 | 0.1316 | 0.2440 | 0.0345 | 0.86 | 87.0 % | 87.7 % | 2.9261 | 0.5913 | 1.346 |
| A2_depuis_2016 | 2022-23 | 1.8659 | 0.1266 | 0.2426 | 0.0160 | 1.02 | 87.8 % | 87.4 % | 2.9014 | 0.5868 | 1.295 |
| A2_depuis_2016 | 2023-24 | 1.8921 | 0.1299 | 0.2377 | 0.0324 | 1.19 | 87.3 % | 87.7 % | 2.9294 | 0.5831 | 1.323 |
| A2_depuis_2016 | 2024-25 | 1.8671 | 0.1267 | 0.2420 | 0.0243 | 0.84 | 89.2 % | 88.1 % | 2.9130 | 0.5861 | 1.305 |
| A2_depuis_2017 | 2021-22 | 1.8980 | 0.1318 | 0.2443 | 0.0346 | 0.89 | 86.9 % | 87.8 % | 2.9274 | 0.5909 | 1.344 |
| A2_depuis_2017 | 2022-23 | 1.8656 | 0.1265 | 0.2425 | 0.0127 | 1.04 | 87.7 % | 87.3 % | 2.9010 | 0.5869 | 1.292 |
| A2_depuis_2017 | 2023-24 | 1.8933 | 0.1301 | 0.2381 | 0.0408 | 1.21 | 87.2 % | 87.6 % | 2.9303 | 0.5831 | 1.323 |
| A2_depuis_2017 | 2024-25 | 1.8667 | 0.1267 | 0.2420 | 0.0252 | 0.85 | 89.1 % | 88.1 % | 2.9117 | 0.5859 | 1.302 |

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| A2_G0G2 | 7123 | 1.8806 | 0.1287 | 0.2417 | 0.0162 | 0.95 | +0.028 |
| G6 | 7123 | 1.8803 | 0.1287 | 0.2415 | 0.0139 | 0.95 | +0.025 |
| G5 | 7123 | 1.8799 | 0.1286 | 0.2415 | 0.0143 | 0.97 | +0.037 |
| G4 | 7123 | 1.8813 | 0.1288 | 0.2419 | 0.0148 | 0.95 | +0.056 |
| G6_G5 | 7123 | 1.8796 | 0.1286 | 0.2414 | 0.0151 | 0.96 | +0.031 |
| G6_G4 | 7123 | 1.8806 | 0.1287 | 0.2416 | 0.0137 | 0.96 | +0.045 |
| G5_G4 | 7123 | 1.8808 | 0.1287 | 0.2417 | 0.0171 | 0.96 | +0.060 |
| G6_G5_G4 | 7123 | 1.8808 | 0.1288 | 0.2418 | 0.0130 | 0.93 | +0.044 |
| A2_depuis_2016 | 7123 | 1.8805 | 0.1287 | 0.2416 | 0.0153 | 0.95 | +0.026 |
| A2_depuis_2017 | 7123 | 1.8809 | 0.1288 | 0.2418 | 0.0160 | 0.96 | +0.051 |

Petits totaux, calibration poolée sur les 4 plis :

| Modèle | k | P(T = k) prédite | observée | Brier | Écart moyen par décile | Pente |
|---|---|---|---|---|---|---|
| A2_G0G2 | 0 | 6.5 % | 6.3 % | 0.0586 | 0.0094 | 0.82 |
| A2_G0G2 | 1 | 17.4 % | 16.3 % | 0.1353 | 0.0148 | 0.97 |
| A2_G0G2 | 2 | 23.5 % | 24.2 % | 0.1828 | 0.0138 | 1.04 |
| G6 | 0 | 6.5 % | 6.3 % | 0.0586 | 0.0086 | 0.85 |
| G6 | 1 | 17.3 % | 16.3 % | 0.1353 | 0.0131 | 0.96 |
| G6 | 2 | 23.5 % | 24.2 % | 0.1828 | 0.0155 | 1.03 |
| G5 | 0 | 6.6 % | 6.3 % | 0.0586 | 0.0116 | 0.86 |
| G5 | 1 | 17.5 % | 16.3 % | 0.1353 | 0.0136 | 0.98 |
| G5 | 2 | 23.6 % | 24.2 % | 0.1827 | 0.0106 | 1.06 |
| G4 | 0 | 6.7 % | 6.3 % | 0.0586 | 0.0096 | 0.82 |
| G4 | 1 | 17.7 % | 16.3 % | 0.1354 | 0.0144 | 0.98 |
| G4 | 2 | 23.7 % | 24.2 % | 0.1827 | 0.0142 | 1.08 |
| G6_G5 | 0 | 6.5 % | 6.3 % | 0.0585 | 0.0086 | 0.90 |
| G6_G5 | 1 | 17.4 % | 16.3 % | 0.1353 | 0.0116 | 0.96 |
| G6_G5 | 2 | 23.5 % | 24.2 % | 0.1828 | 0.0098 | 1.02 |
| G6_G4 | 0 | 6.6 % | 6.3 % | 0.0586 | 0.0121 | 0.83 |
| G6_G4 | 1 | 17.6 % | 16.3 % | 0.1353 | 0.0136 | 0.98 |
| G6_G4 | 2 | 23.6 % | 24.2 % | 0.1827 | 0.0123 | 1.08 |
| G5_G4 | 0 | 6.7 % | 6.3 % | 0.0586 | 0.0107 | 0.86 |
| G5_G4 | 1 | 17.7 % | 16.3 % | 0.1353 | 0.0140 | 0.99 |
| G5_G4 | 2 | 23.7 % | 24.2 % | 0.1827 | 0.0136 | 1.10 |
| G6_G5_G4 | 0 | 6.6 % | 6.3 % | 0.0585 | 0.0100 | 0.87 |
| G6_G5_G4 | 1 | 17.5 % | 16.3 % | 0.1353 | 0.0131 | 0.95 |
| G6_G5_G4 | 2 | 23.6 % | 24.2 % | 0.1828 | 0.0108 | 1.01 |
| A2_depuis_2016 | 0 | 6.5 % | 6.3 % | 0.0586 | 0.0107 | 0.82 |
| A2_depuis_2016 | 1 | 17.3 % | 16.3 % | 0.1353 | 0.0123 | 0.97 |
| A2_depuis_2016 | 2 | 23.5 % | 24.2 % | 0.1828 | 0.0200 | 1.04 |
| A2_depuis_2017 | 0 | 6.7 % | 6.3 % | 0.0586 | 0.0100 | 0.84 |
| A2_depuis_2017 | 1 | 17.6 % | 16.3 % | 0.1353 | 0.0132 | 0.99 |
| A2_depuis_2017 | 2 | 23.7 % | 24.2 % | 0.1828 | 0.0169 | 1.07 |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| A2_G0G2 | G6 | log-loss du total | +0.00035 | [-0.00022 ; +0.00091] | 3 sur 4 | 0.2343 | 2021 : -0.0003 ; 2022 : +0.0000 ; 2023 : +0.0007 ; 2024 : +0.0010 |
| A2_G0G2 | G6 | RPS | +0.00003 | [-0.00005 ; +0.00012] | 2 sur 4 | 0.4264 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : +0.0001 |
| A2_G0G2 | G6 | Brier P(T = 0) | +0.00003 | [+0.00001 ; +0.00006] | 3 sur 4 | 0.0159 | 2021 : -0.0000 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | G6 | Brier P(T = 1) | -0.00000 | [-0.00007 ; +0.00007] | 2 sur 4 | 0.9607 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : -0.0000 |
| A2_G0G2 | G6 | Brier P(T = 2) | -0.00000 | [-0.00006 ; +0.00005] | 2 sur 4 | 0.9624 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **G6 ne remplace pas A2_G0G2** | | | |
| G6 | G6_G5 | log-loss du total | +0.00074 | [-0.00009 ; +0.00157] | 3 sur 4 | 0.0816 | 2021 : -0.0003 ; 2022 : +0.0010 ; 2023 : +0.0011 ; 2024 : +0.0012 |
| G6 | G6_G5 | RPS | +0.00011 | [-0.00001 ; +0.00023] | 3 sur 4 | 0.0791 | 2021 : -0.0000 ; 2022 : +0.0002 ; 2023 : +0.0001 ; 2024 : +0.0002 |
| G6 | G6_G5 | Brier P(T = 0) | +0.00005 | [+0.00001 ; +0.00010] | 4 sur 4 | 0.0131 | 2021 : +0.0000 ; 2022 : +0.0001 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| G6 | G6_G5 | Brier P(T = 1) | +0.00001 | [-0.00010 ; +0.00012] | 2 sur 4 | 0.9021 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : +0.0001 |
| G6 | G6_G5 | Brier P(T = 2) | -0.00000 | [-0.00008 ; +0.00008] | 2 sur 4 | 0.9519 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : -0.0001 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **G6_G5 ne remplace pas G6** | | | |
| A2_G0G2 | G5 | log-loss du total | +0.00078 | [+0.00003 ; +0.00151] | 4 sur 4 | 0.0397 | 2021 : +0.0001 ; 2022 : +0.0005 ; 2023 : +0.0011 ; 2024 : +0.0014 |
| A2_G0G2 | G5 | RPS | +0.00012 | [+0.00001 ; +0.00023] | 4 sur 4 | 0.0320 | 2021 : +0.0000 ; 2022 : +0.0001 ; 2023 : +0.0001 ; 2024 : +0.0002 |
| A2_G0G2 | G5 | Brier P(T = 0) | +0.00003 | [+0.00000 ; +0.00007] | 4 sur 4 | 0.0480 | 2021 : +0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| A2_G0G2 | G5 | Brier P(T = 1) | +0.00002 | [-0.00006 ; +0.00011] | 3 sur 4 | 0.5963 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : +0.0001 |
| A2_G0G2 | G5 | Brier P(T = 2) | +0.00003 | [-0.00004 ; +0.00010] | 4 sur 4 | 0.4239 | 2021 : +0.0000 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) oui, (ii) oui, (iii) oui | **G5 remplace A2_G0G2** | | | |
| G6_G5 | G6_G5_G4 | log-loss du total | -0.00127 | [-0.00210 ; -0.00042] | 0 sur 4 | 0.0031 | 2021 : -0.0022 ; 2022 : -0.0004 ; 2023 : -0.0007 ; 2024 : -0.0019 |
| G6_G5 | G6_G5_G4 | RPS | -0.00015 | [-0.00027 ; -0.00003] | 1 sur 4 | 0.0109 | 2021 : -0.0003 ; 2022 : +0.0000 ; 2023 : -0.0001 ; 2024 : -0.0003 |
| G6_G5 | G6_G5_G4 | Brier P(T = 0) | -0.00004 | [-0.00009 ; +0.00001] | 2 sur 4 | 0.1253 | 2021 : +0.0000 ; 2022 : -0.0001 ; 2023 : -0.0001 ; 2024 : +0.0000 |
| G6_G5 | G6_G5_G4 | Brier P(T = 1) | -0.00006 | [-0.00018 ; +0.00005] | 1 sur 4 | 0.2760 | 2021 : -0.0002 ; 2022 : +0.0001 ; 2023 : -0.0000 ; 2024 : -0.0001 |
| G6_G5 | G6_G5_G4 | Brier P(T = 2) | -0.00003 | [-0.00011 ; +0.00006] | 2 sur 4 | 0.4832 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : -0.0002 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **G6_G5_G4 ne remplace pas G6_G5** | | | |
| G6 | G6_G4 | log-loss du total | -0.00034 | [-0.00109 ; +0.00041] | 3 sur 4 | 0.3695 | 2021 : -0.0023 ; 2022 : +0.0001 ; 2023 : +0.0003 ; 2024 : +0.0005 |
| G6 | G6_G4 | RPS | -0.00002 | [-0.00012 ; +0.00009] | 3 sur 4 | 0.7258 | 2021 : -0.0003 ; 2022 : +0.0001 ; 2023 : +0.0001 ; 2024 : +0.0001 |
| G6 | G6_G4 | Brier P(T = 0) | -0.00003 | [-0.00007 ; +0.00001] | 1 sur 4 | 0.1893 | 2021 : +0.0000 ; 2022 : -0.0001 ; 2023 : -0.0000 ; 2024 : -0.0000 |
| G6 | G6_G4 | Brier P(T = 1) | -0.00003 | [-0.00013 ; +0.00006] | 2 sur 4 | 0.5122 | 2021 : -0.0002 ; 2022 : +0.0001 ; 2023 : +0.0001 ; 2024 : -0.0000 |
| G6 | G6_G4 | Brier P(T = 2) | +0.00004 | [-0.00004 ; +0.00011] | 3 sur 4 | 0.3406 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **G6_G4 ne remplace pas G6** | | | |
| G5 | G5_G4 | log-loss du total | -0.00090 | [-0.00158 ; -0.00022] | 1 sur 4 | 0.0098 | 2021 : -0.0025 ; 2022 : +0.0002 ; 2023 : -0.0009 ; 2024 : -0.0004 |
| G5 | G5_G4 | RPS | -0.00011 | [-0.00020 ; -0.00001] | 1 sur 4 | 0.0219 | 2021 : -0.0003 ; 2022 : +0.0001 ; 2023 : -0.0001 ; 2024 : -0.0001 |
| G5 | G5_G4 | Brier P(T = 0) | -0.00002 | [-0.00006 ; +0.00002] | 2 sur 4 | 0.3579 | 2021 : +0.0000 ; 2022 : -0.0001 ; 2023 : -0.0000 ; 2024 : +0.0000 |
| G5 | G5_G4 | Brier P(T = 1) | -0.00010 | [-0.00018 ; -0.00001] | 1 sur 4 | 0.0297 | 2021 : -0.0003 ; 2022 : +0.0001 ; 2023 : -0.0001 ; 2024 : -0.0001 |
| G5 | G5_G4 | Brier P(T = 2) | +0.00001 | [-0.00006 ; +0.00007] | 2 sur 4 | 0.8178 | 2021 : -0.0000 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **G5_G4 ne remplace pas G5** | | | |
| A2_G0G2 | G4 | log-loss du total | -0.00069 | [-0.00146 ; +0.00009] | 1 sur 4 | 0.0846 | 2021 : -0.0028 ; 2022 : +0.0003 ; 2023 : -0.0001 ; 2024 : -0.0000 |
| A2_G0G2 | G4 | RPS | -0.00008 | [-0.00018 ; +0.00003] | 2 sur 4 | 0.1718 | 2021 : -0.0004 ; 2022 : +0.0001 ; 2023 : -0.0000 ; 2024 : +0.0000 |
| A2_G0G2 | G4 | Brier P(T = 0) | -0.00002 | [-0.00006 ; +0.00003] | 1 sur 4 | 0.4590 | 2021 : +0.0000 ; 2022 : -0.0001 ; 2023 : -0.0000 ; 2024 : -0.0000 |
| A2_G0G2 | G4 | Brier P(T = 1) | -0.00007 | [-0.00017 ; +0.00003] | 1 sur 4 | 0.1481 | 2021 : -0.0003 ; 2022 : +0.0001 ; 2023 : -0.0000 ; 2024 : -0.0001 |
| A2_G0G2 | G4 | Brier P(T = 2) | +0.00001 | [-0.00006 ; +0.00009] | 2 sur 4 | 0.7626 | 2021 : -0.0000 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **G4 ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | G6_G5_G4 | log-loss du total | -0.00019 | [-0.00128 ; +0.00092] | 3 sur 4 | 0.7480 | 2021 : -0.0028 ; 2022 : +0.0006 ; 2023 : +0.0011 ; 2024 : +0.0004 |
| A2_G0G2 | G6_G5_G4 | RPS | -0.00001 | [-0.00017 ; +0.00015] | 3 sur 4 | 0.8951 | 2021 : -0.0004 ; 2022 : +0.0001 ; 2023 : +0.0001 ; 2024 : +0.0001 |
| A2_G0G2 | G6_G5_G4 | Brier P(T = 0) | +0.00005 | [-0.00000 ; +0.00011] | 4 sur 4 | 0.0815 | 2021 : +0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | G6_G5_G4 | Brier P(T = 1) | -0.00006 | [-0.00020 ; +0.00008] | 2 sur 4 | 0.4138 | 2021 : -0.0005 ; 2022 : +0.0001 ; 2023 : +0.0001 ; 2024 : -0.0000 |
| A2_G0G2 | G6_G5_G4 | Brier P(T = 2) | -0.00003 | [-0.00014 ; +0.00007] | 0 sur 4 | 0.5350 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : -0.0000 ; 2024 : -0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **G6_G5_G4 ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | A2_depuis_2016 | log-loss du total | +0.00017 | [-0.00010 ; +0.00043] | 2 sur 4 | 0.2229 | 2021 : -0.0002 ; 2022 : -0.0001 ; 2023 : +0.0008 ; 2024 : +0.0002 |
| A2_G0G2 | A2_depuis_2016 | RPS | +0.00003 | [-0.00001 ; +0.00007] | 3 sur 4 | 0.1152 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| A2_G0G2 | A2_depuis_2016 | Brier P(T = 0) | +0.00000 | [-0.00001 ; +0.00002] | 2 sur 4 | 0.6179 | 2021 : +0.0000 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : -0.0000 |
| A2_G0G2 | A2_depuis_2016 | Brier P(T = 1) | +0.00003 | [-0.00001 ; +0.00006] | 3 sur 4 | 0.1448 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| A2_G0G2 | A2_depuis_2016 | Brier P(T = 2) | +0.00000 | [-0.00002 ; +0.00002] | 3 sur 4 | 0.9702 | 2021 : +0.0000 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **A2_depuis_2016 ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | A2_depuis_2017 | log-loss du total | -0.00030 | [-0.00086 ; +0.00026] | 2 sur 4 | 0.2996 | 2021 : -0.0016 ; 2022 : +0.0002 ; 2023 : -0.0004 ; 2024 : +0.0006 |
| A2_G0G2 | A2_depuis_2017 | RPS | -0.00004 | [-0.00012 ; +0.00004] | 2 sur 4 | 0.3588 | 2021 : -0.0002 ; 2022 : +0.0001 ; 2023 : -0.0001 ; 2024 : +0.0001 |
| A2_G0G2 | A2_depuis_2017 | Brier P(T = 0) | -0.00000 | [-0.00003 ; +0.00002] | 1 sur 4 | 0.7510 | 2021 : +0.0000 ; 2022 : -0.0000 ; 2023 : -0.0000 ; 2024 : -0.0000 |
| A2_G0G2 | A2_depuis_2017 | Brier P(T = 1) | -0.00004 | [-0.00011 ; +0.00003] | 2 sur 4 | 0.2456 | 2021 : -0.0002 ; 2022 : +0.0000 ; 2023 : -0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | A2_depuis_2017 | Brier P(T = 2) | -0.00000 | [-0.00005 ; +0.00005] | 2 sur 4 | 0.9966 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : -0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **A2_depuis_2017 ne remplace pas A2_G0G2** | | | |
| A2_depuis_2016 | G5 | log-loss du total | +0.00061 | [-0.00010 ; +0.00130] | 4 sur 4 | 0.0852 | 2021 : +0.0003 ; 2022 : +0.0006 ; 2023 : +0.0003 ; 2024 : +0.0013 |
| A2_depuis_2016 | G5 | RPS | +0.00009 | [-0.00002 ; +0.00020] | 4 sur 4 | 0.0879 | 2021 : +0.0001 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0002 |
| A2_depuis_2016 | G5 | Brier P(T = 0) | +0.00003 | [+0.00000 ; +0.00006] | 4 sur 4 | 0.0481 | 2021 : +0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| A2_depuis_2016 | G5 | Brier P(T = 1) | -0.00000 | [-0.00009 ; +0.00008] | 3 sur 4 | 0.9843 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_depuis_2016 | G5 | Brier P(T = 2) | +0.00003 | [-0.00004 ; +0.00010] | 4 sur 4 | 0.4089 | 2021 : +0.0000 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **G5 ne remplace pas A2_depuis_2016** | | | |
| A2_depuis_2017 | G4 | log-loss du total | -0.00039 | [-0.00083 ; +0.00004] | 2 sur 4 | 0.0839 | 2021 : -0.0012 ; 2022 : +0.0000 ; 2023 : +0.0003 ; 2024 : -0.0006 |
| A2_depuis_2017 | G4 | RPS | -0.00004 | [-0.00010 ; +0.00002] | 2 sur 4 | 0.2273 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : -0.0001 |
| A2_depuis_2017 | G4 | Brier P(T = 0) | -0.00001 | [-0.00004 ; +0.00001] | 1 sur 4 | 0.3748 | 2021 : -0.0000 ; 2022 : -0.0000 ; 2023 : -0.0000 ; 2024 : +0.0000 |
| A2_depuis_2017 | G4 | Brier P(T = 1) | -0.00003 | [-0.00009 ; +0.00003] | 2 sur 4 | 0.3029 | 2021 : -0.0001 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : -0.0001 |
| A2_depuis_2017 | G4 | Brier P(T = 2) | +0.00001 | [-0.00003 ; +0.00005] | 1 sur 4 | 0.5794 | 2021 : -0.0000 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : -0.0000 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **G4 ne remplace pas A2_depuis_2017** | | | |
| A2_depuis_2017 | G6_G5_G4 | log-loss du total | +0.00012 | [-0.00086 ; +0.00108] | 2 sur 4 | 0.8182 | 2021 : -0.0012 ; 2022 : +0.0004 ; 2023 : +0.0015 ; 2024 : -0.0002 |
| A2_depuis_2017 | G6_G5_G4 | RPS | +0.00003 | [-0.00012 ; +0.00017] | 2 sur 4 | 0.7128 | 2021 : -0.0002 ; 2022 : +0.0001 ; 2023 : +0.0002 ; 2024 : -0.0000 |
| A2_depuis_2017 | G6_G5_G4 | Brier P(T = 0) | +0.00006 | [+0.00001 ; +0.00010] | 4 sur 4 | 0.0217 | 2021 : +0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_depuis_2017 | G6_G5_G4 | Brier P(T = 1) | -0.00002 | [-0.00014 ; +0.00011] | 2 sur 4 | 0.8094 | 2021 : -0.0002 ; 2022 : +0.0001 ; 2023 : +0.0002 ; 2024 : -0.0001 |
| A2_depuis_2017 | G6_G5_G4 | Brier P(T = 2) | -0.00003 | [-0.00013 ; +0.00006] | 1 sur 4 | 0.4884 | 2021 : -0.0000 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : -0.0001 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **G6_G5_G4 ne remplace pas A2_depuis_2017** | | | |

Écart apparié du log-loss du total par tranche de journées (A − B, positif : B meilleur ; descriptif, hors de la règle de décision) :

| A | B | Tranche | Matchs | Écart poolé | IC 95 % |
|---|---|---|---|---|---|
| A2_G0G2 | G6 | 1-5 | 967 | -0.00191 | [-0.00365 ; -0.00016] |
| A2_G0G2 | G6 | 6-10 | 964 | +0.00054 | [-0.00115 ; +0.00221] |
| A2_G0G2 | G6 | 11-19 | 1745 | +0.00060 | [-0.00048 ; +0.00169] |
| A2_G0G2 | G6 | 20-99 | 3447 | +0.00080 | [+0.00004 ; +0.00155] |
| G6 | G6_G5 | 1-5 | 967 | +0.00207 | [-0.00025 ; +0.00437] |
| G6 | G6_G5 | 6-10 | 964 | +0.00012 | [-0.00201 ; +0.00228] |
| G6 | G6_G5 | 11-19 | 1745 | +0.00095 | [-0.00072 ; +0.00262] |
| G6 | G6_G5 | 20-99 | 3447 | +0.00043 | [-0.00077 ; +0.00164] |
| A2_G0G2 | G5 | 1-5 | 967 | +0.00213 | [+0.00016 ; +0.00408] |
| A2_G0G2 | G5 | 6-10 | 964 | -0.00002 | [-0.00194 ; +0.00186] |
| A2_G0G2 | G5 | 11-19 | 1745 | +0.00075 | [-0.00088 ; +0.00235] |
| A2_G0G2 | G5 | 20-99 | 3447 | +0.00064 | [-0.00040 ; +0.00167] |
| G6_G5 | G6_G5_G4 | 1-5 | 967 | -0.00143 | [-0.00387 ; +0.00090] |
| G6_G5 | G6_G5_G4 | 6-10 | 964 | -0.00237 | [-0.00470 ; -0.00011] |
| G6_G5 | G6_G5_G4 | 11-19 | 1745 | -0.00066 | [-0.00216 ; +0.00085] |
| G6_G5 | G6_G5_G4 | 20-99 | 3447 | -0.00122 | [-0.00242 ; -0.00001] |
| G6 | G6_G4 | 1-5 | 967 | +0.00001 | [-0.00243 ; +0.00229] |
| G6 | G6_G4 | 6-10 | 964 | -0.00094 | [-0.00288 ; +0.00086] |
| G6 | G6_G4 | 11-19 | 1745 | +0.00038 | [-0.00105 ; +0.00183] |
| G6 | G6_G4 | 20-99 | 3447 | -0.00064 | [-0.00167 ; +0.00039] |
| G5 | G5_G4 | 1-5 | 967 | -0.00222 | [-0.00498 ; +0.00040] |
| G5 | G5_G4 | 6-10 | 964 | -0.00197 | [-0.00374 ; -0.00034] |
| G5 | G5_G4 | 11-19 | 1745 | -0.00005 | [-0.00134 ; +0.00120] |
| G5 | G5_G4 | 20-99 | 3447 | -0.00066 | [-0.00148 ; +0.00017] |
| A2_G0G2 | G4 | 1-5 | 967 | -0.00160 | [-0.00434 ; +0.00095] |
| A2_G0G2 | G4 | 6-10 | 964 | -0.00129 | [-0.00341 ; +0.00062] |
| A2_G0G2 | G4 | 11-19 | 1745 | +0.00033 | [-0.00117 ; +0.00185] |
| A2_G0G2 | G4 | 20-99 | 3447 | -0.00079 | [-0.00181 ; +0.00025] |
| A2_G0G2 | G6_G5_G4 | 1-5 | 967 | -0.00127 | [-0.00476 ; +0.00223] |
| A2_G0G2 | G6_G5_G4 | 6-10 | 964 | -0.00172 | [-0.00433 ; +0.00079] |
| A2_G0G2 | G6_G5_G4 | 11-19 | 1745 | +0.00088 | [-0.00143 ; +0.00324] |
| A2_G0G2 | G6_G5_G4 | 20-99 | 3447 | +0.00001 | [-0.00157 ; +0.00160] |
| A2_G0G2 | A2_depuis_2016 | 1-5 | 967 | +0.00078 | [+0.00010 ; +0.00143] |
| A2_G0G2 | A2_depuis_2016 | 6-10 | 964 | +0.00072 | [-0.00009 ; +0.00153] |
| A2_G0G2 | A2_depuis_2016 | 11-19 | 1745 | +0.00037 | [-0.00014 ; +0.00091] |
| A2_G0G2 | A2_depuis_2016 | 20-99 | 3447 | -0.00026 | [-0.00063 ; +0.00011] |
| A2_G0G2 | A2_depuis_2017 | 1-5 | 967 | -0.00049 | [-0.00192 ; +0.00093] |
| A2_G0G2 | A2_depuis_2017 | 6-10 | 964 | +0.00008 | [-0.00125 ; +0.00134] |
| A2_G0G2 | A2_depuis_2017 | 11-19 | 1745 | +0.00025 | [-0.00090 ; +0.00141] |
| A2_G0G2 | A2_depuis_2017 | 20-99 | 3447 | -0.00063 | [-0.00148 ; +0.00022] |
| A2_depuis_2016 | G5 | 1-5 | 967 | +0.00135 | [-0.00044 ; +0.00312] |
| A2_depuis_2016 | G5 | 6-10 | 964 | -0.00074 | [-0.00249 ; +0.00104] |
| A2_depuis_2016 | G5 | 11-19 | 1745 | +0.00038 | [-0.00118 ; +0.00188] |
| A2_depuis_2016 | G5 | 20-99 | 3447 | +0.00090 | [-0.00009 ; +0.00190] |
| A2_depuis_2017 | G4 | 1-5 | 967 | -0.00111 | [-0.00303 ; +0.00071] |
| A2_depuis_2017 | G4 | 6-10 | 964 | -0.00136 | [-0.00250 ; -0.00035] |
| A2_depuis_2017 | G4 | 11-19 | 1745 | +0.00008 | [-0.00069 ; +0.00085] |
| A2_depuis_2017 | G4 | 20-99 | 3447 | -0.00015 | [-0.00068 ; +0.00037] |
| A2_depuis_2017 | G6_G5_G4 | 1-5 | 967 | -0.00078 | [-0.00373 ; +0.00223] |
| A2_depuis_2017 | G6_G5_G4 | 6-10 | 964 | -0.00179 | [-0.00411 ; +0.00055] |
| A2_depuis_2017 | G6_G5_G4 | 11-19 | 1745 | +0.00063 | [-0.00136 ; +0.00266] |
| A2_depuis_2017 | G6_G5_G4 | 20-99 | 3447 | +0.00064 | [-0.00080 ; +0.00205] |

### Diagnostic de la stabilité : `stabilite_h2.yaml`

Rapport `stabilite-h2-20261101T123624` : jeu `ds-2026-11-01-e0defb32`, commit `5d76fae`, graine 20260930, 10000 rééchantillonnages.

| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |
|---|---|---|---|---|---|
| 2021-22 | 1826 | 1777 | 49 | n. d. | A2_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 240}; V_h3 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h3', 'half_life': 240}; V_h5 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h5', 'half_life': 240}; V_h10 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h10', 'half_life': 240}; V_h20 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h20', 'half_life': 240}; V_hinf : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'hinf', 'half_life': 240}; V_reset : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'reset', 'half_life': 240}; V_win10 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'win10', 'half_life': 240}; V_overlap : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'overlap_only', 'half_life': 240} |
| 2022-23 | 1826 | 1777 | 49 | n. d. | A2_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 120}; V_h3 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h3', 'half_life': 120}; V_h5 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h5', 'half_life': 120}; V_h10 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h10', 'half_life': 120}; V_h20 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h20', 'half_life': 120}; V_hinf : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'hinf', 'half_life': 120}; V_reset : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'reset', 'half_life': 120}; V_win10 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'win10', 'half_life': 240}; V_overlap : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'overlap_only', 'half_life': 120} |
| 2023-24 | 1752 | 1704 | 48 | n. d. | A2_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 240}; V_h3 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h3', 'half_life': 240}; V_h5 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h5', 'half_life': 240}; V_h10 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h10', 'half_life': 240}; V_h20 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h20', 'half_life': 240}; V_hinf : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'hinf', 'half_life': 240}; V_reset : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'reset', 'half_life': 240}; V_win10 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'win10', 'half_life': 240}; V_overlap : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'overlap_only', 'half_life': 240} |
| 2024-25 | 1752 | 1704 | 48 | n. d. | A2_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 240}; V_h3 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h3', 'half_life': 240}; V_h5 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h5', 'half_life': 240}; V_h10 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h10', 'half_life': 240}; V_h20 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'h20', 'half_life': 240}; V_hinf : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'hinf', 'half_life': 240}; V_reset : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'reset', 'half_life': 240}; V_win10 : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'win10', 'half_life': 240}; V_overlap : {'groups': ['G0', 'G1', 'G2', 'G6'], 'cohesion': 'overlap_only', 'half_life': 240} |

| Modèle | Pli | Log-loss | RPS | Brier P(T > 2,5) | Calibration : écart moyen | Pente | Couverture observée | Couverture annoncée | Log-loss score exact | Brier 1N2 | MAE E[T] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A2_G0G2 | 2021-22 | 1.8941 | 0.1312 | 0.2440 | 0.0377 | 0.88 | 87.3 % | 87.7 % | 2.9268 | 0.5922 | 1.342 |
| A2_G0G2 | 2022-23 | 1.8644 | 0.1263 | 0.2426 | 0.0196 | 1.03 | 87.7 % | 87.3 % | 2.9001 | 0.5889 | 1.293 |
| A2_G0G2 | 2023-24 | 1.8912 | 0.1298 | 0.2378 | 0.0310 | 1.17 | 87.4 % | 87.7 % | 2.9297 | 0.5828 | 1.322 |
| A2_G0G2 | 2024-25 | 1.8696 | 0.1271 | 0.2412 | 0.0288 | 0.87 | 89.0 % | 88.1 % | 2.9183 | 0.5864 | 1.308 |
| V_h3 | 2021-22 | 1.8949 | 0.1314 | 0.2446 | 0.0357 | 0.82 | 87.2 % | 87.7 % | 2.9263 | 0.5916 | 1.345 |
| V_h3 | 2022-23 | 1.8641 | 0.1263 | 0.2425 | 0.0120 | 1.03 | 87.8 % | 87.4 % | 2.8974 | 0.5879 | 1.294 |
| V_h3 | 2023-24 | 1.8905 | 0.1297 | 0.2375 | 0.0341 | 1.18 | 87.3 % | 87.7 % | 2.9259 | 0.5809 | 1.321 |
| V_h3 | 2024-25 | 1.8685 | 0.1269 | 0.2406 | 0.0312 | 0.89 | 89.0 % | 88.1 % | 2.9121 | 0.5833 | 1.305 |
| V_h5 | 2021-22 | 1.8949 | 0.1314 | 0.2446 | 0.0364 | 0.82 | 87.2 % | 87.7 % | 2.9262 | 0.5916 | 1.345 |
| V_h5 | 2022-23 | 1.8642 | 0.1263 | 0.2426 | 0.0109 | 1.02 | 87.8 % | 87.4 % | 2.8973 | 0.5877 | 1.294 |
| V_h5 | 2023-24 | 1.8905 | 0.1297 | 0.2376 | 0.0365 | 1.18 | 87.3 % | 87.7 % | 2.9262 | 0.5811 | 1.321 |
| V_h5 | 2024-25 | 1.8682 | 0.1269 | 0.2406 | 0.0279 | 0.90 | 89.0 % | 88.1 % | 2.9120 | 0.5832 | 1.305 |
| V_h10 | 2021-22 | 1.8947 | 0.1314 | 0.2445 | 0.0375 | 0.83 | 87.3 % | 87.7 % | 2.9262 | 0.5916 | 1.345 |
| V_h10 | 2022-23 | 1.8643 | 0.1264 | 0.2426 | 0.0162 | 1.02 | 87.8 % | 87.4 % | 2.8974 | 0.5876 | 1.294 |
| V_h10 | 2023-24 | 1.8909 | 0.1297 | 0.2377 | 0.0296 | 1.17 | 87.4 % | 87.7 % | 2.9271 | 0.5815 | 1.322 |
| V_h10 | 2024-25 | 1.8683 | 0.1269 | 0.2406 | 0.0290 | 0.90 | 88.9 % | 88.1 % | 2.9127 | 0.5835 | 1.305 |
| V_h20 | 2021-22 | 1.8947 | 0.1314 | 0.2445 | 0.0391 | 0.84 | 87.3 % | 87.7 % | 2.9263 | 0.5916 | 1.344 |
| V_h20 | 2022-23 | 1.8643 | 0.1264 | 0.2426 | 0.0129 | 1.02 | 87.7 % | 87.4 % | 2.8977 | 0.5878 | 1.294 |
| V_h20 | 2023-24 | 1.8912 | 0.1298 | 0.2378 | 0.0321 | 1.17 | 87.4 % | 87.7 % | 2.9280 | 0.5819 | 1.322 |
| V_h20 | 2024-25 | 1.8686 | 0.1269 | 0.2408 | 0.0312 | 0.89 | 88.9 % | 88.1 % | 2.9139 | 0.5841 | 1.306 |
| V_hinf | 2021-22 | 1.8943 | 0.1313 | 0.2442 | 0.0314 | 0.85 | 87.4 % | 87.7 % | 2.9260 | 0.5917 | 1.344 |
| V_hinf | 2022-23 | 1.8643 | 0.1263 | 0.2425 | 0.0149 | 1.03 | 87.7 % | 87.4 % | 2.8984 | 0.5881 | 1.294 |
| V_hinf | 2023-24 | 1.8913 | 0.1298 | 0.2378 | 0.0294 | 1.16 | 87.3 % | 87.7 % | 2.9287 | 0.5821 | 1.323 |
| V_hinf | 2024-25 | 1.8695 | 0.1271 | 0.2411 | 0.0249 | 0.88 | 89.1 % | 88.2 % | 2.9163 | 0.5854 | 1.309 |
| V_reset | 2021-22 | 1.8945 | 0.1313 | 0.2443 | 0.0355 | 0.84 | 87.6 % | 87.7 % | 2.9262 | 0.5918 | 1.344 |
| V_reset | 2022-23 | 1.8642 | 0.1263 | 0.2425 | 0.0200 | 1.03 | 87.7 % | 87.4 % | 2.8971 | 0.5876 | 1.294 |
| V_reset | 2023-24 | 1.8916 | 0.1299 | 0.2380 | 0.0283 | 1.14 | 87.4 % | 87.7 % | 2.9274 | 0.5813 | 1.323 |
| V_reset | 2024-25 | 1.8692 | 0.1270 | 0.2410 | 0.0227 | 0.88 | 88.9 % | 88.1 % | 2.9147 | 0.5844 | 1.307 |
| V_win10 | 2021-22 | 1.8949 | 0.1314 | 0.2447 | 0.0349 | 0.82 | 87.2 % | 87.7 % | 2.9264 | 0.5916 | 1.345 |
| V_win10 | 2022-23 | 1.8638 | 0.1263 | 0.2425 | 0.0143 | 1.03 | 87.8 % | 87.5 % | 2.8975 | 0.5882 | 1.293 |
| V_win10 | 2023-24 | 1.8904 | 0.1297 | 0.2375 | 0.0323 | 1.18 | 87.3 % | 87.8 % | 2.9261 | 0.5813 | 1.321 |
| V_win10 | 2024-25 | 1.8682 | 0.1269 | 0.2405 | 0.0289 | 0.90 | 88.8 % | 88.1 % | 2.9122 | 0.5835 | 1.305 |
| V_overlap | 2021-22 | 1.8943 | 0.1313 | 0.2442 | 0.0368 | 0.86 | 87.3 % | 87.8 % | 2.9266 | 0.5922 | 1.343 |
| V_overlap | 2022-23 | 1.8643 | 0.1263 | 0.2425 | 0.0142 | 1.03 | 87.8 % | 87.4 % | 2.8992 | 0.5886 | 1.293 |
| V_overlap | 2023-24 | 1.8917 | 0.1299 | 0.2379 | 0.0269 | 1.16 | 87.4 % | 87.7 % | 2.9292 | 0.5823 | 1.323 |
| V_overlap | 2024-25 | 1.8692 | 0.1270 | 0.2411 | 0.0282 | 0.88 | 88.9 % | 88.1 % | 2.9166 | 0.5859 | 1.307 |

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| A2_G0G2 | 6962 | 1.8798 | 0.1286 | 0.2414 | 0.0159 | 0.97 | +0.025 |
| V_h3 | 6962 | 1.8795 | 0.1286 | 0.2414 | 0.0081 | 0.96 | +0.024 |
| V_h5 | 6962 | 1.8795 | 0.1286 | 0.2414 | 0.0115 | 0.96 | +0.024 |
| V_h10 | 6962 | 1.8796 | 0.1286 | 0.2414 | 0.0106 | 0.96 | +0.025 |
| V_h20 | 6962 | 1.8797 | 0.1286 | 0.2415 | 0.0101 | 0.96 | +0.025 |
| V_hinf | 6962 | 1.8798 | 0.1286 | 0.2415 | 0.0096 | 0.96 | +0.018 |
| V_reset | 6962 | 1.8799 | 0.1286 | 0.2415 | 0.0121 | 0.96 | +0.024 |
| V_win10 | 6962 | 1.8794 | 0.1286 | 0.2413 | 0.0121 | 0.96 | +0.023 |
| V_overlap | 6962 | 1.8799 | 0.1286 | 0.2415 | 0.0122 | 0.96 | +0.026 |

Petits totaux, calibration poolée sur les 4 plis :

| Modèle | k | P(T = k) prédite | observée | Brier | Écart moyen par décile | Pente |
|---|---|---|---|---|---|---|
| A2_G0G2 | 0 | 6.5 % | 6.3 % | 0.0584 | 0.0104 | 0.79 |
| A2_G0G2 | 1 | 17.4 % | 16.4 % | 0.1358 | 0.0153 | 1.01 |
| A2_G0G2 | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0138 | 1.07 |
| V_h3 | 0 | 6.5 % | 6.3 % | 0.0584 | 0.0101 | 0.81 |
| V_h3 | 1 | 17.3 % | 16.4 % | 0.1358 | 0.0124 | 0.99 |
| V_h3 | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0112 | 1.06 |
| V_h5 | 0 | 6.5 % | 6.3 % | 0.0584 | 0.0096 | 0.81 |
| V_h5 | 1 | 17.3 % | 16.4 % | 0.1358 | 0.0133 | 0.99 |
| V_h5 | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0110 | 1.06 |
| V_h10 | 0 | 6.5 % | 6.3 % | 0.0584 | 0.0096 | 0.81 |
| V_h10 | 1 | 17.3 % | 16.4 % | 0.1358 | 0.0122 | 0.99 |
| V_h10 | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0121 | 1.06 |
| V_h20 | 0 | 6.5 % | 6.3 % | 0.0584 | 0.0105 | 0.81 |
| V_h20 | 1 | 17.4 % | 16.4 % | 0.1358 | 0.0118 | 0.99 |
| V_h20 | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0137 | 1.05 |
| V_hinf | 0 | 6.5 % | 6.3 % | 0.0584 | 0.0105 | 0.81 |
| V_hinf | 1 | 17.3 % | 16.4 % | 0.1358 | 0.0143 | 0.99 |
| V_hinf | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0142 | 1.05 |
| V_reset | 0 | 6.5 % | 6.3 % | 0.0584 | 0.0111 | 0.82 |
| V_reset | 1 | 17.3 % | 16.4 % | 0.1358 | 0.0121 | 0.98 |
| V_reset | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0147 | 1.05 |
| V_win10 | 0 | 6.5 % | 6.3 % | 0.0584 | 0.0092 | 0.81 |
| V_win10 | 1 | 17.3 % | 16.4 % | 0.1358 | 0.0122 | 0.99 |
| V_win10 | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0111 | 1.07 |
| V_overlap | 0 | 6.5 % | 6.3 % | 0.0584 | 0.0096 | 0.80 |
| V_overlap | 1 | 17.4 % | 16.4 % | 0.1358 | 0.0128 | 0.99 |
| V_overlap | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0142 | 1.06 |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| A2_G0G2 | V_h3 | log-loss du total | +0.00031 | [-0.00036 ; +0.00097] | 3 sur 4 | 0.3617 | 2021 : -0.0009 ; 2022 : +0.0003 ; 2023 : +0.0007 ; 2024 : +0.0012 |
| A2_G0G2 | V_h3 | RPS | +0.00003 | [-0.00007 ; +0.00012] | 3 sur 4 | 0.5495 | 2021 : -0.0002 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : +0.0002 |
| A2_G0G2 | V_h3 | Brier P(T = 0) | +0.00002 | [-0.00001 ; +0.00006] | 3 sur 4 | 0.1200 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | V_h3 | Brier P(T = 1) | -0.00001 | [-0.00009 ; +0.00007] | 3 sur 4 | 0.8481 | 2021 : -0.0002 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| A2_G0G2 | V_h3 | Brier P(T = 2) | -0.00000 | [-0.00007 ; +0.00006] | 2 sur 4 | 0.9139 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **V_h3 ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | V_h5 | log-loss du total | +0.00035 | [-0.00030 ; +0.00100] | 3 sur 4 | 0.2964 | 2021 : -0.0008 ; 2022 : +0.0002 ; 2023 : +0.0007 ; 2024 : +0.0014 |
| A2_G0G2 | V_h5 | RPS | +0.00003 | [-0.00006 ; +0.00013] | 2 sur 4 | 0.5088 | 2021 : -0.0002 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : +0.0002 |
| A2_G0G2 | V_h5 | Brier P(T = 0) | +0.00003 | [-0.00000 ; +0.00006] | 3 sur 4 | 0.0838 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | V_h5 | Brier P(T = 1) | -0.00001 | [-0.00009 ; +0.00007] | 3 sur 4 | 0.7698 | 2021 : -0.0002 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| A2_G0G2 | V_h5 | Brier P(T = 2) | -0.00000 | [-0.00007 ; +0.00006] | 2 sur 4 | 0.9611 | 2021 : -0.0001 ; 2022 : -0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **V_h5 ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | V_h10 | log-loss du total | +0.00025 | [-0.00035 ; +0.00083] | 3 sur 4 | 0.4121 | 2021 : -0.0007 ; 2022 : +0.0001 ; 2023 : +0.0003 ; 2024 : +0.0013 |
| A2_G0G2 | V_h10 | RPS | +0.00001 | [-0.00007 ; +0.00010] | 2 sur 4 | 0.7523 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0002 |
| A2_G0G2 | V_h10 | Brier P(T = 0) | +0.00003 | [+0.00000 ; +0.00006] | 3 sur 4 | 0.0341 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | V_h10 | Brier P(T = 1) | -0.00002 | [-0.00009 ; +0.00005] | 2 sur 4 | 0.4979 | 2021 : -0.0002 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : -0.0000 |
| A2_G0G2 | V_h10 | Brier P(T = 2) | -0.00001 | [-0.00007 ; +0.00005] | 1 sur 4 | 0.7468 | 2021 : -0.0001 ; 2022 : -0.0001 ; 2023 : -0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **V_h10 ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | V_h20 | log-loss du total | +0.00010 | [-0.00043 ; +0.00064] | 2 sur 4 | 0.7020 | 2021 : -0.0006 ; 2022 : +0.0001 ; 2023 : -0.0000 ; 2024 : +0.0010 |
| A2_G0G2 | V_h20 | RPS | -0.00001 | [-0.00009 ; +0.00007] | 1 sur 4 | 0.8426 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : -0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | V_h20 | Brier P(T = 0) | +0.00003 | [+0.00000 ; +0.00005] | 3 sur 4 | 0.0227 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | V_h20 | Brier P(T = 1) | -0.00003 | [-0.00009 ; +0.00003] | 2 sur 4 | 0.3385 | 2021 : -0.0002 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : -0.0000 |
| A2_G0G2 | V_h20 | Brier P(T = 2) | -0.00002 | [-0.00007 ; +0.00003] | 1 sur 4 | 0.5223 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : -0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **V_h20 ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | V_hinf | log-loss du total | -0.00004 | [-0.00053 ; +0.00045] | 2 sur 4 | 0.8633 | 2021 : -0.0003 ; 2022 : +0.0001 ; 2023 : -0.0001 ; 2024 : +0.0001 |
| A2_G0G2 | V_hinf | RPS | -0.00002 | [-0.00009 ; +0.00005] | 1 sur 4 | 0.5173 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : -0.0000 ; 2024 : +0.0000 |
| A2_G0G2 | V_hinf | Brier P(T = 0) | +0.00003 | [+0.00001 ; +0.00006] | 4 sur 4 | 0.0094 | 2021 : +0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | V_hinf | Brier P(T = 1) | -0.00003 | [-0.00008 ; +0.00003] | 1 sur 4 | 0.3981 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : -0.0000 ; 2024 : -0.0000 |
| A2_G0G2 | V_hinf | Brier P(T = 2) | -0.00002 | [-0.00006 ; +0.00003] | 1 sur 4 | 0.4262 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : -0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **V_hinf ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | V_reset | log-loss du total | -0.00007 | [-0.00080 ; +0.00063] | 2 sur 4 | 0.8431 | 2021 : -0.0005 ; 2022 : +0.0002 ; 2023 : -0.0004 ; 2024 : +0.0004 |
| A2_G0G2 | V_reset | RPS | -0.00003 | [-0.00014 ; +0.00007] | 1 sur 4 | 0.5530 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : -0.0001 ; 2024 : +0.0001 |
| A2_G0G2 | V_reset | Brier P(T = 0) | +0.00004 | [-0.00000 ; +0.00007] | 3 sur 4 | 0.0639 | 2021 : -0.0000 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| A2_G0G2 | V_reset | Brier P(T = 1) | -0.00005 | [-0.00013 ; +0.00003] | 1 sur 4 | 0.2178 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : -0.0000 ; 2024 : -0.0001 |
| A2_G0G2 | V_reset | Brier P(T = 2) | -0.00002 | [-0.00009 ; +0.00004] | 1 sur 4 | 0.5054 | 2021 : -0.0001 ; 2022 : -0.0001 ; 2023 : -0.0001 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **V_reset ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | V_win10 | log-loss du total | +0.00045 | [-0.00038 ; +0.00126] | 3 sur 4 | 0.2796 | 2021 : -0.0009 ; 2022 : +0.0006 ; 2023 : +0.0008 ; 2024 : +0.0014 |
| A2_G0G2 | V_win10 | RPS | +0.00005 | [-0.00007 ; +0.00016] | 3 sur 4 | 0.4171 | 2021 : -0.0002 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : +0.0002 |
| A2_G0G2 | V_win10 | Brier P(T = 0) | +0.00003 | [-0.00000 ; +0.00007] | 3 sur 4 | 0.0785 | 2021 : -0.0000 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| A2_G0G2 | V_win10 | Brier P(T = 1) | -0.00001 | [-0.00011 ; +0.00010] | 2 sur 4 | 0.8746 | 2021 : -0.0002 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| A2_G0G2 | V_win10 | Brier P(T = 2) | +0.00000 | [-0.00007 ; +0.00008] | 2 sur 4 | 0.9016 | 2021 : -0.0001 ; 2022 : -0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **V_win10 ne remplace pas A2_G0G2** | | | |
| A2_G0G2 | V_overlap | log-loss du total | -0.00006 | [-0.00037 ; +0.00025] | 2 sur 4 | 0.7011 | 2021 : -0.0003 ; 2022 : +0.0001 ; 2023 : -0.0005 ; 2024 : +0.0004 |
| A2_G0G2 | V_overlap | RPS | -0.00002 | [-0.00007 ; +0.00002] | 1 sur 4 | 0.3562 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : -0.0001 ; 2024 : +0.0001 |
| A2_G0G2 | V_overlap | Brier P(T = 0) | +0.00001 | [-0.00000 ; +0.00002] | 4 sur 4 | 0.1651 | 2021 : +0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| A2_G0G2 | V_overlap | Brier P(T = 1) | -0.00002 | [-0.00006 ; +0.00002] | 2 sur 4 | 0.2599 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : -0.0000 ; 2024 : +0.0000 |
| A2_G0G2 | V_overlap | Brier P(T = 2) | -0.00000 | [-0.00004 ; +0.00003] | 2 sur 4 | 0.8254 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : -0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **V_overlap ne remplace pas A2_G0G2** | | | |
| V_overlap | V_h3 | log-loss du total | +0.00037 | [-0.00018 ; +0.00091] | 3 sur 4 | 0.1842 | 2021 : -0.0006 ; 2022 : +0.0002 ; 2023 : +0.0011 ; 2024 : +0.0007 |
| V_overlap | V_h3 | RPS | +0.00005 | [-0.00003 ; +0.00013] | 3 sur 4 | 0.2032 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0002 ; 2024 : +0.0001 |
| V_overlap | V_h3 | Brier P(T = 0) | +0.00001 | [-0.00001 ; +0.00004] | 3 sur 4 | 0.2800 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| V_overlap | V_h3 | Brier P(T = 1) | +0.00002 | [-0.00005 ; +0.00008] | 2 sur 4 | 0.6525 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : -0.0000 |
| V_overlap | V_h3 | Brier P(T = 2) | +0.00000 | [-0.00005 ; +0.00005] | 2 sur 4 | 0.9958 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **V_h3 ne remplace pas V_overlap** | | | |
| V_overlap | V_h5 | log-loss du total | +0.00041 | [-0.00012 ; +0.00095] | 3 sur 4 | 0.1340 | 2021 : -0.0005 ; 2022 : +0.0001 ; 2023 : +0.0011 ; 2024 : +0.0010 |
| V_overlap | V_h5 | RPS | +0.00005 | [-0.00002 ; +0.00013] | 3 sur 4 | 0.1746 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0002 ; 2024 : +0.0001 |
| V_overlap | V_h5 | Brier P(T = 0) | +0.00002 | [-0.00001 ; +0.00004] | 3 sur 4 | 0.2056 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| V_overlap | V_h5 | Brier P(T = 1) | +0.00001 | [-0.00005 ; +0.00008] | 3 sur 4 | 0.7290 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| V_overlap | V_h5 | Brier P(T = 2) | +0.00000 | [-0.00005 ; +0.00005] | 2 sur 4 | 0.9366 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **V_h5 ne remplace pas V_overlap** | | | |
| V_overlap | V_h10 | log-loss du total | +0.00031 | [-0.00016 ; +0.00077] | 2 sur 4 | 0.1920 | 2021 : -0.0004 ; 2022 : -0.0000 ; 2023 : +0.0008 ; 2024 : +0.0009 |
| V_overlap | V_h10 | RPS | +0.00004 | [-0.00003 ; +0.00010] | 2 sur 4 | 0.3000 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : +0.0001 |
| V_overlap | V_h10 | Brier P(T = 0) | +0.00002 | [-0.00000 ; +0.00004] | 3 sur 4 | 0.0862 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| V_overlap | V_h10 | Brier P(T = 1) | -0.00000 | [-0.00006 ; +0.00005] | 2 sur 4 | 0.9620 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0001 ; 2024 : -0.0000 |
| V_overlap | V_h10 | Brier P(T = 2) | -0.00001 | [-0.00005 ; +0.00004] | 2 sur 4 | 0.7951 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **V_h10 ne remplace pas V_overlap** | | | |
| V_overlap | V_h20 | log-loss du total | +0.00017 | [-0.00023 ; +0.00056] | 3 sur 4 | 0.4132 | 2021 : -0.0003 ; 2022 : +0.0000 ; 2023 : +0.0005 ; 2024 : +0.0006 |
| V_overlap | V_h20 | RPS | +0.00001 | [-0.00004 ; +0.00007] | 2 sur 4 | 0.6317 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : +0.0001 |
| V_overlap | V_h20 | Brier P(T = 0) | +0.00002 | [+0.00000 ; +0.00004] | 3 sur 4 | 0.0527 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| V_overlap | V_h20 | Brier P(T = 1) | -0.00001 | [-0.00006 ; +0.00004] | 2 sur 4 | 0.7349 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : -0.0000 |
| V_overlap | V_h20 | Brier P(T = 2) | -0.00001 | [-0.00005 ; +0.00002] | 1 sur 4 | 0.4865 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : -0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **V_h20 ne remplace pas V_overlap** | | | |
| V_overlap | V_hinf | log-loss du total | +0.00002 | [-0.00035 ; +0.00037] | 3 sur 4 | 0.9199 | 2021 : +0.0000 ; 2022 : +0.0000 ; 2023 : +0.0004 ; 2024 : -0.0003 |
| V_overlap | V_hinf | RPS | -0.00000 | [-0.00005 ; +0.00005] | 1 sur 4 | 0.9634 | 2021 : -0.0000 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : -0.0000 |
| V_overlap | V_hinf | Brier P(T = 0) | +0.00002 | [+0.00000 ; +0.00004] | 3 sur 4 | 0.0199 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| V_overlap | V_hinf | Brier P(T = 1) | -0.00000 | [-0.00005 ; +0.00004] | 2 sur 4 | 0.9083 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : -0.0000 |
| V_overlap | V_hinf | Brier P(T = 2) | -0.00001 | [-0.00005 ; +0.00002] | 2 sur 4 | 0.3600 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **V_hinf ne remplace pas V_overlap** | | | |
| V_overlap | V_reset | log-loss du total | -0.00001 | [-0.00062 ; +0.00057] | 2 sur 4 | 0.9737 | 2021 : -0.0002 ; 2022 : +0.0001 ; 2023 : +0.0001 ; 2024 : -0.0000 |
| V_overlap | V_reset | RPS | -0.00001 | [-0.00010 ; +0.00007] | 2 sur 4 | 0.8403 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| V_overlap | V_reset | Brier P(T = 0) | +0.00003 | [-0.00001 ; +0.00006] | 3 sur 4 | 0.1397 | 2021 : -0.0000 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| V_overlap | V_reset | Brier P(T = 1) | -0.00003 | [-0.00010 ; +0.00004] | 2 sur 4 | 0.4485 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : -0.0001 |
| V_overlap | V_reset | Brier P(T = 2) | -0.00002 | [-0.00007 ; +0.00004] | 1 sur 4 | 0.5164 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : -0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **V_reset ne remplace pas V_overlap** | | | |
| V_overlap | V_win10 | log-loss du total | +0.00051 | [-0.00023 ; +0.00123] | 3 sur 4 | 0.1681 | 2021 : -0.0006 ; 2022 : +0.0005 ; 2023 : +0.0012 ; 2024 : +0.0009 |
| V_overlap | V_win10 | RPS | +0.00007 | [-0.00004 ; +0.00017] | 3 sur 4 | 0.1842 | 2021 : -0.0001 ; 2022 : +0.0000 ; 2023 : +0.0002 ; 2024 : +0.0001 |
| V_overlap | V_win10 | Brier P(T = 0) | +0.00002 | [-0.00001 ; +0.00006] | 3 sur 4 | 0.1760 | 2021 : -0.0000 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| V_overlap | V_win10 | Brier P(T = 1) | +0.00001 | [-0.00008 ; +0.00011] | 2 sur 4 | 0.7664 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| V_overlap | V_win10 | Brier P(T = 2) | +0.00001 | [-0.00006 ; +0.00008] | 2 sur 4 | 0.8077 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **V_win10 ne remplace pas V_overlap** | | | |

Écart apparié du log-loss du total par tranche de journées (A − B, positif : B meilleur ; descriptif, hors de la règle de décision) :

| A | B | Tranche | Matchs | Écart poolé | IC 95 % |
|---|---|---|---|---|---|
| A2_G0G2 | V_h3 | 1-5 | 776 | -0.00197 | [-0.00411 ; +0.00018] |
| A2_G0G2 | V_h3 | 6-10 | 970 | -0.00014 | [-0.00219 ; +0.00186] |
| A2_G0G2 | V_h3 | 11-19 | 1746 | +0.00060 | [-0.00062 ; +0.00187] |
| A2_G0G2 | V_h3 | 20-99 | 3470 | +0.00079 | [-0.00008 ; +0.00167] |
| A2_G0G2 | V_h5 | 1-5 | 776 | -0.00174 | [-0.00389 ; +0.00040] |
| A2_G0G2 | V_h5 | 6-10 | 970 | +0.00018 | [-0.00179 ; +0.00211] |
| A2_G0G2 | V_h5 | 11-19 | 1746 | +0.00057 | [-0.00062 ; +0.00182] |
| A2_G0G2 | V_h5 | 20-99 | 3470 | +0.00075 | [-0.00011 ; +0.00162] |
| A2_G0G2 | V_h10 | 1-5 | 776 | -0.00192 | [-0.00408 ; +0.00021] |
| A2_G0G2 | V_h10 | 6-10 | 970 | +0.00032 | [-0.00146 ; +0.00211] |
| A2_G0G2 | V_h10 | 11-19 | 1746 | +0.00045 | [-0.00059 ; +0.00154] |
| A2_G0G2 | V_h10 | 20-99 | 3470 | +0.00061 | [-0.00014 ; +0.00136] |
| A2_G0G2 | V_h20 | 1-5 | 776 | -0.00219 | [-0.00435 ; -0.00001] |
| A2_G0G2 | V_h20 | 6-10 | 970 | +0.00020 | [-0.00147 ; +0.00188] |
| A2_G0G2 | V_h20 | 11-19 | 1746 | +0.00037 | [-0.00053 ; +0.00132] |
| A2_G0G2 | V_h20 | 20-99 | 3470 | +0.00045 | [-0.00018 ; +0.00110] |
| A2_G0G2 | V_hinf | 1-5 | 776 | -0.00229 | [-0.00434 ; -0.00027] |
| A2_G0G2 | V_hinf | 6-10 | 970 | +0.00023 | [-0.00130 ; +0.00177] |
| A2_G0G2 | V_hinf | 11-19 | 1746 | +0.00011 | [-0.00074 ; +0.00101] |
| A2_G0G2 | V_hinf | 20-99 | 3470 | +0.00031 | [-0.00028 ; +0.00089] |
| A2_G0G2 | V_reset | 1-5 | 776 | -0.00428 | [-0.00825 ; -0.00026] |
| A2_G0G2 | V_reset | 6-10 | 970 | -0.00040 | [-0.00238 ; +0.00150] |
| A2_G0G2 | V_reset | 11-19 | 1746 | +0.00067 | [-0.00032 ; +0.00169] |
| A2_G0G2 | V_reset | 20-99 | 3470 | +0.00059 | [-0.00017 ; +0.00136] |
| A2_G0G2 | V_win10 | 1-5 | 776 | -0.00171 | [-0.00425 ; +0.00077] |
| A2_G0G2 | V_win10 | 6-10 | 970 | +0.00013 | [-0.00250 ; +0.00261] |
| A2_G0G2 | V_win10 | 11-19 | 1746 | +0.00064 | [-0.00083 ; +0.00210] |
| A2_G0G2 | V_win10 | 20-99 | 3470 | +0.00093 | [-0.00016 ; +0.00202] |
| A2_G0G2 | V_overlap | 1-5 | 776 | -0.00053 | [-0.00149 ; +0.00042] |
| A2_G0G2 | V_overlap | 6-10 | 970 | +0.00006 | [-0.00094 ; +0.00105] |
| A2_G0G2 | V_overlap | 11-19 | 1746 | +0.00010 | [-0.00048 ; +0.00069] |
| A2_G0G2 | V_overlap | 20-99 | 3470 | -0.00007 | [-0.00049 ; +0.00034] |
| V_overlap | V_h3 | 1-5 | 776 | -0.00144 | [-0.00327 ; +0.00035] |
| V_overlap | V_h3 | 6-10 | 970 | -0.00020 | [-0.00180 ; +0.00137] |
| V_overlap | V_h3 | 11-19 | 1746 | +0.00049 | [-0.00050 ; +0.00150] |
| V_overlap | V_h3 | 20-99 | 3470 | +0.00087 | [+0.00014 ; +0.00160] |
| V_overlap | V_h5 | 1-5 | 776 | -0.00121 | [-0.00303 ; +0.00058] |
| V_overlap | V_h5 | 6-10 | 970 | +0.00011 | [-0.00147 ; +0.00170] |
| V_overlap | V_h5 | 11-19 | 1746 | +0.00046 | [-0.00051 ; +0.00146] |
| V_overlap | V_h5 | 20-99 | 3470 | +0.00082 | [+0.00012 ; +0.00153] |
| V_overlap | V_h10 | 1-5 | 776 | -0.00139 | [-0.00319 ; +0.00036] |
| V_overlap | V_h10 | 6-10 | 970 | +0.00026 | [-0.00116 ; +0.00166] |
| V_overlap | V_h10 | 11-19 | 1746 | +0.00035 | [-0.00049 ; +0.00118] |
| V_overlap | V_h10 | 20-99 | 3470 | +0.00068 | [+0.00011 ; +0.00125] |
| V_overlap | V_h20 | 1-5 | 776 | -0.00165 | [-0.00343 ; +0.00007] |
| V_overlap | V_h20 | 6-10 | 970 | +0.00014 | [-0.00109 ; +0.00134] |
| V_overlap | V_h20 | 11-19 | 1746 | +0.00027 | [-0.00046 ; +0.00097] |
| V_overlap | V_h20 | 20-99 | 3470 | +0.00053 | [+0.00008 ; +0.00099] |
| V_overlap | V_hinf | 1-5 | 776 | -0.00176 | [-0.00340 ; -0.00018] |
| V_overlap | V_hinf | 6-10 | 970 | +0.00017 | [-0.00086 ; +0.00117] |
| V_overlap | V_hinf | 11-19 | 1746 | +0.00001 | [-0.00064 ; +0.00067] |
| V_overlap | V_hinf | 20-99 | 3470 | +0.00038 | [-0.00005 ; +0.00082] |
| V_overlap | V_reset | 1-5 | 776 | -0.00375 | [-0.00718 ; -0.00024] |
| V_overlap | V_reset | 6-10 | 970 | -0.00046 | [-0.00185 ; +0.00086] |
| V_overlap | V_reset | 11-19 | 1746 | +0.00056 | [-0.00025 ; +0.00138] |
| V_overlap | V_reset | 20-99 | 3470 | +0.00066 | [-0.00001 ; +0.00133] |
| V_overlap | V_win10 | 1-5 | 776 | -0.00117 | [-0.00348 ; +0.00101] |
| V_overlap | V_win10 | 6-10 | 970 | +0.00007 | [-0.00221 ; +0.00219] |
| V_overlap | V_win10 | 11-19 | 1746 | +0.00054 | [-0.00076 ; +0.00182] |
| V_overlap | V_win10 | 20-99 | 3470 | +0.00100 | [+0.00002 ; +0.00200] |
