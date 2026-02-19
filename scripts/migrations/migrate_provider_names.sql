-- Migration: Fix legacy provider names in discovered_issues table
-- This fixes old records where provider name ('IA') was stored instead of type ('internet_archive')

-- Check how many records need fixing
SELECT 'Records to update:', COUNT(*) 
FROM discovered_issues 
WHERE latest_provider IN ('IA', 'Internet Archive')
  AND latest_provider != 'internet_archive';

-- Update IA provider names to correct type
UPDATE discovered_issues 
SET latest_provider = 'internet_archive' 
WHERE latest_provider IN ('IA', 'Internet Archive')
  AND latest_provider != 'internet_archive';

-- Verify the update
SELECT 'Records updated. Current provider distribution:';
SELECT latest_provider, COUNT(*) as count
FROM discovered_issues 
WHERE latest_provider IS NOT NULL
GROUP BY latest_provider
ORDER BY count DESC;
