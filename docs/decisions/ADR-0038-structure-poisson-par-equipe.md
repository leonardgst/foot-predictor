# ADR-0038 — Structure du modèle MVP : Poisson par équipe (M3), sans binomiale négative, sans Dixon-Coles, sans régularisation

- **Statut** : acceptée
- **Date** : 2026-09-30
- **Référence** : ADR-0009 (cible, M1 et M2 pédagogiques), ADR-0037 (protocole et règle de décision, tag `protocole-v1`) ; rapport de cadrage, I.2, I.4 ; décision 5 de la partie 4 ; `docs/resultats/modeles.md`

## Contexte

Le lot 2 de la partie 4 compare les structures M1 à M6 sur les 4 plis (7 156 matchs du top 5), avec les variables G0 + G1 (décision 5), par la règle de l'ADR-0037. Rapports : `reports/experiments/m1-m2-20260930T083847.json`, `m3-20260930T084658.json`, `m5-20260930T085337.json`, `m6-20260930T090747.json`. Nombre d'essais à cette date : 7 (dont 2 mesures de durée), 0 échec.

| Étape | Comparaison (A − B, log-loss du total) | Écart | IC 95 % | Règle |
|---|---|---|---|---|
| Linéaire | B1 − M1 | −0,0108 | [−0,0166 ; −0,0049] | M1 perd (pédagogique) |
| Comptage | B1 − M2 | +0,0054 | [+0,0018 ; +0,0090] | M2 bat B1 (pédagogique) |
| Par équipe | M2 − M3 | +0,0033 | [+0,0014 ; +0,0052] | **M3 remplace M2** |
| Dispersion | M3 → M4 | — | — | NB non justifiée : φ ≈ 0,98, α_NB au bord, LR = 0 |
| Dépendance | M3 − M5 | +0,00002 | [−0,0009 ; +0,0010] | M5 ne remplace pas M3 |
| Régularisation | M3 (G0 à G3) − M6 ridge | +0,0002 | [−0,0004 ; +0,0008] | M6 ne remplace pas M3 |
| Régularisation | M3 (G0 à G3) − M6 élastique net | +0,0001 | [−0,0001 ; +0,0004] | idem |

## Options envisagées

1. **M3**, Poisson par équipe, indépendance conditionnelle des deux équipes, maximum de vraisemblance sans pénalité.
2. **M5**, M3 + Dixon-Coles : change P(T = 0) et P(T = 1), sans gain global.
3. **M6**, Poisson régularisé : aucun gain à variables égales.
4. **M4**, binomiale négative : non justifiée (légère sous-dispersion).

## Décision

Option 1. La **structure du modèle MVP est M3** : Y_{m,e} ~ Poisson(λ_{m,e}), log λ = xᵀβ par maximum de vraisemblance, une ligne par (match, équipe), total Poisson(λ_dom + λ_ext). À gain non significatif, la règle garde le plus simple (ADR-0037).

## Conséquences

- Le lot 3 (4.12) fait les **ablations** sur M3 : G0, puis G1, puis G2 (demi-vie choisie dans le pli parmi 60, 120 et 240 jours), puis G3, puis la population d'apprentissage. Le lot 2 montre déjà que G2 + G3 ensemble apportent +0,0091 [+0,0056 ; +0,0126] à M3.
- M5 et M6 restent dans le code (pédagogie, version intermédiaire) ; M4 n'est pas évalué.
- Limites assumées : légère sous-dispersion des buts par équipe (φ ≈ 0,98) non modélisée ; dépendance entre équipes ignorée (ρ ≈ −0,06, sans effet sur le log-loss du total).
- **Critère de révision** : en version intermédiaire, de nouvelles variables (H2) qui rendraient la régularisation utile (nombre de coefficients bien plus grand), ou une dispersion qui s'écarterait nettement de 1 ; dans ce cas, refaire les comparaisons M4 et M6 dans une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
