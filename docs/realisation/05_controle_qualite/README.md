# Étape 05 : contrôle qualité du brut API-FOOTBALL

Mode d'emploi de `src/foot_predictor/quality/raw_check.py`, qui applique les contrôles du rapport de cadrage (G.9) au brut collecté. Décisions liées : ADR-0002 (un palier ne commence que lorsque le précédent est collecté **et contrôlé**) et ADR-0003 (format du brut).

## En bref

- **Lecture seule** : l'outil lit les fichiers `.json.gz`, le journal `_manifest/*.jsonl` et la file `_queue/api_football.sqlite`. La file est ouverte en SQLite `mode=ro`. Aucun appel réseau, aucune base de données. Il refuse d'écrire son rapport dans le dossier brut.
- **Sans risque pendant une collecte** : une ligne de journal en cours d'écriture est signalée, pas fatale. Les fichiers écrits mais pas encore journalisés apparaissent « hors journal » (avertissement).
- **Sortie**, deux fichiers par palier et par jour. Relancer le même jour les remplace.
  - `reports/data_quality/raw_check_<palier>_<AAAA-MM-JJ>.md` : **résumé chiffré, versionné**. Il contient les verdicts et les compteurs par contrôle et par championnat-saison, sans aucun nom ni identifiant de joueur.
  - `reports/data_quality/details/raw_check_<palier>_<AAAA-MM-JJ>_details.md` : **listes détaillées, ignorées par Git**. Elles donnent les matchs sans détail, les joueurs en cause (noms, identifiants), les fichiers corrompus et les tâches en échec.

  Pourquoi cette séparation : les données restent privées (ADR-0002). Seuls les nombres sont committés ; les listes nominatives restent sur le poste.

## Commande

Depuis la racine du dépôt :

```powershell
uv run python -m foot_predictor.quality.raw_check --palier P1 --raw-dir C:/foot-predictor/data/raw
```

| Option | Rôle | Défaut |
|---|---|---|
| `--palier P` | palier à contrôler, répétable (`--palier P1 --palier P2`) | tous les paliers du YAML |
| `--raw-dir D` | dossier brut à lire | `data/raw` |
| `--config F` | fichier des paliers (périmètre attendu) | `config/collecte_api_football.yaml` |
| `--output-dir D` | dossier du résumé ; les listes vont dans `<D>/details/` | `reports/data_quality` |

Le terminal affiche le verdict de chaque contrôle et le chemin des deux fichiers. Code de retour : `0` si rien n'est bloquant, `1` si au moins un contrôle est bloquant, `2` en cas d'erreur d'usage (palier inconnu, dossier absent).

## Ce qui est contrôlé

Le périmètre attendu, c'est-à-dire les championnat-saisons de chaque palier, est tiré du YAML de collecte et filtré par la dernière réponse `/leagues`, avec les mêmes règles que `plan`. Pour chaque fichier, seule la version la plus récente compte.

| Famille | Contrôle | Statut si écart |
|---|---|---|
| Complétude | Liste de matchs présente | BLOQUANT |
| Complétude | Matchs de saison régulière = n × (n - 1) pour n équipes (championnats seulement) | À REGARDER |
| Complétude | Tout match terminé (FT, AET, PEN, AWD, WO) a un détail ; dans les coupes, seulement les matchs d'une équipe suivie | BLOQUANT |
| Détails | 2 compositions par match ; 11 titulaires et 1 gardien titulaire par équipe | À REGARDER si < 99 % |
| Détails | `players` non vide pour les 2 équipes ; `events` non vide | À REGARDER si < 99 % |
| Cohérence | Buts comptés dans `events` = `goals` | À REGARDER |
| Identifiants | `player.id` présent (compositions, statistiques, événements, profils) | À REGARDER |
| Identifiants | Chaque titulaire a un profil `/players` du même championnat-saison (si toutes les pages sont là) | À REGARDER |
| Identifiants | Un identifiant n'a pas de noms incompatibles | À REGARDER |
| Identifiants | Doublons probables : même nom, même date de naissance, identifiants différents ; « inter-paliers » si seul le contrôle commun les trouve | À REGARDER |
| Identifiants | **Collisions** (ADR-0008, règle 3) : même identifiant chez deux équipes le même jour ; deux fois dans un match ; deux dates de naissance | À REGARDER |
| Plausibilité | Minutes entre 0 et 130 ; note entre 3 et 10 | À REGARDER |
| Journal | sha256 conforme au journal, fichier présent et lisible (tout le dossier brut) | BLOQUANT |
| Journal | Tâches `failed` du palier | BLOQUANT |
| Journal | Tâches `suspect` ou `pending` du palier, fichiers hors journal | À REGARDER |

