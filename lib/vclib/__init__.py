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
    number or None if the entry doesn't have a number. And a "log_errors"
    list property will be set holding a list of error messages pertaining
    to the file. Other properties that may be set include "date", "author",
    and "log".

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    entries is a list of DirEntry objects returned from a previous call to
    the listdir() method

    options is a dictionary of implementation specific options
    """
  
  def filelog(self, path_parts, rev, options):
    """Retrieve a file's log information

    The result is a list of Revision objects

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]

    The rev parameter can be set to only retrieve log information for a
    specified revision, or it can be None to return information on all
    file revisions.

    options is a dictionary of implementation specific options
    """

# ======================================================================
class DirEntry:
  "Instances represent items in a directory listing"

  def __init__(self, name, kind, verboten=0):
    self.name = name
    self.kind = kind
    self.verboten = verboten

class Revision:
  """Instances holds information about file revisions"""
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
  def __init__(self, revision):
    if revision is None:
      revision = "(None)"
    Error.__init__(self, "Invalid revision " + str(revision))
