# -*- Mode: python -*-
# -----------------------------------------------------------------------
# Copyright (C) 2000 Jay Painter. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth below:
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#
# -----------------------------------------------------------------------
#
# For tracking purposes, this software is identified by:
#   $Id$
#
# -----------------------------------------------------------------------

import os, sys, string, time

## imports from the database API; we re-assign the namespace here so it
## is easier to switch databases
import MySQLdb
DBI = MySQLdb

from commit import CreateCommit, PrintCommit


## base strings used in SQL querries, these should be static members
## of the CheckinDatabase class

sqlBase = 'SELECT checkins.type, checkins.ci_when,checkins. whoid, checkins.repositoryid, checkins.dirid, checkins.fileid, checkins.revision, checkins.stickytag, checkins.branchid, checkins.addedlines, checkins.removedlines, checkins.descid FROM %s WHERE %s %s'
sqlRepository = '(checkins.repositoryid=repositories.id AND repositories.repository="%s")'
sqlBranch = '(checkins.branchid=branches.id AND branches.branch="%s")'
sqlDirectory = '(checkins.dirid=dirs.id AND dirs.dir LIKE "%s%%")'         
sqlFile = '(checkins.fileid=files.id AND files.file="%s")'
sqlFromDate ='(checkins.ci_when>="%s")'
sqlToDate = '(checkins.ci_when<="%s")'
sqlAuthor = '(checkins.whoid=people.id AND people.who="%s")'
sqlSortByDate = 'ORDER BY checkins.ci_when DESC'
sqlSortByAuthor = 'ORDER BY checkins.whoid'
sqlSortByFile = 'ORDER BY checkins.fileid'  
sqlExcludeVersionFiles = '(checkins.fileid=files.id AND files.file NOT LIKE "%%.ver")'
sqlCheckCommit = 'SELECT * FROM checkins WHERE checkins.repositoryid=%s AND checkins.dirid=%s AND checkins.fileid=%s AND checkins.revision=%s'

## CheckinDatabase provides all interfaces needed to the SQL database
## back-end; it needs to be subclassed, and have its "Connect" method
## defined to actually be complete; it should run well off of any DBI 2.0
## complient database interface

