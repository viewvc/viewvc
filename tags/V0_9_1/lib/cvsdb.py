# -*- Mode: python -*-
#
# Copyright (C) 2000 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://www.lyra.org/viewcvs/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://www.lyra.org/viewcvs/
#
# -----------------------------------------------------------------------
#

#########################################################################
#
# INSTALL-TIME CONFIGURATION
#
# These values will be set during the installation process. During
# development, they will remain None.
#

CONF_PATHNAME = None

#########################################################################

import os
import sys
import string
import time

import config
import dbi
import rlog


## load configuration file, the data is used globally here
if CONF_PATHNAME:
  _cfg_pathname = CONF_PATHNAME
else:
  # developer assistance: running from a CVS working copy
  _cfg_pathname = os.path.join(os.path.dirname(__file__), os.pardir, 'cgi',
                               'viewcvs.conf')
cfg = config.Config()
cfg.set_defaults()
cfg.load_config(_cfg_pathname)

## error
error = "cvsdb error"

## cached (active) database connections
gCheckinDatabase = None
gCheckinDatabaseReadOnly = None


## CheckinDatabase provides all interfaces needed to the SQL database
## back-end; it needs to be subclassed, and have its "Connect" method
## defined to actually be complete; it should run well off of any DBI 2.0
## complient database interface

