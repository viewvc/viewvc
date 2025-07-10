-- ViewVC Database Migration: Schema Version 1 to 2

-- Convert branches table to InnoDB with UTF-8
ALTER TABLE branches 
    ENGINE=InnoDB,
    MODIFY COLUMN branch varchar(64) CHARACTER SET utf8 COLLATE utf8_bin DEFAULT '' NOT NULL;

-- Convert commits table to InnoDB with UTF-8
ALTER TABLE commits 
    ENGINE=InnoDB,
    MODIFY COLUMN revision varchar(32) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL DEFAULT '',
    MODIFY COLUMN stickytag varchar(255) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL DEFAULT '';

-- Convert descs table to InnoDB with UTF-8
ALTER TABLE descs 
    ENGINE=InnoDB,
    MODIFY COLUMN description text CHARACTER SET utf8 COLLATE utf8_bin;

-- Convert dirs table to InnoDB with UTF-8
ALTER TABLE dirs 
    ENGINE=InnoDB,
    MODIFY COLUMN dir varchar(255) CHARACTER SET utf8 COLLATE utf8_bin DEFAULT '' NOT NULL;

-- Convert files table to InnoDB with UTF-8
ALTER TABLE files 
    ENGINE=InnoDB,
    MODIFY COLUMN file varchar(255) CHARACTER SET utf8 COLLATE utf8_bin DEFAULT '' NOT NULL;

-- Convert people table to InnoDB with UTF-8
ALTER TABLE people 
    ENGINE=InnoDB,
    MODIFY COLUMN who varchar(128) CHARACTER SET utf8 COLLATE utf8_bin DEFAULT '' NOT NULL;

-- Convert repositories table to InnoDB with UTF-8
ALTER TABLE repositories 
    ENGINE=InnoDB,
    MODIFY COLUMN repository varchar(64) CHARACTER SET utf8 COLLATE utf8_bin DEFAULT '' NOT NULL;

-- Convert tags table to InnoDB with UTF-8
ALTER TABLE tags 
    ENGINE=InnoDB,
    MODIFY COLUMN revision varchar(32) CHARACTER SET utf8 COLLATE utf8_bin DEFAULT '' NOT NULL;

-- Convert metadata table to InnoDB with UTF-8
ALTER TABLE metadata 
    ENGINE=InnoDB,
    MODIFY COLUMN name varchar(255) CHARACTER SET utf8 COLLATE utf8_bin DEFAULT '' NOT NULL,
    MODIFY COLUMN value text CHARACTER SET utf8 COLLATE utf8_bin;

-- Update schema version to 2
UPDATE metadata SET value = '2' WHERE name = 'version';
