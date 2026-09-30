# ADR-0036 — Cotes plus/moins 2,5 de football-data : une référence de marché, jamais une variable

- **Statut** : acceptée
- **Date** : 2026-09-30
- **Référence** : ADR-0027 (cotes reportées, chargeur prévu en partie 4 ; révisée en partie ici) ; ADR-0009 (Brier de P(T > 2,5) comparable au marché) ; ADR-0010 (horizon H1) ; ADR-0012, ADR-0028 (scellé) ; rapport de cadrage, I.3 (ligne « référence de marché »), I.6, I.8, décision M18 ; décision 9 de la partie 4

## Contexte

Le protocole compare les modèles à trois références : B0, B1 et le **marché** (rapport I.4, M0). Le marché ne donne pas de loi complète du total, seulement P(T > 2,5), implicite dans les cotes plus/moins 2,5 buts des CSV de football-data, déjà stockés (ADR-0024) mais non chargés (ADR-0027).

Deux risques :

- **Fuite par la clôture.** La cote de clôture intègre l'information du jour du match (compositions, météo, mouvements de dernière minute) : elle n'est pas disponible à l'horizon H1 (rapport I.8).
- **Noms de colonnes changeants.** Lecture des en-têtes réels des 270 fichiers (10 divisions, 2000-01 à 2026-27), le 2026-09-30 :

| Colonnes (> 2,5 et < 2,5) | Saisons | Nature |
|---|---|---|
| `Avg`, `AvgC` | 2019-20 et après | moyenne de marché (nombre de cotes non publié) |
| `BbAv` (+ `BbOU`) | 2005-06 à 2018-19 | agrégat historique BetBrain, `BbOU` bookmakers ; pas de clôture |
| `B365`, `B365C` | 2002-03 à 2004-05, puis 2019-20 et après (clôture : 2019-20 et après) | un bookmaker |
| `P`, `PC` | 2019-20 à 2025-26 | un bookmaker (Pinnacle) |
| `BFE`, `BFEC` | 2024-25 et après | bourse Betfair |
| `GB` | 2002-03 à 2004-05 | un bookmaker |
| `Max`, `MaxC`, `BbMx` | selon les saisons | meilleure cote du marché |
| aucune | 2000-01 et 2001-02 | — |

## Options envisagées

1. **Cotes comme variable** du modèle : meilleur log-loss, mais le modèle recopierait le marché ; sans intérêt pédagogique (décision M18).
2. **Cotes comme référence seulement**, en deux versions : « avant clôture » pour l'horizon H1, « clôture » comme borne haute.
3. Ne pas charger les cotes : pas de point de comparaison extérieur.

Pour le choix de la colonne : un seul bookmaker partout (continuité, mais Bet365 manque de 2005-06 à 2018-19), ou une **priorité** moyenne de marché, puis agrégat, puis un bookmaker.

## Décision

Option 2, avec la priorité.

- **Table** : migration **0007, additive**, `staging.match_odds` : match, source (`football_data`), version (`avant_cloture` ou `cloture`), cotes décimales plus et moins 2,5, colonne retenue, nombre de cotes agrégées (vide quand il n'est pas publié). Contraintes : une ligne par (match, source, version), cotes > 1.
- **Chargeur** : `load_external` écrit les cotes de chaque ligne de football-data appariée à un match API ou créée hors API, à côté des tirs ; le choix de la colonne est une fonction pure (`ingestion/football_data_odds.py`, testée).
- **Priorité, pour chaque version et chaque ligne** : la première colonne dont les deux cotes sont lisibles et > 1. Avant clôture : `Avg`, `BbAv`, `B365`, `P`, `BFE`, `GB`. Clôture : `AvgC`, `B365C`, `PC`, `BFEC`. Les maximums (`Max`, `BbMx`) ne sont jamais retenus : un maximum n'estime pas une probabilité. **Aucune cote n'est inventée** : sans colonne lisible, aucune ligne.
- **Probabilité implicite** : P(T > 2,5) = q₊ / (q₊ + q₋), avec q = 1 / cote : la marge est retirée par **normalisation proportionnelle** (décision 9).
- **Rôles** :
  - « avant clôture » : **référence de l'horizon H1**, évaluée sur le seul événement plus/moins 2,5 (Brier et log-loss binaire), jamais sur la loi complète ;
  - « clôture » : **borne haute** seulement, jamais une variable ni une référence de l'horizon H1 ;
  - aucune cote n'entre dans le jeu de données ni dans un modèle.
- **Scellé** : les cotes des matchs scellés sont chargées (permis) ; leur lecture passe par la porte `features/sources.py`, filtrée comme les autres valeurs de match ; les rapports n'en donnent que des décomptes de présence.
- `load` vise la révision 0007 (`ALEMBIC_HEAD`) ; `check-referentiel` gagne une section 7 (présence des cotes par championnat du top 5 et par saison).

## Conséquences

- **Chargement du 2026-09-30** (`ops.load_run` n° 5, 778 s) : 120 983 lignes de cotes ; les 14 autres tables ont les mêmes empreintes que le chargement n° 4. Couverture, matchs de championnat du top 5 terminés (`reports/data_quality/referentiel_2026-09-30.md`, section 7) :
  - 2015-16 à 2024-25 : 18 034 matchs, **99,86 %** avec une cote « avant clôture » (`BbAv` jusqu'en 2018-19, `Avg` ensuite), 59,37 % avec une clôture (depuis 2019-20 seulement) ;
  - plis de validation (2021-22 à 2024-25) : 7 171 matchs, **99,78 %** avant clôture et 99,79 % en clôture, toujours la moyenne de marché ;
  - 2000-01 et 2001-02 : aucune cote ; 2002-03 à 2004-05 : un bookmaker (96 à 100 %) ;
  - après le scellé : présence seulement (100 % en Premier League, 99,35 % en Ligue 1 en 2025-26, par exemple).
- `load` dure désormais **environ 13 minutes** (778 s, contre 352 à 444 s) : la règle « pas de traitement de plus de 10 minutes » des matinées de collecte le concerne d'autant plus.
- La « moyenne de marché » change de nature en 2019-20 (BetBrain, puis la moyenne de football-data) : sur les plis de validation (2021-22 à 2024-25), seule `Avg` sert, ce qui suffit à la référence ; la rupture est écrite, pas corrigée.
- Pas de clôture avant 2019-20 : la borne haute n'existe que sur les plis de validation.
- **Critère de révision** : une couverture « avant clôture » inférieure à 95 % des matchs d'un pli, ou une source de cotes d'ouverture datée ; dans ce cas, revoir la priorité dans une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