class CheckinDatabase:
    def __init__(self, host, user, passwd, database):
        self._host = host
        self._user = user
        self._passwd = passwd
        self._database = database

        ## database lookup caches
        self._get_cache = {}
        self._get_id_cache = {}
        self._desc_id_cache = {}

    def Connect(self):
        self.db = dbi.connect(
            self._host, self._user, self._passwd, self._database)

    def sql_get_id(self, table, column, value, auto_set):
        sql = "SELECT id FROM %s WHERE %s=%%s" % (table, column)
        sql_args = (value, )
        
        cursor = self.db.cursor()
        cursor.execute(sql, sql_args)
        try:
            (id, ) = cursor.fetchone()
        except TypeError:
            if not auto_set:
                return None
        else:
            return str(int(id))
   
        ## insert the new identifier
        sql = "INSERT INTO %s(%s) VALUES(%%s)" % (table, column)
        sql_args = (value, )
        cursor.execute(sql, sql_args)

        return self.sql_get_id(table, column, value, 0)

    def get_id(self, table, column, value, auto_set):
        ## attempt to retrieve from cache
        try:
            return self._get_id_cache[table][column][value]
        except KeyError:
            pass

        id = self.sql_get_id(table, column, value, auto_set)
        if id == None:
            return None

        ## add to cache
        try:
            temp = self._get_id_cache[table]
        except KeyError:
            temp = self._get_id_cache[table] = {}

        try:
            temp2 = temp[column]
        except KeyError:
            temp2 = temp[column] = {}

        temp2[value] = id
        return id

    def sql_get(self, table, column, id):
        sql = "SELECT %s FROM %s WHERE id=%%s" % (column, table)
        sql_args = (id, )

        cursor = self.db.cursor()
        cursor.execute(sql, sql_args)
        try:
            (value, ) = cursor.fetchone()
        except TypeError:
            return None

        return value

    def get(self, table, column, id):
        ## attempt to retrieve from cache
        try:
            return self._get_cache[table][column][id]
        except KeyError:
            pass

        value = self.sql_get(table, column, id)
        if value == None:
            return None

        ## add to cache
        try:
            temp = self._get_cache[table]
        except KeyError:
            temp = self._get_cache[table] = {}

        try:
            temp2 = temp[column]
        except KeyError:
            temp2 = temp[column] = {}

        temp2[id] = value
        return value
        
    def get_list(self, table, field_index):
        sql = "SELECT * FROM %s" % (table)
        cursor = self.db.cursor()
        cursor.execute(sql)

        list = []
        while 1:
            row = cursor.fetchone()
            if row == None:
                break
            list.append(row[field_index])

        return list

    def GetBranchID(self, branch, auto_set = 1):
        return self.get_id("branches", "branch", branch, auto_set)

    def GetBranch(self, id):
        return self.get("branches", "branch", id)

    def GetDirectoryID(self, dir, auto_set = 1):
        return self.get_id("dirs", "dir", dir, auto_set)

    def GetDirectory(self, id):
        return self.get("dirs", "dir", id)

    def GetFileID(self, file, auto_set = 1):
        return self.get_id("files", "file", file, auto_set)

    def GetFile(self, id):
        return self.get("files", "file", id)
    
    def GetAuthorID(self, author, auto_set = 1):
        return self.get_id("people", "who", author, auto_set)

    def GetAuthor(self, id):
        return self.get("people", "who", id)
    
    def GetRepositoryID(self, repository, auto_set = 1):
        return self.get_id("repositories", "repository", repository, auto_set)

    def GetRepository(self, id):
        return self.get("repositories", "repository", id)

    def SQLGetDescriptionID(self, description, auto_set = 1):
        ## lame string hash, blame Netscape -JMP
        hash = len(description)

        sql = "SELECT id FROM descs WHERE hash=%s AND description=%s"
        sql_args = (hash, description)
        
        cursor = self.db.cursor()
        cursor.execute(sql, sql_args)
        try:
            (id, ) = cursor.fetchone()
        except TypeError:
            if not auto_set:
                return None
        else:
            return str(int(id))

        sql = "INSERT INTO descs (hash,description) values (%s,%s)"
        sql_args = (hash, description)
        cursor.execute(sql, sql_args)
        
        return self.GetDescriptionID(description, 0)

    def GetDescriptionID(self, description, auto_set = 1):
        ## attempt to retrieve from cache
        hash = len(description)
        try:
            return self._desc_id_cache[hash][description]
        except KeyError:
            pass

        id = self.SQLGetDescriptionID(description, auto_set)
        if id == None:
            return None

        ## add to cache
        try:
            temp = self._desc_id_cache[hash]
        except KeyError:
            temp = self._desc_id_cache[hash] = {}

        temp[description] = id
        return id

    def GetDescription(self, id):
        return self.get("descs", "description", id)

    def GetRepositoryList(self):
        return self.get_list("repositories", 1)

    def GetBranchList(self):
        return self.get_list("branches", 1)

    def GetAuthorList(self):
        return self.get_list("people", 1)

    def AddCommitList(self, commit_list):
        for commit in commit_list:
            self.AddCommit(commit)

    def AddCommit(self, commit):
        ## MORE TIME HELL: the MySQLdb module doesn't construct times
        ## correctly when created with TimestampFromTicks -- it doesn't
        ## account for daylight savings time, so we use Python's time
        ## module to do the conversion
        temp = time.localtime(commit.GetTime())
        ci_when = dbi.Timestamp(
            temp[0], temp[1], temp[2], temp[3], temp[4], temp[5])

        ci_type = commit.GetTypeString()
        who_id = self.GetAuthorID(commit.GetAuthor())
        repository_id = self.GetRepositoryID(commit.GetRepository())
        directory_id = self.GetDirectoryID(commit.GetDirectory())
        file_id = self.GetFileID(commit.GetFile())
        revision = commit.GetRevision()
        sticky_tag = "NULL"
        branch_id = self.GetBranchID(commit.GetBranch())
        plus_count = commit.GetPlusCount()
        minus_count = commit.GetMinusCount()
        description_id = self.GetDescriptionID(commit.GetDescription())

        sql = "REPLACE INTO checkins"\
              "  (type,ci_when,whoid,repositoryid,dirid,fileid,revision,"\
              "   stickytag,branchid,addedlines,removedlines,descid)"\
              "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        sql_args = (ci_type, ci_when, who_id, repository_id,
                    directory_id, file_id, revision, sticky_tag, branch_id,
                    plus_count, minus_count, description_id)

        cursor = self.db.cursor()
        cursor.execute(sql, sql_args)

    def SQLQueryListString(self, sqlString, query_entry_list):
        sqlList = []

        for query_entry in query_entry_list:
            ## figure out the correct match type
            if query_entry.match == "exact":
                match = "="
            elif query_entry.match == "like":
                match = " LIKE "
            elif query_entry.match == "regex":
                match = " REGEXP "

            sqlList.append(sqlString % (match, query_entry.data))

        return "(%s)" % (string.join(sqlList, " OR "))

    def CreateSQLQueryString(self, query):
        tableList = ["checkins"]
        condList = []

        ## XXX: this is to exclude .ver files -- RN specific hack --JMP
        tableList.append("files")
        temp = "(checkins.fileid=files.id AND files.file NOT LIKE \"%.ver\")"
        condList.append(temp)
        ## XXX

        if len(query.repository_list):
            tableList.append("repositories")

            sql = "(checkins.repositoryid=repositories.id AND "\
                  "repositories.repository%s\"%s\")"
            temp = self.SQLQueryListString(sql, query.repository_list)
            condList.append(temp)

        if len(query.branch_list):
            tableList.append("branches")

            sql = "(checkins.branchid=branches.id AND "\
                  "branches.branch%s\"%s\")"
            temp = self.SQLQueryListString(sql, query.branch_list)
            condList.append(temp)

        if len(query.directory_list):
            tableList.append("dirs")

            sql = "(checkins.dirid=dirs.id AND dirs.dir%s\"%s\")" 
            temp = self.SQLQueryListString(sql, query.directory_list)
            condList.append(temp)
            
        if len(query.file_list):
            tableList.append("files")

            sql = "(checkins.fileid=files.id AND files.file%s\"%s\")"
            temp = self.SQLQueryListString(sql, query.file_list)
            condList.append(temp)
            
        if len(query.author_list):
            tableList.append("people")

            sql = "(checkins.whoid=people.id AND people.who%s\"%s\")"
            temp = self.SQLQueryListString(sql, query.author_list)
            condList.append(temp)
            
        if query.from_date:
            temp = "(checkins.ci_when>=\"%s\")" % (str(query.from_date))
            condList.append(temp)

        if query.to_date:
            temp = "(checkins.ci_when<=\"%s\")" % (str(query.to_date))
            condList.append(temp)

        if query.sort == "date":
            order_by = "ORDER BY checkins.ci_when DESC"
        elif query.sort == "author":
            order_by = "ORDER BY checkins.whoid"
        elif query.sort == "file":
            order_by = "ORDER BY checkins.fileid"

        ## exclude duplicates from the table list
        for table in tableList[:]:
            while tableList.count(table) > 1:
                tableList.remove(table)

        tables = string.join(tableList, ",")
        conditions = string.join(condList, " AND ")

        ## limit the number of rows requested or we could really slam
        ## a server with a large database
        limit = ""
        if cfg.cvsdb.row_limit:
            limit = "LIMIT %s" % (str(cfg.cvsdb.row_limit))

        sql = "SELECT checkins.* FROM %s WHERE %s %s %s" % (
            tables, conditions, order_by, limit)

        return sql
    
    def RunQuery(self, query):
        sql = self.CreateSQLQueryString(query)
        cursor = self.db.cursor()
        cursor.execute(sql)
        
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            
            (dbType, dbCI_When, dbAuthorID, dbRepositoryID, dbDirID,
             dbFileID, dbRevision, dbStickyTag, dbBranchID, dbAddedLines,
             dbRemovedLines, dbDescID) = row

            commit = CreateCommit()

            ## TIME, TIME, TIME is all fucked up; dateobject.gmticks()
            ## is broken, dateobject.ticks() returns somthing like
            ## GMT ticks, except it forgets about daylight savings
            ## time -- we handle it ourself in the following painful way
            gmt_time = time.mktime(
                (dbCI_When.year, dbCI_When.month, dbCI_When.day,
                 dbCI_When.hour, dbCI_When.minute, dbCI_When.second,
                 0, 0, dbCI_When.dst))
    
            commit.SetTime(gmt_time)
            
            commit.SetFile(self.GetFile(dbFileID))
            commit.SetDirectory(self.GetDirectory(dbDirID))
            commit.SetRevision(dbRevision)
            commit.SetRepository(self.GetRepository(dbRepositoryID))
            commit.SetAuthor(self.GetAuthor(dbAuthorID))
            commit.SetBranch(self.GetBranch(dbBranchID))
            commit.SetPlusCount(dbAddedLines)
            commit.SetMinusCount(dbRemovedLines)
            commit.SetDescription(self.GetDescription(dbDescID))

            query.AddCommit(commit)

    def CheckCommit(self, commit):
        repository_id = self.GetRepositoryID(commit.GetRepository(), 0)
        if repository_id == None:
            return None

        dir_id = self.GetDirectoryID(commit.GetDirectory(), 0)
        if dir_id == None:
            return None

        file_id = self.GetFileID(commit.GetFile(), 0)
        if file_id == None:
            return None

        sql = "SELECT * FROM checkins WHERE "\
              "  repositoryid=%s AND dirid=%s AND fileid=%s AND revision=%s"
        sql_args = (repository_id, dir_id, file_id, commit.GetRevision())

        cursor = self.db.cursor()
        cursor.execute(sql, sql_args)
        try:
            (ci_type, ci_when, who_id, repository_id,
             dir_id, file_id, revision, sticky_tag, branch_id,
             plus_count, minus_count, description_id) = cursor.fetchone()
        except TypeError:
            return None

        return commit

