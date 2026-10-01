# Tirs de football-data en live : effet sur les prédictions

*Mesure du 2026-10-01 (décision 12 de la partie 5, ADR-0035). Jeu `ds-2026-09-30-ba2b91f7`, modèles de rejeu des 4 plis, 10000 rééchantillonnages, graine 20260930, 1 essai. Produit par `python -m foot_predictor.inference.shots_check` ; données dans `reports/inference/tirs_football_data.json`.*

Écart = log-loss du total avec la variante − log-loss avec les tirs de référence (API là où elle est complète), même modèle, mêmes matchs. **Positif : la variante est moins bonne.**

| Variante | Écart poolé | IC 95 % | Exclut 0 | DM (p) | 2021-22 | 2022-23 | 2023-24 | 2024-25 |
|---|---|---|---|---|---|---|---|---|
| Saison S en football-data (situation du live) | -0.00002 | [-0.00021 ; +0.00018] | non | 0.863 | -0.00003 | -0.00029 | -0.00009 | +0.00035 |
| Football-data pour toute l'histoire (extrême) | +0.00086 | [-0.00012 ; +0.00189] | non | 0.090 | +0.00286 | +0.00023 | -0.00032 | +0.00061 |

Par championnat :

| Variante | Championnat | Écart | IC 95 % | Exclut 0 | DM (p) | Holm (p) |
|---|---|---|---|---|---|---|
| Saison S en football-data (situation du live) | Premier League | +0.00005 | [-0.00006 ; +0.00016] | non | 0.344 | 1.000 |
| Saison S en football-data (situation du live) | La Liga | +0.00008 | [-0.00009 ; +0.00025] | non | 0.382 | 1.000 |
| Saison S en football-data (situation du live) | Bundesliga | -0.00036 | [-0.00140 ; +0.00070] | non | 0.509 | 1.000 |
| Saison S en football-data (situation du live) | Serie A | +0.00004 | [-0.00023 ; +0.00030] | non | 0.794 | 1.000 |
| Saison S en football-data (situation du live) | Ligue 1 | +0.00004 | [-0.00014 ; +0.00023] | non | 0.631 | 1.000 |
| Football-data pour toute l'histoire (extrême) | Premier League | +0.00011 | [-0.00005 ; +0.00028] | non | 0.181 | 0.725 |
| Football-data pour toute l'histoire (extrême) | La Liga | -0.00012 | [-0.00041 ; +0.00016] | non | 0.401 | 1.000 |
| Football-data pour toute l'histoire (extrême) | Bundesliga | -0.00039 | [-0.00241 ; +0.00168] | non | 0.713 | 1.000 |
| Football-data pour toute l'histoire (extrême) | Serie A | +0.00436 | [+0.00015 ; +0.00851] | oui | 0.046 | 0.232 |
| Football-data pour toute l'histoire (extrême) | Ligue 1 | +0.00001 | [-0.00025 ; +0.00029] | non | 0.922 | 1.000 |

Matchs comparés et part des lignes de test dont une variable du modèle change :

| Variante | Pli | Communs | Référence | Variante | Lignes changées |
|---|---|---|---|---|---|
| Saison S en football-data (situation du live) | 2021 | 1826 | 1826 | 1826 | 97.7% |
| Saison S en football-data (situation du live) | 2022 | 1826 | 1826 | 1826 | 91.5% |
| Saison S en football-data (situation du live) | 2023 | 1752 | 1752 | 1752 | 88.1% |
| Saison S en football-data (situation du live) | 2024 | 1752 | 1752 | 1752 | 96.4% |
| Football-data pour toute l'histoire (extrême) | 2021 | 1826 | 1826 | 1826 | 100.0% |
| Football-data pour toute l'histoire (extrême) | 2022 | 1826 | 1826 | 1826 | 100.0% |
| Football-data pour toute l'histoire (extrême) | 2023 | 1752 | 1752 | 1752 | 100.0% |
| Football-data pour toute l'histoire (extrême) | 2024 | 1752 | 1752 | 1752 | 100.0% |

Écart des sources (tirs cadrés football-data − API, par équipe et par match, quand les deux sont complets) :

| Saisons | Championnat | Équipe-matchs | Écart moyen | Écart absolu moyen | Identiques |
|---|---|---|---|---|---|
| 2021-2024 | Premier League | 3040 | -0.004 | 0.007 | 99.4% |
| 2021-2024 | La Liga | 3040 | +0.008 | 0.035 | 97.1% |
| 2021-2024 | Bundesliga | 2446 | +0.097 | 0.245 | 78.3% |
| 2021-2024 | Serie A | 3038 | +0.000 | 0.036 | 96.7% |
| 2021-2024 | Ligue 1 | 2744 | +0.001 | 0.028 | 97.6% |
| 2015-2024 | Premier League | 7598 | -0.003 | 0.019 | 98.3% |
| 2015-2024 | La Liga | 7598 | +0.004 | 0.037 | 96.7% |
| 2015-2024 | Bundesliga | 6116 | +0.059 | 0.164 | 85.7% |
| 2015-2024 | Serie A | 7598 | +0.264 | 0.320 | 79.3% |
| 2015-2024 | Ligue 1 | 7100 | +0.003 | 0.037 | 96.7% |

## Conclusion

Critère (ADR-0041) : intervalle poolé qui exclut 0, ou championnat dont la p-valeur de Diebold-Mariano corrigée de Holm (5 championnats) est sous 5 %.

**Aucun écart significatif** : le critère de révision de l'ADR-0035 n'est pas atteint ; les tirs de football-data sont utilisés tels quels en live (constat chiffré, ADR-0041).
