# Gel des données du 19 octobre 2026 : procédure

Décisions : ADR-0005 (calendrier : gel le 19, marge les 20 et 21, fin de l'abonnement le 22 à 07:56 UTC) et ADR-0006 (sauvegarde unique sur le disque externe, test de restauration le même jour). Mode d'emploi des commandes : [`README.md`](README.md).

**Répétition à blanc du 2026-09-29**, depuis le checkout principal vers un dossier temporaire :

| Étape | Durée |
|---|---|
| `raw_check` | 74 s |
| Sauvegarde | 218 s |
| Restauration | 252 s |
| **Total** | **9 min 18 s** |

16 421 fichiers (301 Mo) ont été vérifiés aux deux endroits. Le disque externe USB sera plus lent que le disque interne : prévoir **30 minutes** pour `freeze`, et 2 heures pour toute la procédure.

## Avant de commencer

- Les tâches planifiées du 5 au 18 octobre ont tourné. Leurs journaux d'exécution sont dans `C:/foot-predictor/data/logs/`.
- Le disque externe est branché sur `D:`. La copie intermédiaire du 29 septembre (`D:/foot-predictor/copie-2026-06-29/`) **ne se touche pas**.
- Deux dossiers ne doivent pas encore exister : la destination `D:/foot-predictor/data-freeze-2026-10/` et le dossier de restauration `C:/fp_restauration/`.

## Étapes

Terminal Git Bash. Les étapes 1 à 3 se lancent dans `C:/foot-predictor`, les étapes 4 à 7 dans `C:/fp-travail`.

### 1. Relire les tâches planifiées (aucune requête)

```bash
cd /c/foot-predictor
schtasks //Query //FO TABLE | grep FootPredictor        # toutes passées ; aucune en cours
grep -l "ERREUR" data/logs/*.log                          # aucune erreur attendue
tail -n 20 data/logs/refresh_2026-10-12.log data/logs/t60_2026-10-18.log
uv run python -m foot_predictor.collect.api_football lock-status   # doit dire « libre »
git pull --ff-only
```

### 2. Dernier rafraîchissement, le matin (quota : environ 60 à 150 requêtes)

Il récupère les matchs du week-end des 17 et 18 octobre, ceux du lundi 12, et les coupes d'Europe des 13 à 15 octobre.

```bash
uv run python -m foot_predictor.collect.api_football refresh --season 2026 --dry-run
uv run python -m foot_predictor.collect.api_football refresh --season 2026 --yes
uv run python -m foot_predictor.collect.api_football run --max-requests 300
uv run python -m foot_predictor.collect.api_football status     # 0 failed ; relire les suspects
```

Si des tâches sont en `failed` ou `suspect` : les examiner (`status` donne le fichier et la raison). Si c'est un trou temporaire, `requeue --status ...` puis `run --max-requests 50`. Sinon, le noter pour `DATA_FREEZE.md`.

### 3. Bilan du journal T-60 (aucune requête)

```bash
uv run python -m foot_predictor.collect.api_football t60-report
```

Reporter les nombres dans `DATA_FREEZE.md` (étape 6). Critère de l'ADR-0010 : plus de 2 % de titulaires différents.

### 4. Branche du gel, dans le worktree

```bash
cd /c/fp-travail
git fetch origin
git switch --no-track -c data/03-gel-2026-10 origin/main
```

**Pourquoi `freeze` se lance depuis le worktree** : la commande écrit `docs/DATA_FREEZE.md` et le résumé `reports/data_quality/raw_check_tous_<date>.md` dans le dossier courant. Lancée depuis le checkout principal, elle y laisserait des fichiers non suivis, qui bloqueraient le prochain `git pull` (E-021). Le code est le même : la branche part d'`origin/main`. Le brut est lu dans le checkout principal avec `--raw-dir`, et `freeze` n'envoie aucune requête.

### 5. Gel : contrôle, sauvegarde, test de restauration, brouillon

```bash
uv run python -m foot_predictor.collect.api_football --raw-dir C:/foot-predictor/data/raw freeze \
    --dest D:/foot-predictor/data-freeze-2026-10/raw --restore-to C:/fp_restauration/raw
```

La commande enchaîne cinq étapes et s'arrête à la première en échec :

1. elle prend le verrou : elle refuse de démarrer si une collecte tourne ;
2. elle lance `raw_check` sur tous les paliers : un verdict BLOQUANT arrête le gel ;
3. elle copie vers `D:`, puis vérifie les sha256 ;
4. elle recopie de `D:` vers `C:/fp_restauration/raw`, puis vérifie de nouveau ;
5. elle écrit le brouillon `docs/DATA_FREEZE.md`.

### 6. Relire, compléter et committer

- Relire `docs/DATA_FREEZE.md` et compléter les sections « À compléter » : heure du gel, bilan T-60, MLS 2017, renouvellement coupé, tâches supprimées.
- Vérifier qu'il ne contient **aucun nom ni identifiant de joueur** et aucun résultat de match (ADR-0012).
- Commit `data(gel): ...` avec `docs/DATA_FREEZE.md` et le résumé `raw_check_tous_<date>.md`, puis la PR, et la fusion après une CI verte.

### 7. Tag, ménage, abonnement

```bash
git fetch origin
git tag -a data-freeze-2026-10 origin/main -m "Gel des données API-FOOTBALL du 2026-10-19 (docs/DATA_FREEZE.md)"
git push origin data-freeze-2026-10
cd /c/foot-predictor && uv run python -m foot_predictor.collect.api_football lock-status && git pull --ff-only
uv run python scripts/taches_planifiees/creer_taches.py --delete   # tâches toutes passées
```

- **Abonnement** : couper le renouvellement automatique dans le tableau de bord d'API-FOOTBALL (ADR-0005).
- **`C:/fp_restauration/`** : ce n'est qu'une copie. La supprimer une fois le tag posé.
- **Seconde copie hors de la maison** (facultative, ADR-0006) : archive 7-Zip chiffrée sur un cloud gratuit.

## Critères de réussite

- [ ] `freeze` se termine avec le code 0.
- [ ] `raw_check` n'est pas BLOQUANT : tous les matchs terminés ont leur détail, aucun fichier corrompu, aucune tâche `failed` non décidée.
- [ ] Même nombre de fichiers vérifiés dans le brut, sur `D:` et dans la restauration, égal au nombre de lignes du journal. `freeze` compare la sauvegarde et la restauration ; comparer au brut en relisant `DATA_FREEZE.md`.
- [ ] `DATA_FREEZE.md` committé sur `main`, avec le sha256 du journal ; tag `data-freeze-2026-10` poussé.
- [ ] Tâches planifiées supprimées ; renouvellement coupé.

## Si une étape échoue

Ne rien supprimer, ni dans `data/raw/` ni sur `D:`. Relire le message : `freeze` s'arrête à la première étape en échec et dit laquelle.

| Échec | Cause probable | Conduite |
|---|---|---|
| « Dossier brut occupé » | une collecte ou une tâche planifiée tourne | attendre la fin (`lock-status`), relancer |
| `raw_check` BLOQUANT | match terminé sans détail, tâche `failed`, fichier corrompu | lire le résumé ; `requeue`, puis `run --max-requests ...` (le quota reste disponible jusqu'au 22 à 07:56 UTC) ; relancer `freeze` avec une **nouvelle** destination vide |
| Sauvegarde : sha256 différent ou fichier absent sur `D:` | copie interrompue, disque externe défaillant | relancer vers une nouvelle destination vide (`.../raw-2`) ; si l'échec se répète, vérifier le disque (`chkdsk D:`) ou en changer |
| Restauration en échec, sauvegarde conforme | lecture défaillante du disque externe | relancer seulement la restauration : `backup` de `D:` vers un nouveau dossier vide (commande ci-dessous) ; si l'échec persiste, refaire la sauvegarde sur un autre support |
| Fichier du brut corrompu (sha256 différent dans `data/raw`) | disque interne | le fichier est recollectable tant que l'abonnement est actif : retrouver la tâche avec `status`, `requeue`, puis `run`. **Marge : 20 et 21 octobre** |

```bash
# Restauration seule, depuis le disque externe vers un dossier vide
uv run python -m foot_predictor.collect.api_football --raw-dir D:/foot-predictor/data-freeze-2026-10/raw \
    backup --dest C:/fp_restauration_2/raw
```

**Au-delà du 21 octobre au soir, plus aucune recollecte n'est possible.** Si le test de restauration n'a pas réussi le 21, garder les deux copies existantes (portable et `D:`), et consigner l'état exact dans `DATA_FREEZE.md` et dans le journal des erreurs.
