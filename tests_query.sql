SELECT id, name FROM staging.team
WHERE id NOT BETWEEN 97 AND 103
  AND (
    name ILIKE '%bilbao%' OR name ILIKE '%betis%' OR name ILIKE '%celta%'
    OR name ILIKE '%sociedad%' OR name ILIKE '%vallecano%' OR name ILIKE '%valladolid%'
    OR name ILIKE '%atl%madrid%' OR name ILIKE '%atletico%'
  )
ORDER BY id;