class CheckinDatabase:
    def __init__(self, host, user, passwd, database):
        self.dbHost = host
        self.dbUser = user
        self.dbPasswd = passwd
        self.dbDatabase = database

        ## cache Value lookups
        self.dbGetCache = {}
        self.dbGetIDCache = {}
        self.dbDescriptionIDCache = {}

    def Connect(self):
        self.dbConn = self.SQLConnect()

    def SQLGetID(self, table, field, identifier, auto_set):
        sql = 'SELECT id FROM %s x WHERE x.%s="%s"' % (
            table, field, identifier)
                
        cursor = self.dbConn.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        if row:
            return row[0]

        if not auto_set:
            return None

        ## insert the new identifier
        sql = 'INSERT INTO %s (%s) VALUES ("%s")' % (table, field, identifier)
        cursor.execute(sql)
        return self.SQLGetID(table, field, identifier, 0)

    def GetID(self, table, field, identifier, auto_set):
        ## attempt to retrieve from cache
        try:
            return self.dbGetIDCache[table][field][identifier]
        except KeyError:
            pass

        id = self.SQLGetID(table, field, identifier, auto_set)
        if not id:
            return id

        ## add to cache
        if not self.dbGetIDCache.has_key(table):
            self.dbGetIDCache[table] = {}
        if not self.dbGetIDCache[table].has_key(field):
            self.dbGetIDCache[table][field] = {}
        self.dbGetIDCache[table][field][identifier] = id
        return id

    def SQLGet(self, table, field, id):
        sql = 'SELECT %s FROM %s x WHERE x.id="%s"' % (field, table, id)
                
        cursor = self.dbConn.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        if not row:
            return None
        return row[0]

    def Get(self, table, field, id):
        ## attempt to retrieve from cache
        try:
            return self.dbGetCache[table][field][id]
        except KeyError:
            pass

        value = self.SQLGet(table, field, id)
        if not value:
            return None

        ## add to cache
        if not self.dbGetCache.has_key(table):
            self.dbGetCache[table] = {}
        if not self.dbGetCache[table].has_key(field):
            self.dbGetCache[table][field] = {}
        self.dbGetCache[table][field][id] = value
        return value

    def GetBranchID(self, branch, auto_set = 1):
        return self.GetID('branches', 'branch', branch, auto_set)

    def GetBranch(self, id):
        return self.Get('branches', 'branch', id)

    def GetDirectoryID(self, dir, auto_set = 1):
        return self.GetID('dirs', 'dir', dir, auto_set)

    def GetDirectory(self, id):
        return self.Get('dirs', 'dir', id)

    def GetFileID(self, file, auto_set = 1):
        return self.GetID('files', 'file', file, auto_set)

    def GetFile(self, id):
        return self.Get('files', 'file', id)
    
    def GetAuthorID(self, author, auto_set = 1):
        return self.GetID('people', 'who', author, auto_set)

    def GetAuthor(self, id):
        return self.Get('people', 'who', id)
    
    def GetRepositoryID(self, repository, auto_set = 1):
        return self.GetID('repositories', 'repository', repository, auto_set)

    def GetRepository(self, id):
        return self.Get('repositories', 'repository', id)

    def SQLGetDescriptionID(self, description, auto_set = 1):
        ## lame string hash, blame Netscape -JMP
        hash = len(description)
        
        cursor = self.dbConn.cursor()
        cursor.execute(
            'SELECT id FROM descs WHERE hash=%s and description=%s',
            (hash, description))

        row = cursor.fetchone()
        if row:
            return row[0]

        if not auto_set:
            return None

        cursor = self.dbConn.cursor()
        cursor.execute(
            'INSERT INTO descs (hash, description) values (%s, %s)',
            (hash, description))
        
        return self.GetDescriptionID(description, 0)

    def GetDescriptionID(self, description, auto_set = 1):
        ## lame string hash, blame Netscape -JMP
        hash = len(description)
        
        ## attempt to retrieve from cache
        try:
            return self.dbDescriptionIDCache[hash][description]
        except KeyError:
            pass

        id = self.SQLGetDescriptionID(description, auto_set)
        if not id:
            return id

        ## add to cache
        if not self.dbDescriptionIDCache.has_key(hash):
            self.dbDescriptionIDCache[hash] = {}
        self.dbDescriptionIDCache[hash][description] = id
        return id

    def GetDescription(self, id):
        return self.Get('descs', 'description', id)

    def GetList(self, table, field_index):
        sql = 'SELECT * FROM %s' % (table)
        
        cursor = self.dbConn.cursor()
        cursor.execute(sql)

        list = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            list.append(row[field_index])

        return list

    def GetRepositoryList(self):
        return self.GetList('repositories', 1)

    def GetBranchList(self):
        return self.GetList('branches', 1)

    def GetAuthorList(self):
        return self.GetList('people', 1)

    def AddCommitList(self, commit_list):
        for commit in commit_list:
            self.AddCommit(commit)

    def AddCommit(self, commit):
        dbType = commit.GetTypeString()

        ## MORE TIME HELL: the MySQLdb module doesn't construct times
        ## correctly when created with TimestampFromTicks -- it doesn't
        ## account for daylight savings time, so we use Python's time
        ## module to do the conversion
        temp = time.localtime(commit.GetTime())
        dbCI_When = DBI.Timestamp(temp)

        dbWhoID = self.GetAuthorID(commit.GetAuthor())
        dbRepositoryID = self.GetRepositoryID(commit.GetRepository())
        dbDirectoryID = self.GetDirectoryID(commit.GetDirectory())
        dbFileID = self.GetFileID(commit.GetFile())
        dbRevision = commit.GetRevision()
        dbStickyTag = 'NULL'
        dbBranchID = self.GetBranchID(commit.GetBranch())
        dbPlusCount = commit.GetPlusCount()
        dbMinusCount = commit.GetMinusCount()
        dbDescriptionID = self.GetDescriptionID(commit.GetDescription())
        
        sql = 'REPLACE INTO checkins(type, ci_when, whoid, repositoryid, dirid, fileid, revision, stickytag, branchid, addedlines, removedlines, descid) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'
        sqlArguments = (
            dbType, dbCI_When, dbWhoID, dbRepositoryID, dbDirectoryID,
            dbFileID, dbRevision, dbStickyTag, dbBranchID, dbPlusCount,
            dbMinusCount, dbDescriptionID)

        cursor = self.dbConn.cursor()
        cursor.execute(sql, sqlArguments)

    def CreateSQLQueryString(self, query):
        tableList = ['checkins']
        condList = []
   
        tableList.append('files')
        condList.append(sqlExcludeVersionFiles)
 
        if query.repository:
            tableList.append('repositories')
            condList.append(sqlRepository % (query.repository))

        if query.branch:
            tableList.append('branches')
            condList.append(sqlBranch % (query.branch))

        if query.from_date:
            condList.append(sqlFromDate % (str(query.from_date)))

        if query.to_date:
            condList.append(sqlToDate % (str(query.to_date)))

        if query.author:
            tableList.append('people')
            condList.append(sqlAuthor % (query.author))

        if query.directory:
            tableList.append('dirs')
            condList.append(sqlDirectory % (query.directory))

        if query.file:
            #tableList.append('files')
            condList.append(sqlFile % (query.file))

        if query.sort == query.SORT_DATE:
            order_by = sqlSortByDate
        elif query.sort == query.SORT_AUTHOR:
            order_by = sqlSortByAuthor
        elif query.sort == query.SORT_FILE:
            order_by = sqlSortByFile

        sql = sqlBase % (
            string.join(tableList, ', '),
            string.join(condList, ' AND '),
            order_by)

        return sql
    
    def RunQuery(self, query):
        sql = self.CreateSQLQueryString(query)
        cursor = self.dbConn.cursor()
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
        dbRepositoryID = self.GetRepositoryID(commit.GetRepository(), 0)
        if dbRepositoryID == None:
            return None

        dbDirID = self.GetDirectoryID(commit.GetDirectory(), 0)
        if dbDirID == None:
            return None

        dbFileID = self.GetFileID(commit.GetFile(), 0)
        if dbFileID == None:
            return None

        sqlArguments = (dbRepositoryID, dbDirID, dbFileID,
                        commit.GetRevision())

        cursor = self.dbConn.cursor()
        cursor.execute(sqlCheckCommit, sqlArguments)
        row = cursor.fetchone()
        if not row:
            return None

        return commit
        

