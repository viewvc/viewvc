DROP TABLE IF EXISTS branches;
CREATE TABLE branches (
  id mediumint(9) NOT NULL auto_increment,
  branch varchar(64) DEFAULT '' NOT NULL,
  PRIMARY KEY (id),
  UNIQUE branch (branch)
) ENGINE=InnoDB ROW_FORMAT DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

DROP TABLE IF EXISTS commits;
CREATE TABLE commits (
  type enum('Change','Add','Remove') DEFAULT NULL,
  ci_when datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  whoid mediumint(9) NOT NULL DEFAULT 0,
  repositoryid mediumint(9) NOT NULL DEFAULT 0,
  dirid mediumint(9) NOT NULL DEFAULT 0,
  fileid mediumint(9) NOT NULL DEFAULT 0,
  revision varchar(32) NOT NULL DEFAULT '',
  stickytag varchar(255) NOT NULL DEFAULT '',
  branchid mediumint(9) NOT NULL DEFAULT 0,
  addedlines int(11) NOT NULL DEFAULT 0,
  removedlines int(11) NOT NULL DEFAULT 0,
  descid mediumint(9) DEFAULT NULL,
  UNIQUE KEY repositoryid (repositoryid,dirid,fileid,revision),
  KEY ci_when (ci_when),
  KEY whoid (whoid),
  KEY repositoryid_2 (repositoryid),
  KEY dirid (dirid),
  KEY fileid (fileid),
  KEY branchid (branchid),
  KEY descid (descid)
) ENGINE=InnoDB ROW_FORMAT DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

DROP TABLE IF EXISTS descs;
CREATE TABLE descs (
  id mediumint(9) NOT NULL auto_increment,
  description text,
  hash bigint(20) DEFAULT '0' NOT NULL,
  PRIMARY KEY (id),
  KEY hash (hash)
) ENGINE=InnoDB ROW_FORMAT DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

DROP TABLE IF EXISTS dirs;
CREATE TABLE dirs (
  id mediumint(9) NOT NULL auto_increment,
  dir varchar(255) DEFAULT '' NOT NULL,
  PRIMARY KEY (id),
  UNIQUE dir (dir)
) ENGINE=InnoDB ROW_FORMAT DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

DROP TABLE IF EXISTS files;
CREATE TABLE files (
  id mediumint(9) NOT NULL auto_increment,
  file varchar(255) DEFAULT '' NOT NULL,
  PRIMARY KEY (id),
  UNIQUE file (file)
) ENGINE=InnoDB ROW_FORMAT DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

DROP TABLE IF EXISTS people;
CREATE TABLE people (
  id mediumint(9) NOT NULL auto_increment,
  who varchar(128) DEFAULT '' NOT NULL,
  PRIMARY KEY (id),
  UNIQUE who (who)
) ENGINE=InnoDB ROW_FORMAT DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

DROP TABLE IF EXISTS repositories;
CREATE TABLE repositories (
  id mediumint(9) NOT NULL auto_increment,
  repository varchar(64) DEFAULT '' NOT NULL,
  PRIMARY KEY (id),
  UNIQUE repository (repository)
) ENGINE=InnoDB ROW_FORMAT DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

DROP TABLE IF EXISTS tags;
CREATE TABLE tags (
  repositoryid mediumint(9) DEFAULT '0' NOT NULL,
  branchid mediumint(9) DEFAULT '0' NOT NULL,
  dirid mediumint(9) DEFAULT '0' NOT NULL,
  fileid mediumint(9) DEFAULT '0' NOT NULL,
  revision varchar(32) DEFAULT '' NOT NULL,
  UNIQUE repositoryid (repositoryid,dirid,fileid,branchid,revision),
  KEY repositoryid_2 (repositoryid),
  KEY dirid (dirid),
  KEY fileid (fileid),
  KEY branchid (branchid)
) ENGINE=InnoDB ROW_FORMAT DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

DROP TABLE IF EXISTS metadata;
CREATE TABLE metadata (
  name varchar(255) DEFAULT '' NOT NULL,
  value text,
  PRIMARY KEY (name),
  UNIQUE name (name)
) ENGINE=InnoDB ROW_FORMAT DYNAMIC DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO metadata (name, value) VALUES ('version', '2');
