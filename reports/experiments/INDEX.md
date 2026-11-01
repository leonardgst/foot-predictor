# Index des expériences (généré)

Généré par `python -m foot_predictor.modeling evaluate` (ou `index`). **Tous les essais sont conservés**, y compris ceux qui échouent : leur nombre aide à se méfier des comparaisons multiples.

**14 essai(s)**, dont 0 en échec.

| Date (UTC) | Identifiant | Statut | Modèles | Première comparaison (log-loss du total, A − B, poolée) |
|---|---|---|---|---|
| 2026-09-30T08:06:11+00:00 | `references-mesure-duree-20260930T080611` | ok | B0, B1, marche_avant_cloture, marche_cloture | B0 − B1 : +0.0046 [+0.0014 ; +0.0080] |
| 2026-09-30T08:06:23+00:00 | `references-20260930T080623` | ok | B0, B1, marche_avant_cloture, marche_cloture | B0 − B1 : +0.0046 [+0.0010 ; +0.0080] |
| 2026-09-30T08:38:47+00:00 | `m1-m2-20260930T083847` | ok | B1, M1, M2 | B1 − M1 : -0.0108 [-0.0166 ; -0.0049] |
| 2026-09-30T08:46:58+00:00 | `m3-20260930T084658` | ok | B1, M2, M3 | B1 − M3 : +0.0087 [+0.0048 ; +0.0126] |
| 2026-09-30T08:53:37+00:00 | `m5-20260930T085337` | ok | M3, M5 | M3 − M5 : +0.0000 [-0.0009 ; +0.0010] |
| 2026-09-30T09:01:47+00:00 | `m6-mesure-duree-20260930T090147` | ok | M3, M3_G0G3, M6_ridge, M6_en | M3 − M6_ridge : +0.0084 [-0.0004 ; +0.0152] |
| 2026-09-30T09:07:47+00:00 | `m6-20260930T090747` | ok | M3, M3_G0G3, M6_ridge, M6_en | M3 − M6_ridge : +0.0093 [+0.0061 ; +0.0125] |
| 2026-09-30T11:03:52+00:00 | `ablations-20260930T110352` | ok | B0, B1, A0_G0, A1_G0G1, A2_G0G2, A3_G0G3 | B0 − A0_G0 : +0.0039 [+0.0019 ; +0.0059] |
| 2026-09-30T12:09:45+00:00 | `population-20260930T120945` | ok | A2_top5, A2_top5_d2 | A2_top5 − A2_top5_d2 : +0.0003 [-0.0003 ; +0.0010] |
| 2026-10-22T12:05:42+00:00 | `scelle-h1-20261022T120542` | ok | M3_G0G2, B0, B1, marche_avant_cloture, marche_cloture | B1 − M3_G0G2 : +0.0189 [+0.0102 ; +0.0282] |
| 2026-11-01T12:30:30+00:00 | `ablations-h2-mesure-duree-20261101T123030` | ok | A2_G0G2, G6, G5, G4, G6_G5, G6_G4, G5_G4, G6_G5_G4, A2_depuis_2016, A2_depuis_2017 | A2_G0G2 − G6 : +0.0003 [-0.0002 ; +0.0010] |
| 2026-11-01T12:32:12+00:00 | `ablations-h2-20261101T123212` | ok | A2_G0G2, G6, G5, G4, G6_G5, G6_G4, G5_G4, G6_G5_G4, A2_depuis_2016, A2_depuis_2017 | A2_G0G2 − G6 : +0.0003 [-0.0002 ; +0.0009] |
| 2026-11-01T12:34:36+00:00 | `ablations-h2-20261101T123436` | ok | A2_G0G2, G6, G5, G4, G6_G5, G6_G4, G5_G4, G6_G5_G4, A2_depuis_2016, A2_depuis_2017 | A2_G0G2 − G6 : +0.0003 [-0.0002 ; +0.0009] |
| 2026-11-01T12:36:24+00:00 | `stabilite-h2-20261101T123624` | ok | A2_G0G2, V_h3, V_h5, V_h10, V_h20, V_hinf, V_reset, V_win10, V_overlap | A2_G0G2 − V_h3 : +0.0003 [-0.0004 ; +0.0010] |