class MySQLCheckinDatabase(CheckinDatabase):
    def SQLConnect(self):
        return MySQLdb.connect(
            host = self.dbHost,
            user = self.dbUser,
            passwd = self.dbPasswd,
            db = self.dbDatabase)


## CheckinDatabaseQueryData is a object which contains the search parameters
## for a query to the CheckinDatabase

class CheckinDatabaseQuery:

    SORT_DATE = 0
    SORT_AUTHOR = 1
    SORT_FILE = 2
    SORT_CHANGESIZE = 3
    
    def __init__(self):
        ## repository to query
        self.repository = None

        ## branch
        self.branch = None

        ## directory to seach
        self.directory = None

        ## file to search for
        self.file = None

        ## sorting method
        self.sort = CheckinDatabaseQuery.SORT_DATE;
        
        ## author to search for
        self.author = None

        ## date range in DBI 2.0 timedate objects
        self.from_date = None
        self.to_date = None

        ## list of commits -- filled in by CVS query
        self.commit_list = []

        ## commit_cb provides a callback for commits as they
        ## are added
        self.commit_cb = None

    def SetRepository(self, repository):
        self.repository = repository

    def SetBranch(self, branch):
        self.branch = branch

    def SetDirectory(self, directory):
        self.directory = directory

    def SetFile(self, file):
        self.file = file

    def SetSortMethod(self, sort):
        self.sort = sort

    def SetAuthor(self, author):
        self.author = author

    def SetFromDateObject(self, date):
        self.from_date = date

    def SetToDateObject(self, date):
        self.to_date = date

    def SetFromDateHoursAgo(self, hours_ago):
        ticks = time.time() - (3600 * hours_ago)
        self.from_date = DBI.TimestampFromTicks(ticks)
        
    def SetFromDateDaysAgo(self, days_ago):
        ticks = time.time() - (86400 * days_ago)
        self.from_date = DBI.TimestampFromTicks(ticks)

    def SetToDateDaysAgo(self, days_ago):
        ticks = time.time() - (86400 * days_ago)
        self.to_date = DBI.TimestampFromTicks(ticks)

    def AddCommit(self, commit):
        self.commit_list.append(commit)
        if self.commit_cb:
            self.commit_cb(commit)
        
    def SetCommitCB(self, callback):
        self.commit_cb = callback
        

## entrypoints

def CreateCheckinDatabase(host, user, passwd, database):
    return MySQLCheckinDatabase(host, user, passwd, database)

def CreateCheckinQuery():
    return CheckinDatabaseQuery()
