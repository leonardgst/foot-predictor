# ADR-0008 — API-FOOTBALL fait foi pour les identifiants ; `staging` reconstruit depuis le brut

- **Statut** : acceptée ; règle 2 complétée par l'ADR-0011 (appariement des matchs postérieurs au gel)
- **Date** : 2026-09-28
- **Référence** : rapport de cadrage, B.4 (D1, D2, D11), F.1, G.13, décision M7 ; `docs/realisation/05_controle_qualite/constats_P1_P2.md` ; ADR-0003

## Contexte

L'ancien chargement vers `staging` identifie les joueurs et les équipes API-FOOTBALL par leur **nom** (`ingestion/api_football.py`, `ingestion/common.py`). Les homonymes sont fusionnés, et le référentiel actuel dépend de 19 corrections faites à la main, uniquement dans la base dev.

Les contrôles des paliers P1 et P2 (2026-09-28) montrent que le brut API-FOOTBALL peut servir de référence :

| Constat | Valeur |
|---|---|
| Matchs détaillés | 64 573 (50 105 en P1, 14 468 en P2), 100 % des matchs terminés |
| Entrées de composition sans identifiant de joueur | 1 151 (1 098 en P1, 53 en P2) |
| Identifiants « aux noms incompatibles » | 1 118 (1 017 en P1, 101 en P2) |
| Doublons probables (même nom, même date de naissance, deux identifiants) | 33 groupes |
| Titulaires sans profil `/players` | 335 |

**Les 1 118 identifiants ne sont pas 1 118 erreurs.** `quality/raw_check.py` signale un identifiant dès que deux de ses noms, pris dans les compositions, les statistiques joueurs et les événements, n'ont aucun mot significatif en commun. Un surnom et un nom d'état civil suffisent à déclencher l'alerte. Le vrai danger est la **collision** : un identifiant qui désigne deux personnes. Elle se repère au comportement, pas au nom.

Deux autres faits comptent :

- **Structure existante.** Le schéma `staging` utilise déjà des clés internes et des tables de correspondance (`competition_`, `team_`, `player_`, `match_source_mapping`) avec une contrainte d'unicité sur (source, référence).
- **Couverture API.** Elle commence en 2010 pour le top 5 et la Ligue 2, en 2011 pour le Championship et la 2. Bundesliga, et **seulement en 2016** pour la Segunda División et la Serie B (`docs/realisation/03_collecte/couverture.md`). Avant ces dates, seul football-data fournit des matchs.

## Options envisagées

1. **Logique actuelle** : football-data crée les matchs, les noms identifient les joueurs. Conséquences : homonymes fusionnés, corrections manuelles non reproductibles. Déjà écartée de fait par les ADR-0001 et 0003.
2. **API-FOOTBALL fait foi**, `staging` reconstruit depuis le brut, clés internes et tables `*_source_mapping` conservées ; football-data et Understat rattachés par des YAML versionnés. Conséquences : environ 30 h de travail (jalon J3), base saine et reproductible.
3. **Variante de l'option 2 : identifiants API comme clés primaires.** Plus lisible, mais aucune entité absente de l'API ne peut exister. Par exemple, les matchs de Segunda et de Serie B antérieurs à 2016 laisseraient un trou dans l'Elo de ces clubs.
4. **Identifiant neutre, toutes sources à égalité.** Plus général, plus long, sans besoin concret aujourd'hui. La structure de l'option 2 permet d'y venir plus tard.

## Décision

Option 2, avec quatre règles.

1. **Création des entités.** Un joueur ou un entraîneur n'est créé qu'à partir d'un identifiant API-FOOTBALL. Un identifiant API correspond à une seule entité interne (contrainte d'unicité). Un titulaire sans identifiant reste « inconnu » : il n'est pas créé, et il compte 0 dans les indicateurs de composition.
2. **Rattachement des autres sources.**
   - football-data et Understat ne créent **jamais** de joueur.
   - Leurs équipes sont rattachées à un `team.id` API par un YAML versionné, qui remplace les YAML actuels « nom → nom canonique ».
   - Leurs matchs sont appariés aux matchs API par (équipe à domicile, équipe à l'extérieur, date à ±1 jour).
   - football-data ne crée des matchs (et, si nécessaire, des équipes marquées « hors API ») que **hors de la couverture API**.
3. **Identité des joueurs : tri par le comportement, pas par le nom.**
   - **Collisions** (un identifiant, deux personnes) : même identifiant dans deux équipes le même jour, deux fois dans un même match, ou deux dates de naissance différentes dans les profils. Chaque collision est scindée ou exclue par un YAML versionné.
   - **Doublons** (une personne, deux identifiants ; 33 groupes connus) : YAML d'alias vers un identifiant principal.
   - **Tout le reste** est une variante de nom : les noms sont de simples étiquettes.
4. **Aucune correction en base.** Toute correction est un fichier YAML versionné, rejoué par le chargement (`fp load`) et couvert par des tests.

**Avant le gel du 19 octobre**, deux actions sont inscrites au calendrier :

- ajouter le test de collision à `quality/raw_check.py` et le lancer sur P1 à P3. Cela se fait sans quota et donne le vrai nombre de cas ;
- si ce résultat ou les 335 titulaires sans profil le justifient, lancer des requêtes ciblées sur les profils de joueurs, tant que l'abonnement est actif. Le point d'accès exact et son coût restent à vérifier. Ces requêtes demandent un **accord explicite** (`CLAUDE.md`) et n'utilisent que la réserve de quota.

## Conséquences

- **Jalon J3** (après le gel, environ 30 h) :
  - migration 0004 : identifiants sources, contraintes d'unicité, index ;
  - chargeurs de `ingestion/` qui lisent `data/raw/` ;
  - YAML de rapprochement dans `ingestion/mappings/`. Noms indicatifs : équipes football-data et Understat vers `team.id`, alias de joueurs, collisions de joueurs ;
  - tests sur payloads réels anonymisés.
- **Code existant.**
  - `ingestion/api_football.py` n'est toujours **pas exécuté** : il est remplacé par le nouveau chargeur (ADR-0007).
  - `mapping_builder/` peut servir à produire des brouillons de YAML d'équipes, relus à la main.
  - `scripts/one_off/` part aux archives.
- **Nouveaux contrôles de J3** :
  - chaque joueur des compositions correspond à une seule entité interne ;
  - taux d'appariement des matchs football-data couverts par l'API ;
  - liste des matchs football-data non appariés.
- **Hors périmètre de cette ADR** : le rapprochement de joueurs entre sources (par exemple Understat vers API). Aucune variable du MVP n'en dépend ; si le besoin apparaît, il fera l'objet d'une ADR dédiée.
- **Critères de révision** :
  - plus de quelques dizaines de collisions réelles (seuil indicatif : 50). L'identifiant API ne serait alors plus assez fiable pour les indicateurs de composition, et il faudrait revoir la règle 3 ;
  - un appariement football-data ↔ API inférieur à 99,5 % sur la période couverte par l'API. Il faudrait alors revoir la règle d'appariement de la règle 2.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
