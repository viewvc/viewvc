-- Post-migration checks for schema 1 to 2 upgrade
-- These queries verify the migration completed successfully

-- Ensure commits table still has same data count
SELECT COUNT(*) FROM commits;

-- Verify metadata table shows version 2
SELECT value FROM metadata WHERE name = 'version';

-- Check that all tables are now InnoDB and UTF-8
SHOW TABLE STATUS WHERE Name IN ('commits', 'branches', 'descs', 'dirs', 'files', 'people', 'repositories', 'metadata', 'tags');

-- Verify UTF-8 character set on key columns
SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_SCHEMA = DATABASE() 
AND TABLE_NAME IN ('commits', 'branches', 'dirs', 'files', 'people', 'repositories', 'metadata')
AND CHARACTER_SET_NAME IS NOT NULL
ORDER BY TABLE_NAME, COLUMN_NAME;

-- Ensure all expected tables still exist after conversion
SHOW TABLES LIKE 'commits';
SHOW TABLES LIKE 'metadata';
SHOW TABLES LIKE 'branches';
SHOW TABLES LIKE 'descs';
SHOW TABLES LIKE 'dirs';
SHOW TABLES LIKE 'files';
SHOW TABLES LIKE 'people';
SHOW TABLES LIKE 'repositories';
SHOW TABLES LIKE 'tags';
