# ADR-0005 — Fin de l'abonnement API-FOOTBALL et calendrier de gel

- **Statut** : acceptée (renouvellement automatique à vérifier)
- **Date** : 2026-09-27
- **Référence** : rapport de cadrage, C.6, G.4, G.11, décisions M5 et M28

## Contexte

Abonnement Pro (7 500 requêtes par jour) souscrit le 2026-09-22. Le quota journalier se réinitialise à 00:00 UTC.

## Valeurs relevées

| Élément | Valeur |
|---|---|
| Date de fin (tableau de bord) | **2026-10-22 07:56:53 UTC** (09:56 heure de Paris) |
| Dernier jour de quota complet | 2026-10-21 (UTC) |
| Renouvellement automatique | à vérifier |

## Décision

Calendrier, en gardant 3 jours de marge avant la fin :

| Date | Étape |
|---|---|
| 28 sept. → 1er oct. | Collecteur v2 (ADR-0004) relu et fusionné ; inventaire de couverture |
| 2 → 8 oct. | Palier P1, contrôles de qualité |
| 9 → 16 oct. | Paliers P2, P3, P4 ; journal quotidien |
| **17 → 18 oct.** | **Fin de la collecte** ; rattrapages ; contrôles de qualité finaux |
| **19 oct.** | **Gel** : `DATA_FREEZE.md`, export unique sur le disque externe, **test de restauration**, tag `data-freeze-2026-10` |
| 20 → 21 oct. | Marge : recollecte de ce qui manquerait après le test de restauration |
| 22 oct. 09:56 | Fin de l'abonnement |

- Couper le renouvellement automatique s'il est actif, sauf choix contraire explicite.
- La question d'un réabonnement ponctuel (par exemple un mois en juin) est reportée au printemps 2027 (décision M28).

## Conséquences

- Toute action qui consomme du quota après le 19 octobre est un rattrapage, pas une nouvelle collecte.
