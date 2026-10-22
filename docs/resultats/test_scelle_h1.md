# Test scellé du MVP, horizon H1 (jalon J6)

*Sous-étape 4.16. Liste figée : `experiments/scelle_h1.yaml`, tag `pre-scelle-h1` (ADR-0039). Règle : un seul lancement, résultat publié tel quel (ADR-0012, règle 5). Journal des usages du scellé : `reports/sealed_tests.md`.*

## Premier lancement : échec technique, aucun résultat (2026-10-22)

| Étape | Date (UTC) | Commit | Issue |
|---|---|---|---|
| `features build --sealed-test --experiment experiments/scelle_h1.yaml` | 2026-10-22 08:02 | `9724829` | jeu `ds-2026-10-22-94969da0` : 205 216 lignes, dont 9 118 scellées (2025-26 et 2026-27 jusqu'au 2026-10-18) |
| `evaluate experiments/scelle_h1.yaml --sealed-test --dataset ds-2026-10-22-94969da0` | 2026-10-22 08:03 | `70f9766` | **échec** au bout de 8 s : `TypeError: <class 'datetime.date'>` à l'écriture du rapport |

- **Cause** (E-059) : la clé descriptive `test_from: 2025-07-01` du fichier d'expérience est lue comme une date par YAML. Le rapport recopie le fichier, et son encodeur JSON n'accepte pas les dates.
- **Ce qui existe** : un fichier de prédictions par match, écrit avant le plantage, **jamais ouvert** (`data/experiments/scelle-h1-20261022T080319/predictions.parquet`, hors Git ; sha256 `14b103d3…cdd560e44`, relevé avant toute décision), et les lignes de lecture du journal.
- **Ce qui n'existe pas** : aucun rapport, aucune métrique, aucun chiffre affiché. Personne n'a vu de résultat du test scellé. L'index des expériences compte toujours 9 essais : cet essai en échec n'a pas pu y être inscrit, faute de rapport.
- **Suite** : non relancé (consigne : erreur technique, on écrit et on s'arrête). La suite dépend d'une décision de l'utilisateur, consignée dans une nouvelle ADR.
