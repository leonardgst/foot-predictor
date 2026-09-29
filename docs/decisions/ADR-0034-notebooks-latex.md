# ADR-0034 — Notebooks d'exploration sans sorties ; chapitres LaTeX versionnés, compilés sur Overleaf

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : rapport de cadrage, E.1 (critère 6), K, L (J4), décision M26 ; ADR-0012 (scellé), ADR-0028 (porte unique) ; décisions d.7 et d.8 de la partie 3

## Contexte

Le jalon J4 demande une exploration statistique en notebooks et un premier chapitre LaTeX (« données et variables »). Deux risques : un notebook versionné **avec ses sorties** porte des chiffres et des graphiques dans l'historique Git (volume, et risque de montrer des matchs scellés si la porte était contournée) ; un chapitre mathématique qui diverge du code. Pour le LaTeX, la décision M26 hésitait entre Overleaf (téléversement manuel) et une compilation locale (Tectonic ou TeX Live).

## Options envisagées

- Notebooks :
  1. `.ipynb` avec sorties ;
  2. **`.ipynb` sans sorties** (hook `nbstripout`), réexécutables, avec leurs seules dépendances dans un groupe optionnel ;
  3. scripts `.py` au format « percent ».
- LaTeX :
  1. TeX Live local, lourd (plusieurs Go) ;
  2. Tectonic, un exécutable, installable sans droits d'administrateur, mais téléchargé depuis Internet ;
  3. **sources versionnées, compilées sur Overleaf** par téléversement.

## Décision

Notebooks : option 2. LaTeX : option 3.

- **Notebooks** dans `notebooks/`, versionnés **sans sorties** (hook pre-commit `nbstripout`, version 0.9.1).
  - Ils n'accèdent aux données **que par la porte** `foot_predictor.features.sources` ; un test d'architecture refuse tout autre import du projet, `sqlalchemy`, `psycopg` et le texte `staging.`.
  - Chacun pose une question, montre des graphiques et se termine par une **conclusion écrite en français** ; aucune variable ni aucun paramètre n'est choisi à partir d'eux.
  - Groupe de dépendances **`explo`** : `ipykernel` (noyau), `matplotlib` (graphiques), `nbclient` (exécution sans interface, pour vérifier qu'un notebook tourne de bout en bout), `nbformat` (lecture et écriture des `.ipynb`). La justification de chacune est écrite dans `pyproject.toml`.
- **LaTeX** : sources `.tex` dans `docs/latex/mathematiques/`, avec un fichier principal et un dossier `chapitres/`. L'installation de Tectonic n'a pas été autorisée pendant la partie 3 : pas de compilation locale. Les sources sont vérifiées (environnements équilibrés, références), puis l'utilisateur les téléverse sur Overleaf. Chaque formule du chapitre est relue avec le code qu'elle décrit.

## Conséquences

- Un notebook se relit dans Git (code et texte) et se réexécute pour voir ses chiffres ; le résumé de ses conclusions est dans `docs/realisation/07_exploration/README.md`.
- La CI installe aussi le groupe `explo` (`uv sync --all-groups`), sans exécuter les notebooks : il leur faut une base remplie.
- **Critère de révision** : un besoin de compiler localement (rapport LaTeX v1 du jalon J8, figures générées par le code). Dans ce cas, Tectonic, avec l'accord de l'utilisateur, dans une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
