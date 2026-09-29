# ADR-0030 — Jeu de données : instantané Parquet versionné, traçabilité en base, une ligne par (match, équipe)

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : rapport de cadrage, F.2 (couche « variables »), I.1, I.3 ; ADR-0009 (cible), ADR-0010 (horizons), ADR-0012 (plis, scellé), ADR-0028 (porte unique) ; décisions d.5, d.6, d.9 et d.10a de la partie 3

## Contexte

Le MVP a besoin d'un jeu de données **figé et reproductible** : les plis de la partie 4 et le test scellé doivent pouvoir dire exactement sur quelles lignes ils ont été calculés. L'ancien pipeline écrivait les variables ligne par ligne dans `features.team_match_features`, une table vidée par chaque `load` (cascade depuis `staging`), sans version ni empreinte.

Faits de la partie 3 :

- 10 championnats (top 5 et D2), de 2000-01 à 2024-25 : environ 98 000 matchs, donc environ 196 000 lignes (match, équipe) ;
- 249 matchs de barrage ou de play-offs dans les championnats API avant le scellé, aucun avant 2010 (football-data ne les a pas) ; *correction factuelle du 2026-09-29 : « 290 » dans la première rédaction, erreur d'addition de l'étape 0* ;
- 66 colonnes au registre, dont 54 variables (3 demi-vies candidates).

## Options envisagées

1. **Table large en base**, une colonne par variable : vidée par `load`, migration à chaque variable, lente à écrire.
2. **Instantané Parquet par version, avec un manifeste**, et une table de **traçabilité** en base.
3. Fichiers CSV : non typés, volumineux, ambigus (dates, valeurs vides).

## Décision

Option 2.

- **Produit** : `data/datasets/<version>/dataset.parquet` (pyarrow, compression zstd), avec `manifest.json`. Le dossier `data/` est ignoré par Git (licences et volume).
- **Traçabilité** : migration **0006, additive**, table `features.dataset_version` (version, date, commit, révision Alembic, `ops.load_run.id` lu, sha256 du registre et du manifeste, paramètres figés, périmètre, décomptes, chemin). Elle n'a aucune clé étrangère vers `staging`, pour que la trace survive à un `load` (test).
- **Version** : `ds-<AAAA-MM-JJ>-<8 premiers caractères du sha256 du manifeste>`. Le manifeste garde la révision Alembic, le chargement lu, le commit, le sha256 du registre, les paramètres figés (Elo, `xg_proxy`, glissants, huis clos), les décomptes et le sha256 de chaque fichier. Même contenu, même version.
- **Périmètre** : une ligne par (match, équipe) ; matchs de **saison régulière** des 10 championnats, de 2000-01 à 2024-25, terminés, non exclus (ADR-0009), avec un score au temps réglementaire.
  - Les barrages alimentent l'historique (Elo, glissants, repos), mais ne donnent **aucune ligne** (d.10a) : la population reste homogène avant et après 2010.
  - `phase` : `rodage` avant 2015-16, `apprentissage` de 2015-16 à 2020-21, `validation` de 2021-22 à 2024-25 (ADR-0012).
  - `eval_population` : championnats du top 5.
  - Le choix des données d'apprentissage (top 5 seul, avec les D2) reste une expérience de la partie 4.
- **Registre** (`features/registry.yaml`) : chaque colonne y figure, et inversement (test). Une entrée peut décrire la colonne de l'équipe et celle de l'adversaire (`opp_`), et une variable distincte par demi-vie.
- **Anciens modules** : `features/legacy/`, avec un bandeau « remplacé, retrait en partie 4 ». `modeling/` (ancien, non exécuté en partie 3) n'est pas modifié, sauf ses trois lignes d'import vers `features/legacy/`.
- **Nouvelle dépendance `pyarrow`** : pandas l'exige pour écrire du Parquet. L'alternative simple (CSV) perd les types et les valeurs vides ; `fastparquet` est moins répandu. Déjà cité par le rapport (E.1, F.2).

## Conséquences

- `load` vise la révision 0006.
- `python -m foot_predictor.features build` lit la porte (ADR-0028), calcule G0 à G3, écrit l'instantané et la ligne de traçabilité ; `check` contrôle un instantané.
- Déterminisme attendu : deux `build` sur le même `staging` et le même commit donnent les mêmes sha256.
- Phase B de la partie 3 : après le gel, un `build` sur le brut définitif doit redonner, pour les matchs d'avant le 1er juillet 2025, les mêmes lignes.
- **Critère de révision** : un besoin de lire les variables en SQL (API de la partie 5), ou un instantané trop gros pour le portable. Dans ce cas, une table de variables par version, en base, dans une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
