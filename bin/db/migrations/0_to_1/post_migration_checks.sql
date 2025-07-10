-- Post-migration checks for schema 0 to 1 upgrade
-- These queries verify the migration completed successfully

-- Ensure commits table exists and has same data count as original checkins
SELECT COUNT(*) FROM commits;

-- Verify metadata table exists and has correct version
SELECT value FROM metadata WHERE name = 'version';

-- Verify the new descid index was created
SHOW INDEX FROM commits WHERE Key_name = 'descid';

-- Ensure all expected tables still exist
SHOW TABLES LIKE 'commits';
SHOW TABLES LIKE 'metadata';
SHOW TABLES LIKE 'branches';
SHOW TABLES LIKE 'dirs';
SHOW TABLES LIKE 'files';
SHOW TABLES LIKE 'people';
SHOW TABLES LIKE 'repositories';
