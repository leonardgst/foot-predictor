# Étape 16 : documentation finale (jalon J8)

Deux documents LaTeX, versionnés dans le dépôt et compilés sur Overleaf (ADR-0034 ; choix reconfirmé par l'utilisateur pour le rapport v1, le 2026-10-31). Le dépôt fait foi : Overleaf n'est qu'un compilateur.

| Dossier | Contenu | Rôle |
|---|---|---|
| `docs/latex/mathematiques/` | 3 chapitres : données et variables, modèles et évaluation, inférence et disponibilité | document mathématique : équations, hypothèses, lien vers le code |
| `docs/latex/rapport/` | 8 chapitres et une annexe, bibliographie (`references.bib`), figure (`figures/`) | rapport narratif v1 (rapport de cadrage, K.2) |

## Compiler sur Overleaf

1. Compresser le dossier voulu (`mathematiques/` ou `rapport/`) en zip, son contenu à la racine du zip (`main.tex` au premier niveau).
2. Overleaf : *New Project* → *Upload Project* → le zip. Compilateur **pdfLaTeX** (menu, *Compiler*).
3. Le rapport a une bibliographie : Overleaf lance BibTeX tout seul ; sinon, *Recompile from scratch*.
4. Signaler toute erreur ou tout avertissement de référence (`??` dans le PDF) : la correction se fait dans le dépôt, par PR, jamais seulement sur Overleaf (l'offre gratuite n'a pas d'historique au-delà de 24 heures).

## Contrôle sans compilateur

Pas de compilateur local (ADR-0034). Avant chaque PR qui touche `docs/latex/`, contrôle structurel des sources : environnements `\begin`/`\end` équilibrés, accolades, `\(`…`\)` et `\[`…`\]`, `\ref` sans `\label`, étiquette en double, `\cite` sans entrée `.bib`, figure introuvable, `%` non échappé (qui commente silencieusement la fin d'une ligne). Le hook pre-commit E-053 contrôle les fins de ligne `\` au lieu de `\\`.

## Règles de rédaction

- **Chiffres** : recopiés des pages générées de `docs/resultats/` (elles-mêmes produites par `modeling summary`), des ADR ou des retours, jamais recalculés ni arrondis autrement qu'à la source. Une phrase qui cite un chiffre cite aussi son ADR ou sa page.
- **Formules** : relues avec le code qu'elles décrivent (fichier cité en commentaire en tête de chapitre) ; en cas d'écart, le code et les ADR font foi.
- **Figures** : générées par le code, copiées dans `figures/` du document (aujourd'hui : `courbe_apport.png`, de `docs/resultats/figures/`).
- **Bibliographie** : références classiques ; volumes et pages vérifiés par l'utilisateur (2026-10-31). Toute nouvelle entrée se vérifie de même avant sa fusion.
- **Scellé** : aucun chiffre tiré d'une lecture de match scellé hors des résultats publiés des tests (`docs/resultats/test_scelle_h1.md`, `test_scelle_h2.md`) et des rapports d'agrégats de l'inférence ouverte (`reports/inference/rejeu_scelle_*.md`, `prospectif_*.md`, ADR-0052).

## Version 1 (5.16, 2026-10-31)

- Document mathématique (PR #89) : section « Test scellé et modèle final » ; rejeu, modèle du live et fraîcheur par équipe (ADR-0044 à ADR-0046) ; une étiquette en double corrigée (`sec:scelle`).
- Rapport (PR #90) : introduction, état de l'art, données, architecture, méthode, résultats, application, bilan (critères E.1, limites, difficultés, perspectives, conclusion), annexes (ADR, commandes, glossaire) ; environ 20 à 25 pages attendues.
- Compilation sur Overleaf (pdfLaTeX, 2026-10-31, par l'utilisateur) : **sans erreur**.

## Version 2 (6.14, 2026-11-01)

- **Document mathématique** : nouveau chapitre « Composition des équipes (horizon H2) » (`chapitres/composition.tex`) : règle temporelle avec composition, stabilité du onze (la cohésion par paires comme somme de la matrice cumulée, démontrée), qualité du onze (note rétrécie, estimation de la constante `k` par la méthode des moments), entraîneur, modèle H2, décisions de la validation glissante, test scellé de H2. Trois sections ajoutées à « Inférence et disponibilité » : H2 en rejeu, rejeu des saisons scellées et sa garde, évaluation du journal prospectif (ADR-0051, ADR-0052).
- **Rapport v2** : résumé, introduction, données (compositions), architecture, méthode (section sur H2), résultats (H2, structures, test scellé de H2, premier relevé du journal prospectif), application (H2, garde, journal), bilan (critères E.2, limites, difficultés, perspectives, conclusion), annexes (ADR 0047 à 0052, commandes, glossaire). Aucune nouvelle référence bibliographique ni nouvelle figure.
- **Contrôle structurel sans compilateur** (script jetable, non versionné) : environnements équilibrés, accolades, `\(`/`\)` et `\[`/`\]`, `\ref` sans `\label`, étiquettes en double, `\cite`, figures, `\input`, `%` non échappés, fins de ligne `\` : propre (les deux faux positifs sont les `\\[0.5em]` des titres).
- **Compilation sur Overleaf** : à faire par l'utilisateur (pdfLaTeX, puis BibTeX pour le rapport) ; toute erreur ou tout `??` se corrige dans le dépôt, par PR.