## the Commit class holds data on one commit, the representation is as
## close as possible to how it should be committed and retrieved to the
## database engine
class Commit:
    ## static constants for type of commit
    CHANGE = 0
    ADD = 1
    REMOVE = 2
    
    def __init__(self):
        self.__directory = ''
        self.__file = ''
        self.__repository = ''
        self.__revision = ''
        self.__author = ''
        self.__branch = ''
        self.__pluscount = ''
        self.__minuscount = ''
        self.__description = ''
        self.__gmt_time = 0.0
        self.__type = Commit.CHANGE

    def SetRepository(self, repository):
        ## clean up repository path; make sure it doesn't end with a
        ## path seperator
        while len(repository) and repository[-1] == os.sep:
            repository = repository[:-1]

        self.__repository = repository

    def GetRepository(self):
        return self.__repository
        
    def SetDirectory(self, dir):
        ## clean up directory path; make sure it doesn't begin
        ## or end with a path seperator
        while len(dir) and dir[0] == os.sep:
            dir = dir[1:]
        while len(dir) and dir[-1] == os.sep:
            dir = dir[:-1]
        
        self.__directory = dir

    def GetDirectory(self):
        return self.__directory

    def SetFile(self, file):
        ## clean up filename; make sure it doesn't begin
        ## or end with a path seperator
        while len(file) and file[0] == os.sep:
            file = file[1:]
        while len(file) and file[-1] == os.sep:
            file = file[:-1]
        
        self.__file = file

    def GetFile(self):
        return self.__file
        
    def SetRevision(self, revision):
        self.__revision = revision

    def GetRevision(self):
        return self.__revision

    def SetTime(self, gmt_time):
        self.__gmt_time = float(gmt_time)

    def GetTime(self):
        return self.__gmt_time

    def SetAuthor(self, author):
        self.__author = author

    def GetAuthor(self):
        return self.__author

    def SetBranch(self, branch):
        if not branch:
            self.__branch = ''
        else:
            self.__branch = branch

    def GetBranch(self):
        return self.__branch

    def SetPlusCount(self, pluscount):
        self.__pluscount = pluscount

    def GetPlusCount(self):
        return self.__pluscount

    def SetMinusCount(self, minuscount):
        self.__minuscount = minuscount

    def GetMinusCount(self):
        return self.__minuscount

    def SetDescription(self, description):
        self.__description = description

    def GetDescription(self):
        return self.__description

    def SetTypeChange(self):
        self.__type = Commit.CHANGE

    def SetTypeAdd(self):
        self.__type = Commit.ADD

    def SetTypeRemove(self):
        self.__type = Commit.REMOVE

    def GetType(self):
        return self.__type

    def GetTypeString(self):
        if self.__type == Commit.CHANGE:
            return 'Change'
        elif self.__type == Commit.ADD:
            return 'Add'
        elif self.__type == Commit.REMOVE:
            return 'Remove'

