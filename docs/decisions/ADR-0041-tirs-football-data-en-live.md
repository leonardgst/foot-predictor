# ADR-0041 — Tirs de football-data en live : pas de recalibration (constat chiffré)

- **Statut** : acceptée
- **Date** : 2026-10-01
- **Référence** : critère de révision de l'ADR-0035 ; décision 12 de la partie 5 ; ADR-0011 (live après l'abonnement), ADR-0040 ; `docs/resultats/tirs_live.md`, `reports/inference/tirs_football_data.json`

## Contexte

Le modèle apprend sur des tirs d'API-FOOTBALL (2015-16 et après, ADR-0035) ; après le gel, les matchs joués n'auront que ceux de football-data (ADR-0011). Les deux sources ne coïncident exactement que sur 72 % des matchs du top 5. Le critère de révision de l'ADR-0035 demande de mesurer l'effet sur les prédictions, et de recalibrer les tirs de football-data (dans `inference/`) si l'écart est significatif.

Mesure (méthode figée par la décision 12, `src/foot_predictor/inference/shots_check.py`) : pour chaque pli S de 2021-22 à 2024-25, modèle de rejeu de S inchangé, jeu `ds-2026-09-30-ba2b91f7` ; variante « saison S » (les matchs de S perdent leurs tirs de l'API avant `build_frame`, situation du live) et variante extrême (football-data pour toute l'histoire). Écart de log-loss du total apparié, bootstrap par blocs de journées (10 000 tirages, graine 20260930), 7 156 matchs par variante, 1 essai.

| Variante | Écart poolé (variante − API) | IC 95 % | Championnat le plus touché (p de Holm) |
|---|---|---|---|
| Saison S en football-data | −0,00002 | [−0,00021 ; +0,00018] | aucun sous 0,05 (au mieux 1,0) |
| Football-data pour toute l'histoire | +0,00086 | [−0,00012 ; +0,00189] | Serie A : +0,0044, p brute 0,046, p de Holm 0,23 |

Pour échelle : la log-loss du total vaut environ 1,9 par match ; l'écart du live en est moins d'un dix-millième, celui de la variante extrême moins d'un millième. Sur 2021-22 à 2024-25, les tirs cadrés des deux sources sont identiques pour 97 à 99 % des équipes-matchs, sauf en Bundesliga (78 %, +0,10 tir cadré par équipe en moyenne) ; la Serie A ne s'écarte que sur 2015-16 à 2020-21 (rupture de 2018-19 à 2020-21 de l'ADR-0035), ce qui explique sa sensibilité dans la seule variante extrême.

## Options envisagées

1. **Recalibrer les tirs de football-data sur ceux de l'API, par championnat**, dans `inference/` : corrige un écart qu'on ne mesure pas ; une transformation de plus à justifier, à tester et à maintenir, et un risque de sur-correction.
2. **Constat chiffré, tirs de football-data utilisés tels quels en live**, avec une règle de lecture explicite et une surveillance.

## Décision

Option 2. Le critère de révision de l'ADR-0035 **n'est pas atteint** : aucun intervalle poolé n'exclut 0 et aucun championnat n'est significatif après correction de Holm.

« Significatif » est lu ainsi, et le sera pour toute nouvelle mesure de ce type : intervalle poolé à 95 % qui exclut 0, **ou** championnat dont la p-valeur de Diebold-Mariano corrigée de Holm sur les 5 championnats de la variante est sous 0,05. La correction est nécessaire : avec 10 intervalles par championnat, en trouver un qui exclut 0 par hasard est attendu (c'est le cas de la Serie A dans la variante extrême, p brute 0,046). Les deux variantes comptent pour le critère, la variante extrême représentant le long terme où l'historique de football-data s'allonge.

## Conséquences

- Aucune recalibration dans `inference/` ; `features/` reste inchangé (figé par `pre-scelle-h1`). Le live (5.10) prend les tirs de football-data tels quels, via la règle de l'ADR-0035.
- **Surveillance** : la variante extrême de la Serie A est le point faible (+0,0044, non significatif). La mesure est rejouable en 30 secondes (`uv run python -m foot_predictor.inference.shots_check`) ; elle sera refaite, avec la même règle, après le test scellé si la saison 2025-26 devient une saison de développement, et au plus tard quand deux saisons complètes de football-data seront dans l'historique.
- **Critère de révision** : une nouvelle mesure significative au sens ci-dessus, ou un écart des tirs cadrés football-data − API qui dépasse ±0,1 par équipe et par match dans un championnat autre que la Bundesliga (où il est déjà de +0,10 sans effet mesurable) ; on recalibrerait alors dans `inference/`, par championnat, dans une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
