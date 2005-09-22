# -*-python-*-
#
#
# Copyright (C) 1999-2002 The ViewCVS Group. All Rights Reserved.
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

"""Version Control lib is an abstract API to access versioning systems
such as CVS.
"""

import string


# item types returned by Repository.itemtype().
FILE = 'FILE'
DIR = 'DIR'

# diff types recognized by Repository.rawdiff().
UNIFIED = 1
CONTEXT = 2
SIDE_BY_SIDE = 3

# ======================================================================
#
class Repository:
  """Abstract class representing a repository."""

  def itemtype(self, path_parts):
    """Return the type of the item (file or dir) at the given path.

    The result will be vclib.DIR or vclib.FILE

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]
    """
    pass

  def openfile(self, path_parts, rev=None):
    """Open a file object to read file contents at a given path and revision.

    The return value is a 2-tuple of containg the file object and revision
    number in canonical form.

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    The revision number can be None to access a default revision.  
    """

  def listdir(self, path_parts, options):
    """Return list of files in a directory

    The result is a list of DirEntry objects

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    options is a dictionary of implementation specific options
    """

  def dirlogs(self, path_parts, entries, options):
    """Augment directory entries with log information

    New properties will be set on all of the DirEntry objects in the entries
    list. At the very least, a "rev" property will be set to a revision
    number or None if the entry doesn't have a number. Other properties that
    may be set include "date", "author", and "log".

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    entries is a list of DirEntry objects returned from a previous call to
    the listdir() method

    options is a dictionary of implementation specific options
    """
  
  def itemlog(self, path_parts, rev, options):
    """Retrieve an item's log information

    The result is a list of Revision objects

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    The rev parameter can be set to only retrieve log information for a
    specified revision, or it can be None to return information on all
    file revisions.

    options is a dictionary of implementation specific options
    """

  def rawdiff(self, path1, rev1, path2, rev2, type, options={}):
    """Return a diff (in GNU diff format) of two file revisions

    type is the requested diff type (UNIFIED, CONTEXT, etc)

    options is a dictionary that can contain the following options plus
    implementation-specific options

      context - integer, number of context lines to include
      funout - boolean, include C function names
      ignore_white - boolean, ignore whitespace

    Return value is a python file object
    """


# ======================================================================
class DirEntry:
  "Instances represent items in a directory listing"

  def __init__(self, name, kind, errors=[]):
    self.name = name
    self.kind = kind
    self.errors = errors

class Revision:
  """Instances holds information about revisions of versioned resources"""

  """Create a new Revision() item:
        NUMBER:  Revision in an integer-based, sortable format
        STRING:  Revision as a string
        DATE:  Seconds since Epoch (GMT) that this revision was created
        AUTHOR:  Author of the revision
        CHANGED:  Lines-changed (contextual diff) information
        LOG:  Log message associated with the creation of this revision
        SIZE:  Size (in bytes) of this revision's fulltext (files only)
  """
  def __init__(self, number, string, date, author, changed, log, size):
    self.number = number
    self.string = string
    self.date = date
    self.author = author
    self.changed = changed
    self.log = log
    self.size = size

  def __cmp__(self, other):
    return cmp(self.number, other.number)

# ======================================================================

class Error(Exception):
  pass
class ReposNotFound(Error):
  pass
class ItemNotFound(Error):
  def __init__(self, path_parts):
    # use '/' rather than os.sep because this is for user consumption, and
    # it was defined using URL separators
    Error.__init__(self, string.join(path_parts, '/'))
class InvalidRevision(Error):
  def __init__(self, revision=None):
    if revision is None:
      Error.__init__(self, "Invalid revision")
    else:
      Error.__init__(self, "Invalid revision " + str(revision))

# ======================================================================
# Implementation code used by multiple vclib modules

def _diff_args(type, options):
  """generate argument list to pass to diff or rcsdiff"""
  args = []
  if type == CONTEXT:
    if options.has_key('context'):
      args.append('--context=%i' % options['context'])
    else:
      args.append('-c')
  elif type == UNIFIED:
    if options.has_key('context'):
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

