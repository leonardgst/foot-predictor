# ADR-0002 — Périmètre de collecte API-FOOTBALL pendant l'abonnement

- **Statut** : acceptée
- **Date** : 2026-09-27
- **Référence** : rapport de cadrage, G.1, G.3, G.4, décision M2

## Contexte

L'abonnement Pro (7 500 requêtes par jour) prend fin mi ou fin octobre 2026. Après cette date, l'offre gratuite ne donne accès qu'aux saisons 2022 à 2024 : la saison en cours, les compositions récentes, les profils joueurs et les entraîneurs ne pourront plus être récupérés gratuitement.

Avec `/fixtures?ids=` (20 matchs par appel), le coût par match est divisé par 20. Le quota restant (de l'ordre de 100 000 requêtes) dépasse largement le besoin du périmètre minimal.

## Options envisagées

1. Top 5, 2015-2024 (périmètre actuel du code).
2. Top 5, 2015 → saison en cours.
3. Option 2 + deuxièmes divisions, coupes, joueurs, entraîneurs, transferts, blessures.
4. **Maximum utile** : option 3 + saisons plus anciennes (là où la couverture API existe) + autres championnats, collectés **par paliers de priorité**.

## Décision

Option 4 : récupérer le maximum de données utiles tant que l'abonnement est actif, **dans cet ordre strict**. Un palier ne commence que lorsque le précédent est collecté et contrôlé (rapport G.9). La sauvegarde est unique, au gel des données (ADR-0006).

| Palier | Contenu | Requêtes estimées |
|---|---|---|
| **P1 — indispensable** | Top 5, 2015-16 → 2026-27 (dont 2025-26 et la saison en cours) ; D2 des 5 pays ; coupes d'Europe et coupes nationales (matchs des équipes suivies) ; profils joueurs, entraîneurs, transferts, blessures, équipes | ~15 000 |
| **P2 — historique ancien** | Top 5 et D2 avant 2015, **uniquement pour les saisons où `/leagues` déclare `coverage.fixtures.lineups = true`** | ~3 000 |
| **P3 — autres championnats** | Championnats « fournisseurs » de joueurs (Pays-Bas, Portugal, Belgique, Écosse, Turquie, Autriche, Suisse, Danemark, Brésil, Argentine, États-Unis…), 2015 → aujourd'hui, avec profils joueurs | ~10 000 à 15 000 |
| **P4 — compléments** | Historique des indisponibilités (`/sidelined`), classements officiels, journal quotidien des matchs à venir (compositions à T-60, cotes, prédictions de l'API) | selon le reste |

Une réserve de 500 requêtes par jour est conservée pour le journal quotidien et les rattrapages.

## Conséquences

- Le collecteur v2 (ADR-0004) est un prérequis : sans lots de 20, sans reprise et sans lecture du champ `errors`, un périmètre de cette taille serait lent et risqué.
- L'inventaire de couverture (`/leagues`) est fait **avant** P2 et P3 : on ne collecte pas une saison qui n'a pas de compositions.
- Volume disque estimé : de l'ordre de 1 à 2 Go compressés pour P1 à P3, à mesurer.
- **Plus de données ne règle pas à lui seul le problème de la remise à zéro de la stabilité** (rapport H.4) : c'est le choix d'une décroissance sans remise à zéro qui le règle. L'historique ancien sert à « amorcer » cette décroissance dès 2015-16 et à comparer rigoureusement les variantes.
- Utilité des autres championnats, à vérifier par expérience : historique des joueurs recrutés (moins de « joueurs inconnus »), et test de l'hypothèse « entraîner sur 15 championnats améliore les prédictions du top 5 ».
- Les données restent privées : pas de publication, pas de commit dans le dépôt.
