# ADR-0024 — Bruts externes (football-data) : dossier racine séparé jusqu'au gel, même format que l'API

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : ADR-0003 (format du brut), ADR-0006 (sauvegarde), ADR-0018 et ADR-0021 (règles jusqu'au gel), ADR-0023 (sources) ; décision d.7 de la session « partie 2 » du 2026-09-29

## Contexte

Le brut football-data doit être stocké tel que téléchargé, toutes colonnes comprises (ADR-0003). Jusqu'au gel du 19 octobre, le dossier `C:/foot-predictor/data/raw` ne reçoit aucune écriture autre que celle du collecteur API : le gel compte ses fichiers et vérifie leurs sha256 (`freeze`, `DATA_FREEZE.md`). `rawstore` n'écrit que des enveloppes JSON, et il est gelé.

## Options envisagées

1. Écrire les CSV dans `C:/foot-predictor/data/raw` : fausserait les décomptes du gel, et enfreint les règles du gel.
2. **Dossier racine séparé, même arborescence et même journal, puis recopie après le gel.**
3. Stocker le CSV dans une enveloppe JSON : ce ne serait plus le fichier tel que téléchargé (encodage, BOM).

## Décision

Option 2.

- Dossier racine des bruts externes : `C:/fp-travail/data/raw/` (ignoré par Git), passé par `--raw-dir` ; aucun chemin n'est écrit en dur dans le code.
- Arborescence : `football_data/csv/season=<année>/<division>__<horodatage>.csv`. Le fichier est stocké **octet pour octet** : nouveau module `collect/raw_bytes.py`, voisin de `rawstore/`, sans modifier ce dernier.
- Journal `_manifest/football_data.jsonl` : une ligne par fichier stocké (URL, date, statut HTTP, taille, durée, `file`, `sha256`), lue par `backup`, `verify` et `raw_check` comme les autres journaux. Verrou `_lock/collecte.lock` pendant un téléchargement.
- Le collecteur **refuse** un dossier qui contient déjà le brut API-FOOTBALL (`api_football/` ou `_queue/`), sauf option explicite après le gel.
- **Après le gel** (partie 2, phase B) : recopie de `football_data/` et de son journal vers `C:/foot-predictor/data/raw`, avec vérification des sha256.
- **Sauvegarde** : copie sur le disque externe dans un nouveau dossier, une fois la collecte faite (d.7). Le 2026-09-29, l'écriture sur `D:` a été refusée par les permissions de la session : cette copie reste à faire (voir le retour de la partie 2). Le brut football-data se retélécharge, contrairement au brut API.

## Conséquences

- Le chargeur (`load`) prend deux dossiers : le brut API (`--raw-dir`) et celui des bruts externes (`--external-raw-dir`), qui ne font plus qu'un après la recopie.
- **Critère de révision** : une seconde source externe (collecteur live de J7, ADR-0011) ou la réunion des deux dossiers ; mettre alors à jour cette ADR par une nouvelle.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
