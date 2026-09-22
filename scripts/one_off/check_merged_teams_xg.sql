SELECT t.name,
       COUNT(*) AS nb_team_match,
       COUNT(tm.xg_for) AS nb_avec_xg
FROM staging.team_match tm
JOIN staging.team t ON t.id = tm.team_id
WHERE t.name IN ('Athletic Club','Atletico Madrid','Parma Calcio 1913','Hellas Verona',
                 'Celta Vigo','Rayo Vallecano','Real Betis','Real Sociedad','Real Valladolid',
                 'Bayer Leverkusen','Borussia Dortmund','Borussia Monchengladbach',
                 'Eintracht Frankfurt','FSV Mainz 05','VfB Stuttgart','1899 Hoffenheim',
                 'VfL Bochum','VfL Wolfsburg','Stade Brestois 29')
GROUP BY t.name
ORDER BY nb_avec_xg;