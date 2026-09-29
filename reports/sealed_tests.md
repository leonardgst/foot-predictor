# Journal des tests scellés (ADR-0012)

Chaque usage de l'option `sealed_test=True` (ou `--sealed-test`) ajoute une ligne à ce fichier,
automatiquement, par `foot_predictor.seal.check_seal`. Le test scellé se lance **une fois par
version** (MVP, puis version intermédiaire) ; le résultat est publié tel quel, même décevant.
Un usage absent de ce journal est une levée du scellé à constater dans une nouvelle ADR.

| Date (UTC) | Commit | Fichier d'expérience | Résultat |
|---|---|---|---|
