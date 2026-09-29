# ADR-0033 — Calendrier (G3) rétrospectif avec indicateur de fiabilité ; huis clos (G0) par périodes sourcées

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : rapport de cadrage, I.3 (G0, G3), I.5 (régimes particuliers) ; ADR-0010, ADR-0011 (G3 en rejeu seulement), ADR-0012 (huis clos dans les plis) ; décisions d.4, d.10c et d.10e de la partie 3 ; mesure 4 de l'étape 0

## Contexte

**Calendrier.** Le repos et la charge récente dépendent des coupes. Or elles ne sont dans `staging` **qu'à partir de 2015-16** : coupes nationales d'Angleterre, d'Allemagne et de France, et coupes d'Europe, depuis 2015-16 ; Coppa Italia depuis 2016-17 ; Copa del Rey depuis 2018-19. Supercoupes et Coupe du monde des clubs : jamais. Avant, seuls les matchs de championnat sont connus. Après l'abonnement, aucune source gratuite ne couvre les coupes (ADR-0011).

**Huis clos.** Les matchs sans public de 2020-21 (et de la fin de 2019-20) sont un régime particulier à traiter dans tous les plis (ADR-0012). Aucune donnée du projet ne le dit : il faut des sources publiques datées.

## Options envisagées

- Calendrier :
  1. Repos calculé sur le seul championnat : homogène, mais faux dès qu'une équipe joue une coupe.
  2. Repos toutes compétitions présentes, sans indicateur : faux avant 2015-16, sans que le modèle le sache.
  3. Repos toutes compétitions présentes, **avec un indicateur de fiabilité** par pays et par saison.
- Huis clos :
  1. Indicateur deviné (« 2020-21 = huis clos ») : faux pour les jauges partielles et selon les pays.
  2. **Périodes par championnat**, chacune avec sa source, et `incertain` quand la source manque.
  3. Reporter l'indicateur à la partie 4.

## Décision

Calendrier : option 3. Huis clos : option 2.

- `features/rest.py` : `rest_days`, `matches_last_14d`, `european_match_last_4d`, sur les matchs **terminés avant le jour J**, toutes compétitions présentes dans `staging`.
  - **Rétrospectif seulement** : la date du prochain match n'est jamais utilisée (reports, incertitude).
  - `rest_reliable` est vrai à partir de la première saison où toutes les coupes du pays sont chargées : Angleterre, Allemagne, France en 2015-16 ; Italie en 2016-17 ; Espagne en 2018-19 (d.10c). Les valeurs sont calculées même quand l'indicateur est faux : elles sous-estiment alors la charge, et l'indicateur le dit.
  - G3 est « rejeu seulement » (ADR-0011) : `disponible_en_live: non` au registre.
- `features/huis_clos.yaml` et `huis_clos.py` : périodes par championnat, bornes incluses, chacune avec sa source (lue le 2026-09-29).
  - `huis_clos` vaut 1 ; `jauge_reduite` vaut 0 (période gardée pour la partie 4) ; `incertain` vaut 0 et l'emporte sur une période sûre qui la recouvre : on ne devine pas (d.10e).
  - Pour 2019-20, une période commence à la suspension de mars 2020 : aucun match n'a eu lieu entre la suspension et la reprise, qui s'est faite partout à huis clos. Les dates exactes de reprise sont donc inutiles.

## Conséquences

- Périodes sûres : Angleterre du 13/03/2020 au 01/12/2020, puis du 04/01/2021 au 17/05/2021 ; Allemagne du 11/03/2020 au 11/07/2020, puis du 02/11/2020 au 21/05/2021 ; Italie du 05/03/2020 au 31/08/2020, puis du 26/10/2020 au 16/05/2021 ; Espagne du 12/03/2020 au 15/05/2021 ; France du 30/10/2020 au 18/05/2021, plus les barrages de fin mai 2021. **4 128 matchs** des 10 championnats (de 293 en Ligue 1 à 562 en Championship).
- Périodes `incertain`, signalées au retour :
  - Angleterre, décembre 2020 (paliers régionaux, selon le club) ;
  - Championship, 19/09/2020 (deux matchs pilotes) ;
  - fins de saison 2020-21 en Allemagne, en Italie, en Espagne et en France (retours partiels du public) ;
  - Allemagne, du 28/12/2021 au 28/02/2022 (huis clos national, mais public admis à Berlin).
- Les jauges réduites (automne 2020 en France, en Allemagne et en Italie ; mai 2021 en Angleterre) valent 0. Leur effet éventuel est une question de la partie 4.
- Part des lignes à repos fiable : 0 % avant 2015-16 ; 58 % en 2015-16 ; 79 % en 2016-17 et 2017-18 ; 100 % à partir de 2018-19.
- **Critère de révision** : une source gratuite des coupes utilisable en live (G3 disponible en live), ou une source qui lève une période `incertain`.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
