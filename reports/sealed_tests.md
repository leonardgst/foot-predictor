# Journal des tests scellés (ADR-0012)

Chaque usage de l'option `sealed_test=True` (ou `--sealed-test`) ajoute une ligne à ce fichier,
automatiquement, par `foot_predictor.seal.check_seal`. Le test scellé se lance **une fois par
version** (MVP, puis version intermédiaire) ; le résultat est publié tel quel, même décevant.
Un usage absent de ce journal est une levée du scellé à constater dans une nouvelle ADR.

| Date (UTC) | Commit | Fichier d'expérience | Résultat |
|---|---|---|---|
| 2026-10-22 08:02 | 97248299f605 | experiments/scelle_h1.yaml | accès autorisé, résultat à compléter (17381 match(s) scellé(s) lus) |
| 2026-10-22 08:03 | 70f976631fbf | experiments/scelle_h1.yaml | accès autorisé, résultat à compléter (9118 match(s) scellé(s) lus) |
| 2026-10-22 08:03 | 70f976631fbf | experiments/scelle_h1.yaml | accès autorisé, résultat à compléter (8694 match(s) scellé(s) lus) |
