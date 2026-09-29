# ADR-0031 — Elo maison (G1) : une échelle par pays, mise à jour par jour, paramètres réglés sur 2005-06 à 2014-15 puis figés

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : rapport de cadrage, I.3 (G1), I.5, M17 (Elo maison) ; ADR-0009 (exclusions), ADR-0010 (règle temporelle), ADR-0012 (période de développement, amorçage) ; décisions d.2, d.10b et d.10g de la partie 3 ; `reports/variables/elo_reglage.md`

## Contexte

Le groupe G1 du MVP est une note de force globale par équipe, disponible avant le match et en live (résultats de football-data). ClubElo est derrière une authentification (rapport, M17) : l'Elo est calculé ici. Données : top 5 et D2, de 2000-01 à aujourd'hui, D1 et D2 d'un même pays étant liées par la montée et la descente ; aucun match entre pays dans les championnats.

## Options envisagées

1. **Une échelle commune à tous les pays** : impossible à ancrer sans les coupes d'Europe, absentes avant 2015-16.
2. **Une échelle par championnat** : une équipe promue changerait d'échelle et perdrait son histoire.
3. **Une échelle par pays (D1 et D2)**, sans lien entre pays : le produit évalue des matchs de championnat, qui opposent toujours deux équipes d'un même pays.

## Décision

Option 3, avec les règles suivantes (`src/foot_predictor/features/elo.py`).

- **Espérance** : E = 1 / (1 + 10^(−(R_dom + H − R_ext)/400)), avec H l'avantage du terrain en points.
- **Mise à jour**, à somme nulle : ΔR_dom = K · G · (S − E), avec S = 1, 0,5 ou 0. G est le multiplicateur d'écart de buts de l'Elo des sélections (1 si N ≤ 1, 1,5 si N = 2, (11 + N)/8 si N ≥ 3), ou 1 sans multiplicateur.
- **Par jour** : la note d'un match du jour J ne dépend que des matchs terminés avant J ; les variations d'un jour s'appliquent ensemble à la fin du jour, donc deux matchs du même jour ne s'influencent pas (ADR-0010).
- **Matchs qui alimentent l'Elo** : terminés, non exclus (ADR-0009), avec un score au temps réglementaire, dans les 10 championnats, barrages compris. Les autres matchs (à venir, exclus) reçoivent leurs notes d'avant-match sans les modifier.
- **Intersaison** : au premier match d'une nouvelle saison, une équipe présente dans l'échelle la saison précédente revient vers la moyenne de fin de saison précédente de **sa division de la nouvelle saison** : R ← m + (1 − r)(R − m). C'est la décision d.10b, plutôt que la moyenne du pays, qui réduirait chaque été l'écart entre D1 et D2.
  - Le niveau d'une saison se lit sur la saison régulière : un barrage de D1 joué par une équipe de D2 ne la range pas en D1.
  - Les cibles sont figées au premier match de la saison dans l'échelle, à partir des seules notes de fin de saison précédente : elles ne dépendent d'aucun match futur, donc le jeu est invariant à la date de coupe.
- **Équipe sans match dans l'échelle la saison précédente** (promue de D3, ou revenue après une absence) : note d'entrée = moyenne des 3 plus basses notes de fin de saison de sa division. La toute première saison (2000-01) : 1500 en D1, 1500 − Δ en D2.
- **Réglage** : grille fixée avant le calcul (K, H, r, multiplicateur, Δ : 576 combinaisons), évaluée sur **2005-06 à 2014-15 seulement**, avec 2000-01 à 2004-05 en amorçage. Critère : log-loss du 1N2 d'une logistique ordonnée sur l'écart d'Elo, sur les matchs de saison régulière du top 5. La meilleure combinaison est **figée** dans `features/params/elo.json`.
- **Interprétation de l'ADR-0012** : l'ADR-0012 dit que les saisons d'avant 2015-16 « servent seulement à amorcer l'Elo et les fenêtres glissantes ». Régler les paramètres de l'Elo sur 2005-06 à 2014-15 fait partie de cet amorçage : ces saisons précèdent le début de l'apprentissage (2015-16), et le réglage ne lit aucune saison postérieure à 2014-15, donc aucun pli de validation (2021-22 à 2024-25) ni aucun match scellé.

## Conséquences

- **Paramètres retenus** (réglage du 2026-09-29, 217 s, 18 259 matchs) : K = 15, H = 40, r = 0, multiplicateur d'écart de buts, Δ = 100. Log-loss du 1N2 : **0,9936**, contre 1,0622 pour la référence sans note (fréquences de 1, N, 2). Le relief est plat : l'écart entre la meilleure et la pire des 576 combinaisons n'est que de 0,0097, et de 0,0001 entre voisines pour H et r. H et r tombent au bord de la grille (40 points ; aucun retour à la moyenne) ; la grille n'est pas étendue après coup, pour ne pas multiplier les essais.
- Variables du registre : `elo_pre`, `opp_elo_pre`, `elo_diff` (sans l'avantage du terrain, porté par `is_home`), `elo_matches`, `opp_elo_matches`.
- Réglage reproductible : `python -m foot_predictor.features.elo_tuning` réécrit `elo.json` et `reports/variables/elo_reglage.md`. Le relancer après le gel ne change rien : les saisons lues sont antérieures au scellé.
- **Limites** :
  - quelques matchs de D2 absents de l'API ne sont pas appariés (Ligue 2 2010-11 : 10 matchs ; 2. Bundesliga 2012-13 : 4), donc manquent à l'Elo ; l'effet est négligeable, et antérieur à l'apprentissage ;
  - une équipe reléguée en D3 disparaît de l'échelle ; à son retour, elle repart de la note d'entrée ;
  - les matchs hors API n'ont qu'une date (sans heure), ce qui suffit pour une mise à jour par jour.
- **Critère de révision** : un Elo réglé qui ne bat pas nettement la référence sans note (fréquences de 1, N, 2) sur la fenêtre de réglage, ou une ablation G1 sans gain en partie 4. Dans ce cas, revoir la forme (Elo de type Glicko, ou forces de Dixon-Coles) dans une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
