# -*-python-*-
#
# Copyright (C) 1999-2011 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

"""Version Control lib is an abstract API to access versioning systems
such as CVS.
"""

import string
import types


# item types returned by Repository.itemtype().
FILE = 'FILE'
DIR = 'DIR'

# diff types recognized by Repository.rawdiff().
UNIFIED = 1
CONTEXT = 2
SIDE_BY_SIDE = 3

# root types returned by Repository.roottype().
CVS = 'cvs'
SVN = 'svn'

# action kinds found in ChangedPath.action
ADDED      = 'added'
DELETED    = 'deleted'
REPLACED   = 'replaced'
MODIFIED   = 'modified'

# log sort keys
SORTBY_DEFAULT = 0  # default/no sorting
SORTBY_DATE    = 1  # sorted by date, youngest first
SORTBY_REV     = 2  # sorted by revision, youngest first


# ======================================================================
#
class Repository:
  """Abstract class representing a repository."""

  def rootname(self):
    """Return the name of this repository."""

  def roottype(self):
    """Return the type of this repository (vclib.CVS, vclib.SVN, ...)."""

  def rootpath(self):
    """Return the location of this repository."""

  def authorizer(self):
    """Return the vcauth.Authorizer object associated with this
    repository, or None if no such association has been made."""
    
  def open(self):
    """Open a connection to the repository."""
    
  def itemtype(self, path_parts, rev):
    """Return the type of the item (file or dir) at the given path and revision

    The result will be vclib.DIR or vclib.FILE

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    rev is the revision of the item to check
    """
    pass

  def openfile(self, path_parts, rev, options):
    """Open a file object to read file contents at a given path and revision.

    The return value is a 2-tuple of containg the file object and revision
    number in canonical form.

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    rev is the revision of the file to check out

    options is a dictionary of implementation specific options
    """

  def listdir(self, path_parts, rev, options):
    """Return list of files in a directory

    The result is a list of DirEntry objects

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    rev is the revision of the directory to list

    options is a dictionary of implementation specific options
    """

  def dirlogs(self, path_parts, rev, entries, options):
    """Augment directory entries with log information

    New properties will be set on all of the DirEntry objects in the entries
    list. At the very least, a "rev" property will be set to a revision
    number or None if the entry doesn't have a number. Other properties that
    may be set include "date", "author", "log", "size", and "lockinfo".

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    rev is the revision of the directory listing and will effect which log
    messages are returned

    entries is a list of DirEntry objects returned from a previous call to
    the listdir() method

    options is a dictionary of implementation specific options
    """
  
  def itemlog(self, path_parts, rev, sortby, first, limit, options):
    """Retrieve an item's log information

    The result is a list of Revision objects

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    rev is the revision of the item to return information about

    sortby indicates the way in which the returned list should be
    sorted (SORTBY_DEFAULT, SORTBY_DATE, SORTBY_REV)

    first is the 0-based index of the first Revision returned (after
    sorting, if any, has occured)

    limit is the maximum number of returned Revisions, or 0 to return
    all available data
    
    options is a dictionary of implementation specific options
    """

  def itemprops(self, path_parts, rev):
    """Return a dictionary mapping property names to property values
    for properties stored on an item.

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    rev is the revision of the item to return information about.
    """
    
  def rawdiff(self, path_parts1, rev1, path_parts2, rev2, type, options={}):
    """Return a diff (in GNU diff format) of two file revisions

    type is the requested diff type (UNIFIED, CONTEXT, etc)

    options is a dictionary that can contain the following options plus
    implementation-specific options

      context - integer, number of context lines to include
      funout - boolean, include C function names
      ignore_white - boolean, ignore whitespace

    Return value is a python file object
    """

  def annotate(self, path_parts, rev):
    """Return a list of annotate file content lines and a revision.

    The result is a list of Annotation objects, sorted by their
    line_number components.
    """

  def revinfo(self, rev):
    """Return information about a global revision

    rev is the revision of the item to return information about
    
    Return value is a 5-tuple containing: the date, author, log
    message, a list of ChangedPath items representing paths changed,
    and a dictionary mapping property names to property values for
    properties stored on an item.

    Raise vclib.UnsupportedFeature if the version control system
    doesn't support a global revision concept.
    """

  def isexecutable(self, path_parts, rev):
    """Return true iff a given revision of a versioned file is to be
    considered an executable program or script.

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    rev is the revision of the item to return information about
    """
    
    
# ======================================================================
class DirEntry:
  """Instances represent items in a directory listing"""

  def __init__(self, name, kind, errors=[]):
    """Create a new DirEntry() item:
          NAME:  The name of the directory entry
          KIND:  The path kind of the entry (vclib.DIR, vclib.FILE)
          ERRORS:  A list of error strings representing problems encountered
                   while determining the other info about this entry
    """
    self.name = name
    self.kind = kind
    self.errors = errors

class Revision:
  """Instances holds information about revisions of versioned resources"""

  def __init__(self, number, string, date, author, changed, log, size, lockinfo):
    """Create a new Revision() item:
          NUMBER:  Revision in an integer-based, sortable format
          STRING:  Revision as a string
          DATE:  Seconds since Epoch (GMT) that this revision was created
          AUTHOR:  Author of the revision
          CHANGED:  Lines-changed (contextual diff) information
          LOG:  Log message associated with the creation of this revision
          SIZE:  Size (in bytes) of this revision's fulltext (files only)
          LOCKINFO:  Information about locks held on this revision
    """
    self.number = number
    self.string = string
    self.date = date
    self.author = author
    self.changed = changed
    self.log = log
    self.size = size
    self.lockinfo = lockinfo

  def __cmp__(self, other):
    return cmp(self.number, other.number)

