-- ViewVC Database Migration: Schema Version 0 to 1

-- Create metadata table to track schema version
CREATE TABLE metadata (
    name varchar(255) binary DEFAULT '' NOT NULL,
    value text,
    PRIMARY KEY (name),
    UNIQUE name (name)
) ENGINE=MyISAM;

-- Insert initial version marker
INSERT INTO metadata (name, value) VALUES ('version', '1');

-- Rename checkins table to commits
RENAME TABLE checkins TO commits;

-- Add descid index to commits table for better query performance
ALTER TABLE commits ADD INDEX descid (descid);