## QueryEntry holds data on one match-type in the SQL database
## match is: "exact", "like", or "regex"
class QueryEntry:
    def __init__(self, data, match):
        self.data = data
        self.match = match

## CheckinDatabaseQueryData is a object which contains the search parameters
## for a query to the CheckinDatabase
class CheckinDatabaseQuery:
    def __init__(self):
        ## sorting
        self.sort = "date"
        
        ## repository to query
        self.repository_list = []
        self.branch_list = []
        self.directory_list = []
        self.file_list = []
        self.author_list = []

        ## date range in DBI 2.0 timedate objects
        self.from_date = None
        self.to_date = None

        ## list of commits -- filled in by CVS query
        self.commit_list = []

        ## commit_cb provides a callback for commits as they
        ## are added
        self.commit_cb = None

    def SetRepository(self, repository, match = "exact"):
        self.repository_list.append(QueryEntry(repository, match))

    def SetBranch(self, branch, match = "exact"):
        self.branch_list.append(QueryEntry(branch, match))

    def SetDirectory(self, directory, match = "exact"):
        self.directory_list.append(QueryEntry(directory, match))

    def SetFile(self, file, match = "exact"):
        self.file_list.append(QueryEntry(file, match))

    def SetAuthor(self, author, match = "exact"):
        self.author_list.append(QueryEntry(author, match))

    def SetSortMethod(self, sort):
        self.sort = sort

    def SetFromDateObject(self, ticks):
        self.from_date = dbi.TimestampFromTicks(ticks)

    def SetToDateObject(self, ticks):
        self.to_date = dbi.TimestampFromTicks(ticks)

    def SetFromDateHoursAgo(self, hours_ago):
        ticks = time.time() - (3600 * hours_ago)
        self.from_date = dbi.TimestampFromTicks(ticks)
        
    def SetFromDateDaysAgo(self, days_ago):
        ticks = time.time() - (86400 * days_ago)
        self.from_date = dbi.TimestampFromTicks(ticks)

    def SetToDateDaysAgo(self, days_ago):
        ticks = time.time() - (86400 * days_ago)
        self.to_date = dbi.TimestampFromTicks(ticks)

    def AddCommit(self, commit):
        self.commit_list.append(commit)
        if self.commit_cb:
            self.commit_cb(commit)
        
    def SetCommitCB(self, callback):
        self.commit_cb = callback


