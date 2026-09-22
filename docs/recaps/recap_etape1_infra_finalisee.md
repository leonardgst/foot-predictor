# Récap — Étape 1 finalisée : infra Neon, VSCode, Alembic

Ce document complète `recap_mise_en_place_git_docker.md` et clôture le point A/B/C du guide `ETAPE_1_infra.md`. Il documente l'état final ainsi que les incidents rencontrés et leurs résolutions, pour ne pas les reperdre.

---

## 1. État final — les 3 environnements sont opérationnels

| Environnement | Connexion | Statut |
|---|---|---|
| Dev | `localhost:5440` (Docker) | ✅ Schémas `raw`/`staging`/`features` créés |
| Test | `localhost:5433` (Docker) | ✅ Schémas `raw`/`staging`/`features` créés |
| Prod | Neon (cloud) | ✅ Schémas `raw`/`staging`/`features` créés |

Vérifié via SQLTools sur les 3 connexions avec :
```sql
SELECT schema_name FROM information_schema.schemata
WHERE schema_name IN ('raw', 'staging', 'features');
```

Première migration Alembic (`0001_create_schemas`) appliquée avec succès sur les 3 bases :
```bash
APP_ENV=dev  uv run alembic upgrade head
APP_ENV=test uv run alembic upgrade head
APP_ENV=prod uv run alembic upgrade head
```

## 2. ⚠️ Changement important : port dev modifié (5432 → 5440)

**Cause** : une installation PostgreSQL native (antérieure à ce projet, mentionnée comme non utilisée dans `recap_mise_en_place_git_docker.md` section 4) tournait en fait toujours en arrière-plan sur la machine et occupait le port `5432`. SQLTools se connectait donc silencieusement à ce serveur local au lieu du conteneur Docker `foot-predictor-dev`, d'où des erreurs `password authentication failed` malgré des identifiants corrects.

**Diagnostic clé** : arrêter le conteneur Docker supposé cible. Si l'erreur reste une erreur Postgres (`password authentication failed`) plutôt que `connection refused`, un autre serveur répond sur ce port.

**Résolution** : mapping du port dev changé dans `docker-compose.yml` :
```yaml
services:
  postgres_dev:
    ports:
      - 5440:5432   # anciennement 5432:5432
```

**Impact à retenir** :
- `.env.dev` → `POSTGRES_PORT=5440` (au lieu de 5432)
- Connexion SQLTools dev → port `5440`
- Le port `5433` (test) n'est pas concerné, aucun conflit détecté dessus.
- Recommandé mais non obligatoire : désactiver le service Windows PostgreSQL natif (`services.msc` → `postgresql-x64-XX` → Désactivé) pour éviter que ce conflit ne resurgisse sur un futur projet.

*(Tableau de la section 4 de `recap_mise_en_place_git_docker.md` à mettre à jour avec ce nouveau port.)*

## 3. Autres incidents rencontrés (pour référence future)

