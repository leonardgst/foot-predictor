# ADR-0039 — Modèle MVP, horizon H1 : Poisson par équipe sur G0 + G1 + G2, appris sur le top 5 ; liste du test scellé

- **Statut** : acceptée
- **Date** : 2026-09-30
- **Référence** : ADR-0009, ADR-0010, ADR-0011 (règle 4, live), ADR-0012 (règle 5, test scellé), ADR-0037 (règle de décision), ADR-0038 (structure) ; `docs/resultats/references.md`, `modeles.md`, `ablations.md` ; `experiments/scelle_h1.yaml`

## Contexte

La règle de l'ADR-0037 s'applique sans exception, dans l'ordre fixé : structures (G0 + G1), puis groupes de variables par ajout cumulatif, puis population d'apprentissage. Tous les chiffres : 4 plis (2021-22 à 2024-25), 7 156 matchs du top 5, écarts de log-loss du total A − B avec intervalle à 95 % par bootstrap par blocs. Essais à cette date : **9**, 0 échec (`reports/experiments/INDEX.md`).

| Décision | Comparaison | Écart [IC 95 %] | Plis | Verdict de la règle |
|---|---|---|---|---|
| Structure | M2 − M3 (par équipe) | +0,0033 [+0,0014 ; +0,0052] | 4/4 | M3 remplace M2 |
| Dispersion | M3 → M4 (NB2) | φ ≈ 0,98, LR = 0 | — | NB non justifiée |
| Dépendance | M3 − M5 (Dixon-Coles) | +0,00002 [−0,0009 ; +0,0010] | 2/4 | M3 conservé |
| Régularisation | M3 (G0 à G3) − M6 ridge | +0,0002 [−0,0004 ; +0,0008] | 3/4 | M3 conservé |
| G1 | G0 − (G0 + G1) | +0,0094 [+0,0060 ; +0,0128] | 4/4 | G1 retenu |
| G2 | (G0 + G1) − (G0 à G2) | +0,0092 [+0,0057 ; +0,0127] | 4/4 | G2 retenu |
| G3 | (G0 à G2) − (G0 à G3) | −0,0001 [−0,0004 ; +0,0002] | 2/4 | G3 non retenu |
| Population | top 5 − (top 5 et D2) | +0,0003 [−0,0003 ; +0,0010] | 3/4 | top 5 retenu |

Objectif du MVP (ADR-0037) : le modèle retenu bat **B1 de +0,0179 [+0,0133 ; +0,0226]** (4 plis sur 4) ; pente de calibration poolée 0,95 ; **couverture** de [q10 ; q90] à ±1,1 point au plus de la couverture annoncée, par pli (critère : ±3 points, rempli) ; **calibration de P(T > 2,5) par décile** (diagnostic, non bloquant) : écart moyen de 1,7 point, 9 déciles sur 10 à moins de 3 points, un décile à 3,8 points, publié tel quel.

## Options envisagées

1. **M3 sur G0 + G1 + G2, top 5** (verdict de la règle).
2. M3 sur G0 à G3 : sans gain, et G3 indisponible en live (ADR-0011).
3. Un modèle plus complexe (M5, M6) : sans gain significatif, écarté par la règle.

## Décision

Option 1.

- **Modèle MVP H1** : Poisson par équipe (M3, ADR-0038), variables G0 (domicile, championnat, huis clos et son interaction avec le domicile), G1 (Elo de l'équipe et de l'adversaire), G2 (logarithmes des moyennes glissantes de buts et d'`xg_proxy`, pour et contre, des deux équipes), standardisées dans l'apprentissage ; demi-vie choisie par validation interne parmi 60, 120 et 240 jours (240 dans 3 plis sur 4) ; appris sur le top 5.
- **Variante live** : aucune. G3 n'est pas retenu : le même modèle sert en rejeu et en live (ADR-0011, règle 4). En live, G2 lira les tirs de football-data seulement (ADR-0035 : écart d'`xg_proxy` de +0,02 en moyenne, à contrôler en partie 5).
- **Liste du test scellé** (`experiments/scelle_h1.yaml`) : le modèle retenu, B0, B1, le marché avant clôture et, en borne haute, le marché à la clôture. Procédure : apprentissage sur 2015-16 à 2024-25 (matchs antérieurs au 1er juillet 2025), hyperparamètres par validation interne sur 2024-25, puis réajustement ; évaluation **une seule fois** sur les matchs de championnat du top 5 joués à partir du 1er juillet 2025, jusqu'au gel.
- **Tag `pre-scelle-h1`** : posé après la sous-étape 4.14, pour figer **aussi** le code du test scellé et de l'entraînement final (`build --sealed-test`, `evaluate --sealed-test`, `train --final`). Ensuite, plus aucun changement sous `src/foot_predictor/modeling/`, `src/foot_predictor/features/`, `experiments/` avant le test ; la phase B le vérifie par `git diff pre-scelle-h1..HEAD`.

## Conséquences

- Phase B (4.16) : un seul lancement, résultat publié tel quel dans `docs/resultats/test_scelle_h1.md` et journalisé dans `reports/sealed_tests.md` ; aucun modèle modifié ensuite (ADR-0012).
- Phase B (4.17) : réentraînement du modèle retenu sur toutes les données disponibles, carte d'identité, tag `v0.5.0`.
- **Critère de révision** : un test scellé où le modèle retenu ne bat pas B1 (intervalle qui contient 0 ou négatif) est publié tel quel ; la version intermédiaire (H2) repart de ce constat dans une nouvelle ADR, sans retoucher le modèle H1.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
