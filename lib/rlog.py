# -*- Mode: python -*-
#
# Copyright (C) 2000-2002 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://viewcvs.sourceforge.net/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewcvs.sourceforge.net/
#
# -----------------------------------------------------------------------
#

import os
import string

from vclib import bincvs

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

        return self.symbolic_name_hash.get(branch_revision, '')
    

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


def _get_v_file(filename):
    # all RCS files have the ",v" ending
    if filename[-2:] != ",v":
        filename = filename + ',v'

    if os.path.isfile(filename):
        return filename

    # check the Attic for the RCS file
    path, basename = os.path.split(filename)
    filename = os.path.join(path, "Attic", basename)

    if os.path.isfile(filename):
        return filename

    ### create an exception class
    raise error, "rlog file not found: %s" % (filename)

def _get_co_file(v_file):
    # remove the ",v" suffix
    co_file = v_file[:-2]

    # look for, and remove, any Attic component
    path, basename = os.path.split(co_file)
    if path[-6:] == '/Attic':
        return os.path.join(path[:-6], basename)

    return co_file

def GetRLogData(repository, path, revision=''):
    v_file = _get_v_file(path)
    branch, taginfo, revs = bincvs.fetch_log(repository, v_file, revision)
    class _blank:
      pass

    data = RLogData(_get_co_file(v_file))

    for name, rev in taginfo.items():
        # if this is a branch (X.Y.0.Z), then remove the .0 portion
        idx = string.rfind(rev, '.')
        if rev[idx-2:idx] == '.0':
            rev = rev[:idx-2] + rev[idx:]

        ### hmm. this is only useful for *branch names*, which won't overlap
        ### on a specific rev.
        ### note: the tag name associated with a revision will be
        ### non-deterministic because of this overlap.
        ### maybe just omit the name for non-branch tags?
        data.symbolic_name_hash[rev] = name

    for entry in revs:
        new_entry = _blank()

        if entry.changed:
            # extract the plus/minus and drop the sign
            plus, minus = string.split(entry.changed)
            new_entry.pluscount = plus[1:]
            new_entry.minuscount = minus[1:]

            if entry.dead:
                new_entry.type = RLogEntry.REMOVE
            else:
                new_entry.type = RLogEntry.CHANGE
        else:
            new_entry.type = RLogEntry.ADD
            new_entry.pluscount = new_entry.minuscount = ''

        # some goop to drop a trailing newline
        if entry.log[-1:] == '\n':
          new_entry.description = entry.log[:-1]
        else:
          new_entry.description = entry.log

        new_entry.revision = entry.string
        new_entry.author = entry.author
        new_entry.time = entry.date

        data.rlog_entry_list.append(new_entry)

    return data
