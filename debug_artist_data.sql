-- Debug script to check if auto-match data is being saved
-- Run this in your database to check the current state of artist data

-- Find artists with the name "Ren" (or similar)
SELECT 
    id,
    name,
    spotify_id,
    lastfm_name,
    imvdb_id,
    imvdb_metadata,
    updated_at
FROM artists 
WHERE name LIKE '%Ren%' 
   OR name LIKE '%ren%'
LIMIT 5;

-- Check specific keys in imvdb_metadata JSON
SELECT 
    id,
    name,
    JSON_EXTRACT(imvdb_metadata, '$.musicbrainz_id') as musicbrainz_id,
    JSON_EXTRACT(imvdb_metadata, '$.allmusic_id') as allmusic_id,
    JSON_EXTRACT(imvdb_metadata, '$.wikipedia_page') as wikipedia_page,
    updated_at
FROM artists 
WHERE name LIKE '%Ren%' 
   OR name LIKE '%ren%'
LIMIT 5;