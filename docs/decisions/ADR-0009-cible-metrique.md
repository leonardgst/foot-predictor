# ADR-0009 — Cible : buts par équipe, sortie : loi du total, métrique principale : log-loss du total

- **Statut** : acceptée
- **Date** : 2026-09-28
- **Référence** : rapport de cadrage, B.4 (M1, M2), C.2, E.1, I.1, I.2, I.6, I.7, décision M8 ; `docs/realisation/05_controle_qualite/constats_P1_P2.md`

## Contexte

Le projet doit prédire **la distribution du nombre de buts** d'un match. Or `modeling/evaluation.py` ne mesure aujourd'hui que le score exact et le 1N2 : log-loss du score exact de 2,933 et Brier 1N2 de 0,59 sur 2024-25 (`docs/RESULTATS_MODELE.md`). Rien ne porte sur le total.

Faits à prendre en compte :

- **Plafond de prédictibilité.** Le total est très bruité. Même un modèle parfait expliquerait environ 10 à 15 % de sa variance (rapport, C.2). Une valeur ponctuelle seule serait trompeuse ; seules des métriques probabilistes mesurent correctement de petits gains.
- **Structure multiplicative.** L'attaque d'une équipe rencontre la défense de l'autre de façon multiplicative. Modéliser le total directement est mal spécifié, et perd l'information « qui marque ».
- **Coupes collectées.** Les coupes sont désormais dans le brut (ADR-0002). Il faut donc préciser le temps de jeu de la cible (prolongations, tirs au but).
- **Écarts entre sources.** 162 + 33 matchs ont un nombre de buts dans les événements différent du score (constats P1 et P2).
- **Totaux discrets.** Un intervalle construit sur les quantiles 10 % et 90 % ne couvre pas 80 % des cas, même pour un modèle parfait. Calcul pour une loi de Poisson :

| λ (buts attendus) | Intervalle [q10 ; q90] | Couverture réelle |
|---|---|---|
| 2,2 | 0 à 4 | 92,8 % |
| 2,8 | 1 à 5 | 87,4 % |
| 3,4 | 1 à 6 | 90,9 % |

Le critère de réussite E.1(4) du rapport, « couverture de l'intervalle à 80 % entre 77 et 83 % », est donc mal posé.

## Options envisagées

1. **Total T modélisé directement.** Simple, mal spécifié, perte d'information.
2. **Buts de chaque équipe (λ domicile, λ extérieur), puis loi du total.** Structure du modèle A existant ; 1N2 et score exact dérivables sans calcul supplémentaire.
3. **Valeur ponctuelle seule** (E[T]). Trompeuse, vu le bruit.

Pour la métrique principale : log-loss du total (vraisemblance, strictement propre), RPS (ordinal), ou MAE et RMSE (moyenne seulement).

## Décision

Option 2, avec une sortie en distribution et le **log-loss du total** comme métrique principale.

- **Cible.** Buts marqués par chaque équipe **à la fin du temps réglementaire**, prolongations et tirs au but exclus. Le score officiel fait foi, pas les événements. Les matchs sur tapis vert, annulés ou abandonnés sont exclus.
- **Unités.** Apprentissage : une ligne par (match, équipe). Évaluation : le **match**.
- **Sortie.** P(T = k) pour k de 0 à 9 et « 10 et plus » ; E[T] ; P(T > 2,5) ; un intervalle de prédiction avec sa couverture annoncée ; λ domicile et λ extérieur.
- **Métriques** :

| Rôle | Métrique |
|---|---|
| **Principale** (règle de décision, rapport I.7) | Log-loss du total : moyenne de −log P̂(T = t observé) |
| Secondaires | RPS du total (catégories 0 à 7 et plus) ; Brier de P(T > 2,5) (comparable aux cotes de football-data) |
| Diagnostics | Calibration de P(T > 2,5) par décile ; PIT randomisé ; couverture observée contre couverture annoncée ; log-loss du score exact et Brier 1N2 (continuité avec les résultats antérieurs) ; log-loss par équipe |
| Descriptives, jamais pour sélectionner | MAE et RMSE de E[T] |

- **Critère E.1(4) remplacé.** Pour chaque match, l'intervalle est accompagné de sa couverture annoncée P̂(T ∈ intervalle). Sur l'ensemble d'évaluation, la couverture observée doit être à **±3 points de la moyenne des couvertures annoncées**.
- **Étapes pédagogiques.** La régression linéaire sur T (M1) et le Poisson sur T (M2) restent des étapes du parcours, **pas des candidats** au choix du modèle final.
- **Population d'évaluation** (top 5 seul ou avec les D2) : tranchée par la décision M11.

## Conséquences

- `modeling/evaluation.py` est complété : loi du total calculée à partir de la loi jointe (convolution, ou somme de la matrice des scores), log-loss et RPS du total, Brier plus ou moins 2,5 buts, PIT, couverture annoncée contre observée. Les métriques existantes restent, comme diagnostics.
- Le chargement vers `staging` doit conserver le score au temps réglementaire (`score.fulltime` de l'API) distinct du score final, et marquer les matchs à exclure.
- Le document mathématique (LaTeX) présente la loi du total, les règles de score et la couverture des intervalles discrets.
- La page de détail de l'application affiche la couverture annoncée de l'intervalle, pas un « 80 % » nominal.
- **Critère de révision** : si un modèle nettement meilleur en log-loss du total est moins bon en RPS et en calibration sur plusieurs plis, revoir le choix de la métrique principale plutôt que retenir ce modèle.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
