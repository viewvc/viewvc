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

import os, sys, string, time, re

## RLogOutputParser uses the output of rlog to build a list of Commit
## objects describing all the checkins from a given RCS file; this
## parser is fairly optimized, and therefore can be delicate if the
## rlog output varies between versions of rlog; I don't know if it does;
## to make really fast, I should wrap the C rcslib

## there's definately not much error checking here; I'll assume things
## will go smoothly, and trap errors via exception handlers above this
## function

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
    ## static constants for type of log entry; this will be changed
    ## to strings I guess -JMP
    CHANGE = 0
    ADD = 1
    REMOVE = 2

## Here's the init function, which isn't needed since this class
## is fully initalized by RLogParser when creating a new log entry.
## Let's keep this initializer as a description of what is held in
## the class, but keep it commented out since it only makes things
## slow.
##
##     def __init__(self):
##         self.revision = ''
##         self.author = ''
##         self.branch = ''
##         self.pluscount = ''
##         self.minuscount = ''
##         self.description = ''
##         self.time = None
##         self.type = RLogEntry.CHANGE


class RLog:
    "Provides a alternative file-like interface for running 'rlog'."
    
    def __init__(self, filename, revision, date):
        self.filename = self.fix_filename(filename)
        self.checkout_filename = self.create_checkout_filename(self.filename)
        self.revision = revision
        self.date = date

        arg_list = []
        if self.revision:
            arg_list.append('-r%s' % (self.revision))
        if self.date:
            arg_list.append('-d%s' % (self.date))

        self.cmd = 'rlog %s "%s"' % (string.join(arg_list), self.filename)
        self.rlog = os.popen(self.cmd, 'r')

    def fix_filename(self, filename):
        ## all RCS files have the ",v" ending
        if filename[-2:] != ",v":
            filename = "%s,v" % (filename)

        if os.path.isfile(filename):
            return filename

        ## check the Attic for the RCS file
        path, basename = os.path.split(filename)
        filename = os.path.join(path, "Attic", basename)

        if os.path.isfile(filename):
            return filename
        
        raise error, "file not found"

    def create_checkout_filename(self, filename):
        ## cut off the ",v"
        checkout_filename = filename[:-2]

        ## check if the file is in the Attic
        path, basename = os.path.split(checkout_filename)
        if path[-6:] != '/Attic':
            return checkout_filename

        ## remove the "Attic" part of the path
        checkout_filename = os.path.join(path[:-6], basename)
        return checkout_filename
        
    def readline(self):
        line = self.rlog.readline()
        if line:
            return line

        status = self.close()
        if status:
            temp = '[ERROR] %s' % (self.cmd)
            raise error, temp

        return None

    def close(self):
        status = self.rlog.close()
        self.rlog = None
        return status


## constants used in the output parser

_rlog_commit_sep = '----------------------------\n'
_rlog_end = '=============================================================================\n'

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
    
    def __init__(self, rlog):
        self.rlog = rlog
        self.rlog_data = RLogData(rlog.checkout_filename)

        ## run the parser
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

            (tag, revision) = match.groups()

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
            if line == _rlog_commit_sep:
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
        (revision,) = match.groups()

        ## data line
        line = self.rlog.readline()
        match = _re_data_line.match(line)
        if not match:
            match = _re_data_line_add.match(line)

        if not match:
            raise error, 'bad rlog parser, no cookie!'

        ## retrieve the matched grops as a tuple in hopes
        ## this will be faster (ala profiler)
        groups = match.groups()

        year = string.atoi(groups[0])
        month = string.atoi(groups[1])
        day = string.atoi(groups[2])
        hour = string.atoi(groups[3])
        minute = string.atoi(groups[4])
        second = string.atoi(groups[5])
        author = groups[6]
        state = groups[7]

        ## very strange; here's the deal: if this is a newly added file,
        ## then there is no plus/minus count count of lines; if there
        ## is, then this could be a "CHANGE" or "REMOVE", you can tell
        ## if the file has been removed by looking if state == 'dead'
        try:
            pluscount = groups[8]
            minuscount = groups[9]
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
            ## or '------'... between entries
            if line == _rlog_commit_sep or line == _rlog_end:
                break

            ## append line to the descripton list
            desc_line_list.append(string.rstrip(line))

        ## compute time using time routines in seconds from epoc GMT
        ## NOTE: mktime's arguments are in local time, and we have
        ##       them in GMT from RCS; therefore, we have to manually
        ##       subtract out the timezone correction
        ##
        ## XXX: Linux glib2.0.7 bug: it looks like mktime doesn't honor
        ##      the '0' flag to force no timezone correction, so we look
        ##      at the correction ourself and do the right thing after
        ##      mktime mangles the date
        gmt_time = \
            time.mktime((year, month, day, hour, minute, second, 0, 0, -1))

        if time.daylight:
            gmt_time = gmt_time - time.altzone
        else:
            gmt_time = gmt_time - time.timezone

        ## now create and return the RLogEntry
        rlog_entry = RLogEntry()
        rlog_entry.type = cmit_type
        rlog_entry.revision = revision
        rlog_entry.author = author
        rlog_entry.description = string.join(desc_line_list, '\n')
        rlog_entry.time = gmt_time
        rlog_entry.pluscount = pluscount
        rlog_entry.minuscount = minuscount

        return rlog_entry


## entrypoints

def GetRLogData(path, revision = '', date = ''):
    rlog = RLog(path, revision, date)
    rlog_parser = RLogOutputParser(rlog)
    return rlog_parser.rlog_data