**Pourquoi deux niveaux ?** BLOQUANT signale un trou ou une corruption que l'on peut encore corriger pendant l'abonnement : recollecte, `requeue`, restauration. À REGARDER signale le plus souvent une donnée telle que l'API la fournit ; la redemander ne changerait rien. On l'examine, puis on la documente (futur `DATA_FREEZE.md`). Une tâche `failed` n'est jamais retentée automatiquement : il faut décider (`requeue` ou abandon documenté). C'est pour cela qu'elle bloque.

## Règles et limites à connaître

- **Couverture** : un contrôle de détail n'est pas appliqué à une saison que `/leagues` déclare non couverte. Le tableau affiche alors « n. c. ». Sans réponse `/leagues`, tout est contrôlé.
- **Nombre attendu** : l'hypothèse aller-retour ne vaut pas pour tous les formats (Suisse, Écosse, Belgique, MLS, Argentine...). Pour ces championnats, un écart est normal : il faut le vérifier à la main. Les barrages (`round` autre que « Regular Season ») sont exclus. Une saison arrêtée (Ligue 1 2019-20) sortira aussi en écart.
- **Buts** : les penalties manqués et les tirs au but (`comments = "Penalty Shootout"`) ne comptent pas. Un but contre son camp est attribué par l'API à l'équipe qui en profite. Les matchs sur tapis vert (AWD, WO) sont exclus des contrôles de détail.
- **Noms** : l'API abrège les noms dans les compositions (« S. Romero ») et les donne en entier ailleurs (« Sergio Romero »). Deux noms sont jugés compatibles s'ils partagent un mot significatif : pas une initiale, pas une particule comme « de » ou « van ». La comparaison ignore les accents et translittère ø, ł, ß... Seuls les identifiants dont les noms forment plusieurs groupes incompatibles sont listés.
- **Doublons** : la date de naissance vient uniquement des profils `/players` ; les détails de match n'en ont pas.
- **Plusieurs paliers ensemble** (`--palier P1 --palier P2 --palier P3`) : doublons et collisions se calculent sur l'ensemble. Un cas qui réunit deux paliers est étiqueté « P1+P3 » dans le tableau de la section 5 du résumé.
- **Collisions**, trois types (constats : [`constats_collisions.md`](constats_collisions.md)) :
  - *même jour* : un identifiant chez deux équipes le même jour (date UTC du match). L'équipe d'un joueur est celle de sa composition, sinon celle de ses statistiques ;
  - *même match* : l'identifiant chez les deux équipes, ou avec deux numéros de maillot dans la même équipe ;
  - *deux naissances* : deux dates dans les profils. Une date qui change **une fois** d'une saison à l'autre est une correction de l'API, listée à part.
- **Faux positifs écartés automatiquement**, comptés dans le résumé :
  - l'identifiant `0`, donné par l'API aux joueurs qu'elle ne connaît pas ;
  - les matchs dont les statistiques sont rattachées à l'équipe adverse (au moins 5 joueurs dans ce cas) ;
  - la même entrée répétée (même équipe, même numéro).
- **Coût** : aucune passe de plus sur le brut. Les présences (joueur, jour, équipe, match) sont relevées pendant la lecture des détails, puis regroupées une fois avec numpy : environ 160 Mo de mémoire pour P1 à P3 et 10 % de temps en plus.
- **sha256** : la vérification porte sur tout le dossier brut, pas seulement sur le palier. Elle relit tous les fichiers : compter environ une minute par Go.

## Quand le lancer

- Après chaque journée de collecte d'un palier, pour suivre les trous.
- Avant de planifier le palier suivant (ADR-0002) : le verdict doit être OK ou À REGARDER, et chaque point « à regarder » examiné.
- Au gel (19 octobre), sur tous les paliers : le dernier rapport alimente `DATA_FREEZE.md`.

## Tests

```bash
uv run pytest tests/quality -q
```

Les tests rangent les 5 matchs réels de `tests/fixtures/api_football/` dans un dossier brut temporaire (fichiers, journal, file), puis y injectent une anomalie de chaque sorte. Ils vérifient aussi :

- que le dossier brut est identique, octet pour octet et date de modification comprise, avant et après le contrôle ;
- que le résumé ne contient ni nom de joueur ni identifiant de joueur en anomalie, alors que le fichier de détails les liste ;
- pour les collisions, sur des matchs synthétiques : un cas positif et un cas négatif par type, les faux positifs (identifiant 0, statistiques inversées, entrée répétée), une date corrigée, et les cas visibles seulement quand P1 et P3 sont contrôlés ensemble.