class Annotation:
  """Instances represent per-line file annotation information"""

  def __init__(self, text, line_number, rev, prev_rev, author, date):
    """Create a new Annotation() item:
          TEXT:  Raw text of a line of file contents
          LINE_NUMBER:  Line number on which the line is found
          REV:  Revision in which the line was last modified
          PREV_REV:  Revision prior to 'rev'
          AUTHOR:  Author who last modified the line
          DATE:  Date on which the line was last modified, in seconds since
                 the epoch, GMT
    """
    self.text = text
    self.line_number = line_number
    self.rev = rev
    self.prev_rev = prev_rev
    self.author = author
    self.date = date

class ChangedPath:
  """Instances represent changes to paths"""

  def __init__(self, path_parts, rev, pathtype, base_path_parts,
               base_rev, action, copied, text_changed, props_changed):
    """Create a new ChangedPath() item:
          PATH_PARTS:       Path that was changed
          REV:              Revision represented by this change
          PATHTYPE:         Type of this path (vclib.DIR, vclib.FILE, ...)
          BASE_PATH_PARTS:  Previous path for this changed item
          BASE_REV:         Previous revision for this changed item
          ACTION:           Kind of change (vclib.ADDED, vclib.DELETED, ...)
          COPIED:           Boolean -- was this path copied from elsewhere?
          TEXT_CHANGED:     Boolean -- did the file's text change?
          PROPS_CHANGED:    Boolean -- did the item's metadata change?
    """
    self.path_parts = path_parts
    self.rev = rev
    self.pathtype = pathtype
    self.base_path_parts = base_path_parts
    self.base_rev = base_rev
    self.action = action
    self.copied = copied
    self.text_changed = text_changed
    self.props_changed = props_changed


# ======================================================================

class Error(Exception):
  pass

class ReposNotFound(Error):
  pass

class UnsupportedFeature(Error):
  pass

class ItemNotFound(Error):
  def __init__(self, path):
    # use '/' rather than os.sep because this is for user consumption, and
    # it was defined using URL separators
    if type(path) in (types.TupleType, types.ListType):
      path = string.join(path, '/')
    Error.__init__(self, path)

class InvalidRevision(Error):
  def __init__(self, revision=None):
    if revision is None:
      Error.__init__(self, "Invalid revision")
    else:
      Error.__init__(self, "Invalid revision " + str(revision))

class NonTextualFileContents(Error):
  pass

# ======================================================================
# Implementation code used by multiple vclib modules

import popen
import os
import time

def _diff_args(type, options):
  """generate argument list to pass to diff or rcsdiff"""
  args = []
  if type == CONTEXT:
    if options.has_key('context'):
      if options['context'] is None:
        args.append('--context=-1')
      else:
        args.append('--context=%i' % options['context'])
    else:
      args.append('-c')
  elif type == UNIFIED:
    if options.has_key('context'):
      if options['context'] is None:
        args.append('--unified=-1')
      else:
        args.append('--unified=%i' % options['context'])
    else:
      args.append('-u')
  elif type == SIDE_BY_SIDE:
    args.append('--side-by-side')
    args.append('--width=164')
  else:
    raise NotImplementedError

  if options.get('funout', 0):
    args.append('-p')

  if options.get('ignore_white', 0):
    args.append('-w')

  return args

class _diff_fp:
  """File object reading a diff between temporary files, cleaning up
  on close"""

  def __init__(self, temp1, temp2, info1=None, info2=None, diff_cmd='diff', diff_opts=[]):
    self.temp1 = temp1
    self.temp2 = temp2
    args = diff_opts[:]
    if info1 and info2:
      args.extend(["-L", self._label(info1), "-L", self._label(info2)])
    args.extend([temp1, temp2])
    self.fp = popen.popen(diff_cmd, args, "r")

  def read(self, bytes):
    return self.fp.read(bytes)

  def readline(self):
    return self.fp.readline()

  def close(self):
    try:
      if self.fp:
        self.fp.close()
        self.fp = None
    finally:
      try:
        if self.temp1:
          os.remove(self.temp1)
          self.temp1 = None
      finally:
        if self.temp2:
          os.remove(self.temp2)
          self.temp2 = None

  def __del__(self):
    self.close()

  def _label(self, (path, date, rev)):
    date = date and time.strftime('%Y/%m/%d %H:%M:%S', time.gmtime(date))
    return "%s\t%s\t%s" % (path, date, rev)


def check_root_access(repos):
  """Return 1 iff the associated username is permitted to read REPOS,
  as determined by consulting REPOS's Authorizer object (if any)."""

  auth = repos.authorizer()
  if not auth:
    return 1
  return auth.check_root_access(repos.rootname())
  
def check_path_access(repos, path_parts, pathtype=None, rev=None):
  """Return 1 iff the associated username is permitted to read
  revision REV of the path PATH_PARTS (of type PATHTYPE) in repository
  REPOS, as determined by consulting REPOS's Authorizer object (if any)."""

  auth = repos.authorizer()
  if not auth:
    return 1
  if not pathtype:
    pathtype = repos.itemtype(path_parts, rev)
  return auth.check_path_access(repos.rootname(), path_parts, pathtype, rev)

