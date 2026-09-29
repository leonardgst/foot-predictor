# ADR-0028 — Scellé technique : une date unique, une porte unique de lecture des matchs, un journal

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : ADR-0012 (règle 4, « scellé technique », et conséquences « Code ») ; rapport de cadrage, I.5, I.8 ; partie 3, sous-étape 3.1

## Contexte

L'ADR-0012 met sous scellés tout match joué à partir du 1er juillet 2025. Les données de ces matchs sont déjà dans le brut et dans `staging` (167 876 matchs, dont 7 548 après cette date pour les 10 divisions du MVP). Le scellé ne peut donc pas reposer sur leur absence : il doit être **protégé par le code**. L'ADR-0012 le demande pour la construction du jeu de données, la commande d'évaluation et les notebooks, avec une option explicite et un journal versionné.

Jusqu'ici, chaque module de `features/` et de `modeling/` interrogeait lui-même `staging.match`. Chaque nouvelle requête aurait été une occasion d'oublier le filtre.

## Options envisagées

1. **Filtre dans chaque requête** : simple, mais rien n'empêche une requête d'oublier le filtre.
2. **Filtre après coup** (lire tout, puis retirer les matchs scellés en pandas) : les valeurs scellées passent en mémoire et peuvent fuir (affichage, moyenne calculée trop tôt).
3. **Une porte unique qui filtre à la source**, une date écrite une seule fois, une seconde barrière après la requête, et un test d'architecture qui interdit tout autre accès.

## Décision

Option 3.

- **Date unique** : `foot_predictor.seal.SEAL_DATE = 2025-07-01`. Un match est scellé si son coup d'envoi UTC est au 1er juillet 2025 ou après ; pour un match hors API, la date de football-data fait foi (stockée à minuit UTC).
- **Porte unique** : `foot_predictor.features.sources.load_matches`. Elle lit `staging` et place le filtre dans la clause `where` de la requête SQL (`match_date < :upper`). Une borne `until` plus stricte est permise, une borne plus tardive jamais : `until` ne lève pas le scellé.
- **Seconde barrière** : `check_seal` vérifie les dates renvoyées et lève `SealViolation` s'il en reste une au-delà de la frontière. Son message ne donne que le **nombre** de matchs, jamais leur contenu.
- **Option explicite** : `sealed_test=True` (future option `--sealed-test` des commandes). Elle exige le fichier d'expérience et ajoute une ligne à `reports/sealed_tests.md` : date UTC, commit, fichier d'expérience, résultat. Le journal est créé avec son seul en-tête, et un test vérifie qu'il ne contient aucun usage.
- **Test d'architecture** (`tests/features/test_architecture.py`) :
  - dans `features/`, hors `sources.py` et hors des anciens modules (`features/legacy/`), aucun import du modèle `Match` ni de SQL sur `staging.match` ;
  - les notebooks n'importent du projet que `foot_predictor.features.sources`, ni `sqlalchemy`, ni `psycopg`, ni le texte `staging.`.

**Ce que la porte couvre** : jeux de données (`features build`), notebooks d'exploration, mesures chiffrées des rapports de variables, et `modeling/` quand il sera réécrit (partie 4).

**Ce qu'elle ne couvre pas** : une requête écrite à la main (`psql`, `docker exec ... psql`, script jetable). Là, le scellé relève de la **discipline** : filtre `match_date < '2025-07-01'` explicite pour toute valeur (score, tirs, xG, cotes) ; après cette date, présence et décomptes seulement. Règle écrite dans `CLAUDE.md`.

## Conséquences

- `modeling/` lit encore l'ancienne table `features.team_match_features` sans filtre du scellé. Il n'est pas exécuté en partie 3 et sera réécrit en partie 4 sur la porte ; le test d'architecture s'étendra alors à `modeling/`.
- Dans le conteneur Docker, les jointures parallèles d'une lecture complète dépassent `/dev/shm` (64 Mo) : la porte désactive le parallélisme pour sa seule session (E-035).
- Le test scellé de la partie 4 passe par `sealed_test=True` ; il est lancé une fois par version (ADR-0012, règle 5).
- **Critère de révision** : un usage du scellé hors journal, ou un accès aux matchs qui contourne la porte. Le constater dans une nouvelle ADR, comme le prévoit l'ADR-0012.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
