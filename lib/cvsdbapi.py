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

import os, cfg, database, rlog, commit

## error
error = 'cvsdbapi error'

## database
CreateCheckinDatabase = database.CreateCheckinDatabase
CreateCheckinQuery = database.CreateCheckinQuery

## rlog
GetRLogData = rlog.GetRLogData

## commit
CreateCommit = commit.CreateCommit
PrintCommit = commit.PrintCommit

## cached (active) database connections
gCheckinDatabase = None
gCheckinDatabaseReadOnly = None


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
    ## repository, and the ,v at the end of the RCS file;
    ## we strip those out here
    temp = rlog_data.filename[len(repository):]
    while temp[0] == os.sep:
        temp = temp[1:]
    directory, file = os.path.split(temp)

    if file[-2:] == ",v":
        file = file[:-2]

    for rlog_entry in rlog_data.rlog_entry_list:
        commit = CreateCommit()
        commit.SetRepository(repository)
        commit.SetDirectory(directory)
        commit.SetFile(file)
        commit.SetRevision(rlog_entry.revision)
        commit.SetAuthor(rlog_entry.author)
        commit.SetDescription(rlog_entry.description)
        commit.SetDate(rlog_entry.date)
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
