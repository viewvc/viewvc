# $Id$
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

import os, sys, string, time, re

## RLogOutputParser uses the output of rlog to build a list of Commit
## objects describing all the checkins from a given RCS file; this
## parser is fairly optimized, and therefore can be delicate if the
## rlog output varies between versions of rlog; I don't know if it does;
## to make really fast, I should wrap the C rcslib

## there's definately not much error checking here; I'll assume things
## will go smoothly, and trap errors via exception handlers above this
## function


## constants
RLOG_COMMIT_SEP = '----------------------------\n'
RLOG_END = '=============================================================================\n'


## exception for this class
error = 'rlog error'


class RLogData:
    "Container object for all data parsed from a 'rlog' output."
  
    def __init__(self, filename):
        self.filename = filename
        self.symbolic_name_hash = {}
        self.rlog_entry_list = []

    def LookupBranch(self, rlog_entry):
        index = string.rfind(rlog_entry.revision, '.')
        branch_revision = rlog_entry.revision[:index]

        try:
            branch = self.symbolic_name_hash[branch_revision]
        except KeyError:
            branch = ''

        return branch
    

class RLogEntry:

    ## static constants for type of log entry
    CHANGE = 0
    ADD = 1
    REMOVE = 2
  
    def __init__(self):
        self.revision = ''
        self.author = ''
        self.branch = ''
        self.pluscount = ''
        self.minuscount = ''
        self.description = ''
        self.date = None
        self.type = RLogEntry.CHANGE


class RLog:
    "Provides a alternative file-like interface for running 'rlog'."
    
    def __init__(self, filename, revision, date):
        self.filename = filename
        self.revision = revision
        self.date = date

        arg_list = []
        if self.revision:
            arg_list.append('-r%s' % (self.revision))
        if self.date:
            arg_list.append('-d%s' % (self.date))
            
        self.cmd = 'rlog %s "%s"' % (string.join(arg_list), filename)
        self.rlog = os.popen(self.cmd, 'r')

    def readline(self):
        if not self.rlog:
            raise error, 'rlog terminated'
        
        line = self.rlog.readline()
        if not line:
            status = self.close()
            if status:
                temp = '[ERROR] %s' % (self.cmd)
                raise error, temp

        return line

    def close(self):
        status = self.rlog.close()
        self.rlog = None
        return status


## regular expression used in the output parser
_re_symbolic_name = re.compile("\s+([^:]+):\s+(.+)$")

_re_revision = re.compile("^revision\s+([0-9.]+).*")

_re_data_line = re.compile(
    "^date:\s+(\d+)/(\d+)/(\d+)\s+(\d+):(\d+):(\d+);\s+"\
    "author:\s+([^;]+);\s+"\
    "state:\s+([^;]+);\s+"\
    "lines:\s+\+(\d+)\s+\-(\d+)$")

_re_data_line_add = re.compile(
    "^date:\s+(\d+)/(\d+)/(\d+)\s+(\d+):(\d+):(\d+);\s+"\
    "author:\s+([^;]+);\s+"\
    "state:\s+([^;]+);$")

class RLogOutputParser:

    def __init__(self, filename, revision, date):
        self.rlog_data = RLogData(filename)
        self.revision = revision
        self.date = date

    def Run(self):
        self.rlog = RLog(self.rlog_data.filename, self.revision, self.date)
        self.parse_to_symbolic_names()
        self.parse_symbolic_names()
        self.parse_to_description()
        self.parse_rlog_entries()
    
    def parse_to_symbolic_names(self):
        while 1:
            line = self.rlog.readline()
            if line[:15] == 'symbolic names:':
                break

    def parse_symbolic_names(self):
        ## parse all the tags int the branch_hash, it's used later to get
        ## the text names of non-head branches
        while 1:
            line = self.rlog.readline()
            match = _re_symbolic_name.match(line)
            if not match:
                break

            tag = match.group(1)
            revision = match.group(2)

            ## check if the tag represents a branch, in RCS this means
            ## the second-to-last number is a zero
            index = string.rfind(revision, '.')
            if revision[index-2:index] == '.0':
                revision = revision[:index-2] + revision[index:]
            
            self.rlog_data.symbolic_name_hash[revision] = tag

    def parse_to_description(self):
        while 1:
            line = self.rlog.readline()
            if line[:12] == 'description:':
                break
            
        ## eat all lines until we reach '-----' seperator
        while 1:
            line = self.rlog.readline()
            if line == RLOG_COMMIT_SEP:
                break

    def parse_rlog_entries(self):
        while 1:
            rlog_entry = self.parse_one_rlog_entry()
            if not rlog_entry:
                break
            self.rlog_data.rlog_entry_list.append(rlog_entry)

    def parse_one_rlog_entry(self):
        ## revision line/first line
        line = self.rlog.readline()
        if not line:
            return None

        ## revision
        match = _re_revision.match(line)
        revision = match.group(1)

        ## data line
        line = self.rlog.readline()
        match = _re_data_line.match(line)
        if not match:
            match = _re_data_line_add.match(line)

        if not match:
            raise error, 'bad rlog parser, no cookie!'

        year = string.atoi(match.group(1))
        month = string.atoi(match.group(2))
        day = string.atoi(match.group(3))
        hour = string.atoi(match.group(4))
        minute = string.atoi(match.group(5))
        second = string.atoi(match.group(6))
        author = match.group(7)
        state = match.group(8)

        ## very strange; here's the deal: if this is a newly added file,
        ## then there is no plus/minus count count of lines; if there
        ## is, then this could be a "CHANGE" or "REMOVE", you can tell
        ## if the file has been removed by looking if state == 'dead'
        try:
            pluscount = match.group(9)
            minuscount = match.group(10)
        except IndexError:
            pluscount = ''
            minuscount = ''
            cmit_type = RLogEntry.ADD
        else:
            if state == 'dead':
                cmit_type = RLogEntry.REMOVE
            else:
                cmit_type = RLogEntry.CHANGE
        
        ## branch line: pretty much ignored if it's there
        desc_line_list = []
                
        line = self.rlog.readline()
        if not line[:10] == 'branches: ':
            desc_line_list.append(string.rstrip(line))

        ## suck up description
        while 1:
            line = self.rlog.readline()

            ## the last line printed out by rlog is '===='...
            if line == RLOG_END:
                done = 1
                break

            ## commit delimiters, when we hit one this commit is done
            if line == RLOG_COMMIT_SEP:
                break

            ## append line to the descripton list
            desc_line_list.append(string.rstrip(line))

        ## now create and return the RLogEntry
        rlog_entry = RLogEntry()
        rlog_entry.type = cmit_type
        rlog_entry.revision = revision
        rlog_entry.author = author
        rlog_entry.description = string.join(desc_line_list, '\n')
        rlog_entry.date = (year, month, day, hour, minute, second)
        rlog_entry.pluscount = pluscount
        rlog_entry.minuscount = minuscount

        return rlog_entry


## entrypoints

def GetRLogData(path, revision = '', date = ''):
    rlog_parser = RLogOutputParser(path, revision, date)
    rlog_parser.Run()
    return rlog_parser.rlog_data


def RLogDataToCommitList(repository, rlog_data):
    from commit import CreateCommit
    commit_list = []

    ## the filename in rlog_data contains the entire path of the
    ## repository, and the ,v at the end of the RCS file;
    ## we strip those out here
    temp = rlog_data.filename[len(repository):]
    while temp[0] == os.sep:
        temp = temp[1:]
    directory, file = os.path.split(temp)
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
