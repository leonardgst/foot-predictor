# Contrôle des lignes d'inférence sur la période scellée, contre le jeu ds-2026-10-22-94969da0 — 2026-10-22

Sous-étape 5.13 (ADR-0045) : table des matchs ouverte à l'inférence, jeu scellé du test H1 et du modèle final (lecture journalisée dans `reports/sealed_tests.md`). Ce rapport ne donne que des dates, des décomptes et des noms de colonnes : aucune valeur d'un match scellé.

Produit par `python -m foot_predictor.inference check` (ADR-0040, décision 2). Lignes d'inférence d'un jour (historique tronqué au jour J, cibles à 0-0 sans statistiques) contre lignes du jeu d'entraînement pour les mêmes matchs ; toutes colonnes sauf `goals_for`, `goals_against`, `shots_source`.

**Verdict : identiques au bit près** sur 8 jours et 434 lignes.

| Jour | Raison du choix | Lignes | Identiques | Colonnes en écart | Durée (s) |
|---|---|---|---|---|---|
| 2025-08-15 | première journée 2025-26 (promus sans historique de D1) | 22 | oui | aucune | 5.8 |
| 2026-01-13 | milieu de la période 2025-26 | 6 | oui | aucune | 5.8 |
| 2026-05-24 | dernier jour présent 2025-26 | 58 | oui | aucune | 6.3 |
| 2026-05-17 | jour le plus chargé 2025-26 | 90 | oui | aucune | 6.0 |
| 2026-08-15 | première journée 2026-27 (promus sans historique de D1) | 36 | oui | aucune | 6.2 |
| 2026-09-06 | milieu de la période 2026-27 | 58 | oui | aucune | 6.3 |
| 2026-10-18 | dernier jour présent 2026-27 | 60 | oui | aucune | 6.2 |
| 2026-09-12 | jour le plus chargé 2026-27 | 104 | oui | aucune | 6.1 |
