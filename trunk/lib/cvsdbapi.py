# -*- Mode: python -*-
#
# Copyright (C) 2000-2001 The ViewCVS Group. All Rights Reserved.
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

import database
import query
import rlog
import commit
import config

## error
error = 'cvsdbapi error'

## database
CreateCheckinDatabase = database.CreateCheckinDatabase
CreateCheckinQuery = query.CreateCheckinQuery

## rlog
GetRLogData = rlog.GetRLogData

## commit
CreateCommit = commit.CreateCommit
PrintCommit = commit.PrintCommit

## cached (active) database connections
gCheckinDatabase = None
gCheckinDatabaseReadOnly = None

## load configuration file, the data is used globally here
cfg = config.Config()
cfg.set_defaults()
cfg.load_config(CONF_PATHNAME)


def ConnectDatabaseReadOnly():
    global gCheckinDatabaseReadOnly
    
    if gCheckinDatabaseReadOnly:
        return gCheckinDatabaseReadOnly
    
    gCheckinDatabaseReadOnly = database.CreateCheckinDatabase(
        cfg.cvsdb.host,
        cfg.cvsdb.readonly_user,
        cfg.cvsdb.readonly_passwd,
        cfg.cvsdb.database_name)
    
    gCheckinDatabaseReadOnly.Connect()
    return gCheckinDatabaseReadOnly


def ConnectDatabase():
    global gCheckinDatabase
    
    gCheckinDatabase = database.CreateCheckinDatabase(
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
        rlog_data = GetRLogData(filename)
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
