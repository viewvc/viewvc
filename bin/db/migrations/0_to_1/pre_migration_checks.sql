-- Pre-migration checks for schema 0 to 1 upgrade
-- These queries verify the database is in a valid state before migration

-- Ensure checkins table exists and has data
SELECT COUNT(*) FROM checkins;

-- Verify expected schema 0 table structure
SHOW TABLES LIKE 'checkins';
SHOW TABLES LIKE 'branches';
SHOW TABLES LIKE 'dirs';
SHOW TABLES LIKE 'files';
SHOW TABLES LIKE 'people';
SHOW TABLES LIKE 'repositories';
