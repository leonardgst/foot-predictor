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
- **Décisions M7 à M12 tranchées** (2026-09-28, PR #11) :
  - ADR-0008 : API-FOOTBALL fait foi pour les identifiants ;
  - ADR-0009 : cible et métrique. Le critère E.1(4) du rapport est remplacé ;
  - ADR-0010 : deux horizons de prédiction ;
  - ADR-0011 : rejeu et live après l'abonnement ;
  - ADR-0012 : validation glissante et scellés ;
  - ADR-0013 : masse salariale et MVS.
- **Tri de `docs/`, première passe** (PR #12, ADR-0014, décision M19) : documents dépassés archivés dans `docs/archives/`, index `docs/README.md`, README racine en vitrine, journal complété (E-006 à E-020), documents vivants alignés sur les ADR.

## En cours

- **Palier P3** (11 autres championnats, 2015-2026, avec profils joueurs) : lancé le 2026-09-28, environ 6 000 requêtes, fin prévue le 29 septembre.

## Bloqué

- Rien. Points de vigilance :
  - ne pas exécuter `ingestion/api_football.py` (raw vers staging) : il sera remplacé par le nouveau chargeur (ADR-0008) ;
  - ne jamais lancer `docker compose down -v` ni supprimer `data/raw/` avant le gel ;
  - pas de `git pull` dans `C:/foot-predictor` pendant qu'un `run` tourne ; le code se travaille dans `C:/fp-travail` (worktree) ;
  - **scellé (ADR-0012)** : aucune analyse des résultats (scores, buts, performances) des matchs joués à partir du 1er juillet 2025. Les contrôles de complétude du brut restent permis.

## Décisions ouvertes

- Renouvellement automatique de l'abonnement : à vérifier dans le tableau de bord.
- Rapport, décisions 13 à 22, non bloquantes. À trancher en priorité : **M17** (Understat, qui conditionne l'xG en live, ADR-0011) et **M16** (variante de stabilité).

## Prochaines actions

**Court terme**

- [ ] Terminer P3 (relancer `run` le 29 après 02:00, heure de Paris) puis `raw_check --palier P3`.
- [ ] Après P3 et la fusion des PR de documentation : retirer de `C:/foot-predictor` les copies non suivies des ADR 0008 à 0013 et de `docs/decisions/README.md` et `docs/ETAT_PROJET.md`, puis `git pull`.
- [ ] **Test de collision des identifiants de joueurs** dans `quality/raw_check.py`, sans quota (ADR-0008). Détecte un même identifiant chez deux équipes le même jour, deux fois dans un match, ou avec deux dates de naissance. Branche courte, puis lancement sur P1 à P3.
- [ ] `refresh --season 2026 --palier P1` le **lundi 5 octobre** (d'abord `--dry-run`), puis `run`.

**Moyen terme (d'ici le 19 octobre)**

- [ ] Selon le résultat du test de collision : **requêtes ciblées sur les profils** des identifiants en collision et des 335 titulaires sans profil, **avant le 16 octobre**. Point d'accès et coût à vérifier ; accord explicite requis ; réserve de quota seulement (ADR-0008).
- [ ] `refresh` le **lundi 12 octobre**.
- [ ] Facultatif, après P3, les `refresh` et les actions de l'ADR-0008 :
  - **journal T-60** : compositions annoncées avant le coup d'envoi, sur quelques journées du top 5, pour vérifier que le onze annoncé est celui du détail du match (ADR-0010) ;
  - P4 (sidelined, standings).
- [ ] 17-18 oct. : rattrapages uniquement (`status`, `requeue`, `run`).
- [ ] **19 oct.** : `refresh` le matin, `run`, `raw_check` sur tous les paliers, `DATA_FREEZE.md`, export sur disque externe, test de restauration, commit des résumés de contrôle, tag `data-freeze-2026-10`.

**Long terme**

- **PR de nettoyage** : anciens collecteurs (ADR-0004, 0007), retrait de `hdbscan`, `market_value/` marqué gelé (ADR-0013), instrumentation de diagnostic de `understat.py`, commentaires de code qui citent des documents archivés et constante inutilisée `RESULTS_MD_PATH` (liste dans la PR du tri de `docs/`).
- **J3 Référentiel** : `staging` reconstruit depuis le brut, identifiants API, YAML de rapprochement et d'alias (ADR-0008).
- **J4 Variables v2** : registre des variables avec horizon (ADR-0010).
- **J5 Protocole et références** : métriques du total (ADR-0009), plis glissants et scellé technique (ADR-0012).
- **J6 Modèle MVP** : test scellé n° 1 (ADR-0012).
- **J7 et J8** : API, interface, collecteur football-data pour le live (ADR-0011), `v1.0.0`.
- **J9 Version intermédiaire** : groupe « qualité du XI » (ADR-0013), stabilité, test scellé n° 2.
- Détail des jalons : rapport, partie L.

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
