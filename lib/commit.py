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

import os

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
        while repository[-1] == os.sep:
            repository = repository[:-1]

        self.__repository = repository

    def GetRepository(self):
        return self.__repository
        
    def SetDirectory(self, dir):
        ## clean up directory path; make sure it doesn't begin
        ## or end with a path seperator
        while dir[0] == os.sep:
            dir = dir[1:]
        while dir[-1] == os.sep:
            dir = dir[:-1]
        
        self.__directory = dir

    def GetDirectory(self):
        return self.__directory

    def SetFile(self, file):
        ## clean up filename; make sure it doesn't begin
        ## or end with a path seperator
        while file[0] == os.sep:
            file = file[1:]
        while file[-1] == os.sep:
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


## entrypoints
        
def CreateCommit():
    return Commit()


def PrintCommit(commit):
    print os.path.join(commit.GetDirectory(), commit.GetFile()),\
          commit.GetRevision(),\
          commit.GetAuthor()
        
    if commit.GetBranch():
        print commit.GetBranch()
    print commit.GetDescription()
    print