| Incident | Cause | Correction |
|---|---|---|
| `password authentication failed` persistant après reset du volume Docker | Le volume `pg_dev_data` n'était pas réellement supprimé avant `docker compose up` (conteneur pas arrêté ou pas supprimé au préalable) | Toujours faire `stop` → `rm -f` → `volume rm` → `up`, dans cet ordre, et vérifier via `docker logs` la présence de `running bootstrap script` pour confirmer une vraie réinitialisation |
| Connexion SQLTools créée mais invisible / erreur `Received null` sur le mot de passe | Connexions résiduelles dans les settings VSCode (user **et** workspace) + credentials mis en cache dans le Gestionnaire d'identifiants Windows | Vider `sqltools.connections` dans les deux fichiers de settings (`Ctrl+Shift+P` → *Preferences: Open User Settings (JSON)* **et** `.vscode/settings.json` du workspace) + nettoyer le Gestionnaire d'identifiants Windows + `Developer: Reload Window` |
| `uv add` → `error: Project is missing a [project] table` | `pyproject.toml` existait mais était vide | `rm pyproject.toml` puis `uv init --no-readme` |
| `uv run alembic init migrations` → `Directory already exists` | Dossier `migrations/versions/` déjà présent (vide) depuis la structure initiale du projet | Déplacer temporairement `versions/` **hors** de `migrations/`, lancer `alembic init`, puis remettre `versions/` à sa place en écrasant le dossier vide généré |
| `ModuleNotFoundError: No module named 'foot_predictor'` lors d'`alembic upgrade head` | `prepend_sys_path` dans `alembic.ini` pointait sur `.` (racine) au lieu de `src` (où vit le package) | `prepend_sys_path = src` dans `alembic.ini`, + vérifier la présence de `src/foot_predictor/__init__.py` |
| `pydantic_core.ValidationError: postgres_user Field required` alors que la variable est bien présente dans `.env.dev` | Fichier `.env.dev` sauvegardé en encodage **UTF-8 with BOM** (ajouté par certains éditeurs Windows) — le BOM corrompt le nom de la toute première variable du fichier | Dans VSCode : ré-enregistrer le fichier en **UTF-8** (sans BOM) via le sélecteur d'encodage en bas à droite. Fait sur `.env.dev`, `.env.test`, `.env.prod` par précaution |

## 4. Fichiers modifiés / créés durant cette étape

- `docker-compose.yml` — port dev changé en `5440:5432`
- `.env.dev`, `.env.test`, `.env.prod` — ré-encodés en UTF-8 sans BOM ; `.env.dev` avec `POSTGRES_PORT=5440`
- `pyproject.toml` — recréé proprement via `uv init --no-readme`
- `src/foot_predictor/__init__.py` — créé (vide)
- `src/foot_predictor/config.py` — config pydantic-settings, bascule via `APP_ENV`
- `alembic.ini` — `sqlalchemy.url` vide (injecté dynamiquement), `prepend_sys_path = src`
- `migrations/env.py` — lit la config via `foot_predictor.config`, `target_metadata = None` en attendant l'étape 2
- `migrations/versions/0001_create_schemas.py` — première migration : crée `raw`, `staging`, `features`

## 5. Checklist étape 1 — complète ✅

- [x] Compte + projet Neon créés (Neon Auth non activé, pas de besoin identifié)
- [x] `.env.prod` renseigné avec `sslmode=require`, connexion directe (non-pooled)
- [x] Connexions SQLTools opérationnelles pour dev, test, prod
- [x] `uv` installé, dépendances ajoutées (`sqlalchemy`, `alembic`, `psycopg[binary]`, `pydantic-settings`)
- [x] Alembic configuré et branché sur `.env.{APP_ENV}`
- [x] Migration `0001_create_schemas` appliquée avec succès sur dev, test et prod
- [x] Schémas `raw`/`staging`/`features` vérifiés dans les 3 bases

## 6. À faire avant de passer à l'étape 2 (optionnel, hygiène de projet)

- [ ] Désactiver le service Windows PostgreSQL natif qui occupait le port 5432
- [ ] Mettre à jour `.env.example` avec les nouvelles variables (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_SSLMODE`)
- [ ] Mettre à jour le tableau de la section 4 de `recap_mise_en_place_git_docker.md` avec le port `5440`
- [ ] Commit + push (`git add . && git commit -m "Infra: Alembic + schémas raw/staging/features sur dev/test/prod"`)

---

## Prochaine étape du projet

**Étape 2 — Détail des tables par schéma** (`raw`, `staging`, `features`) : colonnes, types, clés primaires/étrangères, en s'appuyant sur les données listées en section 4 de `recap_decisions_projet.md` (calendrier, compositions, indicateur de stabilité, valeur marchande, âge, classement, forme récente, buts, xG).

---

*Document généré à partir de l'échange avec Claude — à intégrer à la suite de `recap_mise_en_place_git_docker.md`.*
