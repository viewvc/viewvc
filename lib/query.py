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

import time

## imports from the database API; we re-assign the namespace here so it
## is easier to switch databases
import MySQLdb
DBI = MySQLdb


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
        self.from_date = DBI.TimestampFromTicks(ticks)

    def SetToDateObject(self, ticks):
        self.to_date = DBI.TimestampFromTicks(ticks)

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
def CreateCheckinQuery():
    return CheckinDatabaseQuery()
