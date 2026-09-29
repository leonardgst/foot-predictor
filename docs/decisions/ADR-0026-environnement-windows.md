# ADR-0026 — Environnement : Windows natif et Git Bash ; WSL2 étudié après le gel

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : rapport de cadrage, A.4, C.4, décision M13 ; décision d.2 de la session « partie 2 » du 2026-09-29

## Contexte

Le rapport (M13) recommande WSL2, mais **après** le gel des données : ne pas changer d'environnement pendant la collecte. Plusieurs incidents passés sont propres à Windows (BOM des `.env`, E-002 ; port 5432, E-001 ; chemins transformés par Git Bash ; `\t` interprétés, E-029).

Machine mesurée le 2026-09-29 : Windows 11 Famille 10.0.26200, Intel i7-1255U, **15,7 Go de RAM**, 726 Go libres sur C: et 884 Go sur le disque externe D:. WSL2 est déjà installé (Ubuntu, version 2) : Docker Desktop s'en sert.

Jusqu'au gel du 19 octobre, neuf tâches planifiées Windows (`schtasks`) font tourner la collecte dans `C:/foot-predictor` (ADR-0018).

## Options envisagées

1. **Windows natif, terminal Git Bash** : rien à changer ; frictions connues et documentées.
2. **WSL2 (Ubuntu)** : environ 2 heures de mise en place ; `cron` natif ; mais un second environnement à tenir pendant la collecte, et des chemins différents.

## Décision

Option 1 pendant toute la partie 2. WSL2 sera étudié dans un **mini-jalon après le gel**, sans effet sur le code de cette partie :

- aucun chemin écrit en dur : brut, bruts externes, dossiers de sortie et bases passent par des options (`--raw-dir`, `--external-raw-dir`, `--output-dir`) ou par `.env.{APP_ENV}` ;
- les commandes de la documentation sont écrites pour Git Bash (`//` devant les options Windows, apostrophes autour des chemins à antislash) ;
- le contrôle pre-commit des caractères de contrôle (E-029) protège contre la famille d'erreurs la plus coûteuse.

## Conséquences

- Tâches planifiées Windows jusqu'au gel ; au-delà, l'orchestration (décision M22) pourra choisir `cron` sous WSL2.
- **Critère de révision** : un second incident propre à Windows qui coûte plus d'une heure, ou le besoin d'une planification régulière après le gel (collecteur football-data en live, ADR-0011).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
