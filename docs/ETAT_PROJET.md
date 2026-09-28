# État du projet

**Dernière mise à jour** : 2026-09-28
**Jalon courant** : J1 — Collecte (rapport de cadrage, partie L) : P1 et P2 terminés et contrôlés, P3 en cours.
**Échéance dure** : fin de l'abonnement API-FOOTBALL le **2026-10-22 à 07:56 UTC** ; gel des données le **19 octobre** (ADR-0005)

## Terminé

- Cadrage intégré (PR #5) : rapport `docs/cadrage/rapport_cadrage_2026-09-24.md`, ADR-0001 à 0006, `CLAUDE.md`, cet état, `docs/JOURNAL_ERREURS.md`.
- Collecteur v2 (PR #6, ADR-0007), inventaire de couverture (PR #7), contrôle qualité du brut (PR #8), commande `refresh` de la saison en cours (PR #9).
- **Palier P1** collecté (2026-09-27 et 28) et contrôlé : 50 105 matchs détaillés (100 %), aucun échec, 7 entraîneurs vides côté API (acceptés).
- **Palier P2** collecté et contrôlé (2026-09-28) : 38 championnat-saisons avant 2015, 14 468 matchs détaillés (100 %). Compositions seules : pas de postes ni de statistiques joueurs.
- Constats détaillés et conséquences : `docs/realisation/05_controle_qualite/constats_P1_P2.md`.

## En cours

- **Palier P3** (11 autres championnats, 2015-2026, avec profils joueurs) : lancé le 2026-09-28, environ 6 000 requêtes, fin prévue le 29 septembre.

## Bloqué

- Rien. Points de vigilance :
  - ne pas exécuter `ingestion/api_football.py` (raw vers staging) avant correction de l'identification des joueurs (rapport B.4, D1 et D3) ;
  - ne jamais lancer `docker compose down -v` ni supprimer `data/raw/` avant le gel ;
  - pas de `git pull` dans `C:/foot-predictor` pendant qu'un `run` tourne ; le code se travaille dans `C:/fp-travail` (worktree).

## Décisions ouvertes

- **À trancher avant le 19 octobre** (conversation dédiée) : M7 à M12 du rapport, qui deviendront les ADR-0008 et suivantes :
  M7 référentiel d'identifiants, M8 cible et métrique, M9 horizon de prédiction, M10 fonctionnement après l'abonnement (rejeu, live), M11 protocole de validation (2025-26 sous scellés), M12 masse salariale et MVS.
- Renouvellement automatique de l'abonnement : à vérifier dans le tableau de bord.

## Prochaines actions

**Court terme**

- [ ] Terminer P3 (relancer `run` le 29 après 02:00, heure de Paris) puis `raw_check --palier P3`.
- [ ] Trancher M7 à M12 → ADR-0008 et suivantes.
- [ ] `refresh --season 2026 --palier P1` le **lundi 5 octobre** (d'abord `--dry-run`), puis `run`.

**Moyen terme (d'ici le 19 octobre)**

- [ ] `refresh` le **lundi 12 octobre**.
- [ ] Facultatif : P4 (sidelined, standings) et journal quotidien (prompt D du plan), selon le quota et le temps.
- [ ] 17-18 oct. : rattrapages uniquement (`status`, `requeue`, `run`).
- [ ] **19 oct.** : `refresh` le matin, `run`, `raw_check` sur tous les paliers, `DATA_FREEZE.md`, export sur disque externe, test de restauration, commit des résumés de contrôle, tag `data-freeze-2026-10`.

**Long terme**

- Restructuration de `docs/` (rapport K), référentiel reconstruit depuis le brut (J3), variables v2 (J4), protocole et références (J5), modèle MVP (J6), API (J7), interface et `v1.0.0` (J8) : voir rapport, partie L.

## Début de la prochaine session

Suivi de la collecte, dans `C:/foot-predictor` (aucune requête) :

```bash
uv run python -m foot_predictor.collect.api_football status
```

Contrôle qualité d'un palier (lecture seule du brut) :

```bash
uv run python -m foot_predictor.quality.raw_check --palier P3 --raw-dir /c/foot-predictor/data/raw
```

Travail sur le code : dans `C:/fp-travail` (`git worktree add`), jamais dans le dossier de collecte pendant un `run`.
