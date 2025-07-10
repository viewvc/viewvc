-- Pre-migration checks for schema 1 to 2 upgrade
-- These queries verify the database is in a valid state before migration

-- Ensure commits table exists and has data
SELECT COUNT(*) FROM commits;

-- Verify metadata table exists and shows version 1
SELECT value FROM metadata WHERE name = 'version';

-- Check current table engines (should be MyISAM)
SHOW TABLE STATUS WHERE Name IN ('commits', 'branches', 'descs', 'dirs', 'files', 'people', 'repositories', 'metadata');

-- Verify all expected schema 1 tables exist
SHOW TABLES LIKE 'commits';
SHOW TABLES LIKE 'metadata';
SHOW TABLES LIKE 'branches';
SHOW TABLES LIKE 'descs';
SHOW TABLES LIKE 'dirs';
SHOW TABLES LIKE 'files';
SHOW TABLES LIKE 'people';
SHOW TABLES LIKE 'repositories';
SHOW TABLES LIKE 'tags';