##
## entrypoints
##
def CreateCheckinDatabase(host, user, passwd, database):
    return CheckinDatabase(host, user, passwd, database)
  
def CreateCommit():
    return Commit()
    
def CreateCheckinQuery():
    return CheckinDatabaseQuery()

def ConnectDatabaseReadOnly():
    global gCheckinDatabaseReadOnly
    
    if gCheckinDatabaseReadOnly:
        return gCheckinDatabaseReadOnly
    
    gCheckinDatabaseReadOnly = CreateCheckinDatabase(
        cfg.cvsdb.host,
        cfg.cvsdb.readonly_user,
        cfg.cvsdb.readonly_passwd,
        cfg.cvsdb.database_name)
    
    gCheckinDatabaseReadOnly.Connect()
    return gCheckinDatabaseReadOnly

def ConnectDatabase():
    global gCheckinDatabase
    
    gCheckinDatabase = CreateCheckinDatabase(
        cfg.cvsdb.host,
        cfg.cvsdb.user,
        cfg.cvsdb.passwd,
        cfg.cvsdb.database_name)
    
    gCheckinDatabase.Connect()
    return gCheckinDatabase

def RLogDataToCommitList(repository, rlog_data):
    commit_list = []

    ## the filename in rlog_data contains the entire path of the
    ## repository; we strip that out here
    temp = rlog_data.filename[len(repository):]
    directory, file = os.path.split(temp)

    for rlog_entry in rlog_data.rlog_entry_list:
        commit = CreateCommit()
        commit.SetRepository(repository)
        commit.SetDirectory(directory)
        commit.SetFile(file)
        commit.SetRevision(rlog_entry.revision)
        commit.SetAuthor(rlog_entry.author)
        commit.SetDescription(rlog_entry.description)
        commit.SetTime(rlog_entry.time)
        commit.SetPlusCount(rlog_entry.pluscount)
        commit.SetMinusCount(rlog_entry.minuscount)
        commit.SetBranch(rlog_data.LookupBranch(rlog_entry))

        if rlog_entry.type == rlog_entry.CHANGE:
            commit.SetTypeChange()
        elif rlog_entry.type == rlog_entry.ADD:
            commit.SetTypeAdd()
        elif rlog_entry.type == rlog_entry.REMOVE:
            commit.SetTypeRemove()

        commit_list.append(commit)

    return commit_list

def GetCommitListFromRCSFile(repository, filename):
    try:
        rlog_data = rlog.GetRLogData(cfg, filename)
    except rlog.error, e:
        raise error, e
    
    commit_list = RLogDataToCommitList(repository, rlog_data)
    return commit_list

def GetUnrecordedCommitList(repository, filename):
    commit_list = GetCommitListFromRCSFile(repository, filename)
    db = ConnectDatabase()

    unrecorded_commit_list = []
    for commit in commit_list:
        result = db.CheckCommit(commit)
        if not result:
            unrecorded_commit_list.append(commit)

    return unrecorded_commit_list
