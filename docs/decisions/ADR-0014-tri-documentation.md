# ADR-0014 — Restructuration de la documentation : première passe (archives, index, aucun dossier vide)

- **Statut** : acceptée
- **Date** : 2026-09-28
- **Référence** : rapport de cadrage, K.1, K.2, décision M19 ; branche `docs/01-tri-documentation`

## Contexte

- `docs/` mélangeait des documents vivants (état, journal, ADR, modes d'emploi) et des documents dépassés (`RECAP_PROJET.md`, `OBJECTIFS.md`, `API_FOOTBALL_ABONNEMENT.md`, 11 récaps). Ces derniers contredisent les ADR 0007 à 0013 : cible « score exact », bouton grisé jusqu'à la composition, MVS comme prochaine étape, chargement par `ingestion/api_football.py`.
- Le rapport (K.1) propose une arborescence complète (`cadrage/01` à `14`, `technologies/`, `resultats/`, `latex/`) et interdit les dossiers vides.
- Contraintes : le code cite certains documents par leur nom ou leur chemin (`RESULTATS_MODELE.md`, `model_results.json`, `couverture.md`, `MODELE_MATHEMATIQUE.md`, récaps) ; la collecte P3 tourne ; aucune modification de `src/`, `tests/` ni `config/` dans cette passe.

## Options envisagées

1. **Migration complète vers K.1** : tous les dossiers d'un coup. Conséquences : beaucoup de fichiers à écrire sans contenu nouveau, chemins cités par le code à changer.
2. **Première passe** : archiver ce qui est dépassé, reporter ce qui reste vrai dans les documents vivants, ajouter un index. Les autres dossiers de K.1 naissent avec leur contenu.

## Décision

Option 2.

- Les documents dépassés vont dans `docs/archives/` par `git mv`, sous leur nom d'origine, avec un bandeau « Archivé le …, les ADR font foi ». Rien n'est supprimé.
- Ce qui reste vrai et utile est reporté : incidents et leçons dans `JOURNAL_ERREURS.md`, contradictions corrigées dans les documents vivants.
- `docs/README.md` sert d'index : où trouver quoi, ordre de lecture, anciens chemins.
- Les fichiers cités par le code restent à leur place (`RESULTATS_MODELE.md`, `model_results.json`, `MODELE_MATHEMATIQUE.md`, `realisation/03_collecte/couverture.md`).
- Aucun fichier `cadrage/0N_*.md` n'est créé : le rapport (A, C.3, G.12) et les ADR couvrent déjà le contenu.

## Conséquences

- Reportés, créés quand leur contenu existe : `cadrage/0N_*.md`, `technologies/`, `resultats/`, `latex/`, `realisation/README.md`.
- Les commentaires de code qui citent un document archivé restent à mettre à jour (liste dans la PR) ; les noms étant gardés, on retrouve le fichier dans `docs/archives/`.
- Le rapport et les ADR 0007 et 0010 citent d'anciens chemins : la table des anciens chemins de `docs/README.md` y répond, sans les modifier.
- Critère de révision : si l'index ne suffit plus à trouver un document, ou si un document vivant contredit de nouveau une ADR, faire une seconde passe.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
