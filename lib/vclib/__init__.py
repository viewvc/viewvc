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


# item types returned by Repository.itemtype(). these values are also
# available as object.type where object is a Versfile or Versdir.
FILE = 'FILE'
DIR = 'DIR'

# Developers' note:
# The only class you need to derive to write a new driver for Versionlib
# is the Repository class.


# ======================================================================
#
# TODO: Add a last modified property
#
class Repository:
  """
  Abstract class representing a repository.
  
  Developers: This should be the only class to be derived to obtain an
  actual implementation of a versioning system.
  """

  # Public methods ( accessible from the upper layers )

  def getitem(self, path_parts):
    """Return the item (file or dir) at the given path.

    The result will be an instance of Versfile or Versdir. Before calling
    this method, you can also use .itemtype() to determine the type of
    the item at the given path.

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]
    """
    pass

  def itemtype(self, path_parts):
    """Return the type of the item (file or dir) at the given path.

    The result will be vclib.DIR or vclib.FILE

    The path is specified as a list of components, relative to the root
    of the repository. e.g. ["subdir1", "subdir2", "filename"]
    """
    pass

  # Private methods ( accessed by Versfile and Revision )

  def _getvf_files(self, path_parts):
    "Return a dictionary of versioned files. (name : Versfile)"
    pass

  def _getvf_subdirs(self, path_parts):
    "Return a dictionary of subdirectories. (name : Versdir)"
    pass

  def _getvf_info(self, target, path_parts):
    """
    This method will add to <target> (expect to be an instance of Versfile)
    a certain number of attributes:
    head (string)
    age (int timestamp)
    author (string)
    log
    branch
    ... ( there can be other stuff here)
    
    Developers: method to be overloaded.
    """

  def _getvf_tree(self, versfile):
    """
    should return a dictionary of Revisions
    Developers: method to be overloaded.
    """

  def _getvf_properties(self, target, path_parts, revisionnumber):
    """
    Add/update into target's attributes (expected to be an instance of
    Revision) a certain number of attributes:
    rev
    date
    author
    state
    log
    previous revision number
    branches ( a list of revision numbers )
    changes ( string of the form: e.g. "+1 -0 lines" )
    tags
    ... ( there can be other stuff here)
    
    Developers: in the cvs implementation, the method will never be called.
    There is no point in developping this method as  _getvf_tree already
    gets the properties.
    """

  def _getvf_cofile(self, target, path_parts):
    """
    should return a file object representing the checked out revision.
    Notice that _getvf_co can also add the properties in <target> the
    way _getvf_properties does.  

    Developers: method to be overloaded.
    """

# ======================================================================
class Versitem:
  pass
  
# ======================================================================

class Versdir(Versitem):
  "Instances represent directories within a repository."

  #
  # Note to developers: you do not need to derive this class.
  #

  type = DIR

  def __init__(self, repository, path_parts):
    assert isinstance(repository, Repository)

    self.repository = repository
    self.path = path_parts

  def getfiles(self):
    "Return a dictionary of versioned files. (name : Versfile)"
    return self.repository._getvf_files(self.path)

  def getsubdirs(self):
    "Return a dictionary of subdirectories. (name : Versdir)"
    return self.repository._getvf_subdirs(self.path)


# ======================================================================
    
class Versfile(Versitem):
  "Instances represent a (versioned) file within a repository."

  #
  # Note to developers: you do not need to derive this class.
  #

  type = FILE
  names = ("head", "age", "author", "log", "branch", "tags")

  def __init__(self, repository, path_parts, tree=None):
    "Called by Repository.getfile"

    assert isinstance(repository, Repository)

    self.repository = repository
    self.path = path_parts 
    
    if tree != None:
      self.tree = tree
      
  # if an attribute is not present in the dict of the instance, look for it in
  # the repository. Special treatment for the "tree" attribute.
  def __getattr__(self, name):
    if name == "tree":
      self.tree = self.repository._getvf_tree(self)
      return self.tree
    if name in self.names:
      self.repository._getvf_info(self, self.path)
      return self.__dict__[name]
    raise AttributeError()

  # private methods ( access from Revision's methods )
  def _getvf_properties(self, target, revisionnumber):
    return self.repository._getvf_properties(target, self.path, revisionnumber)

  def _getvf_cofile(self, target):
    return self.repository._getvf_cofile(target, self.path)

  
# ======================================================================

class Revision:
  "Instances represent a specific revision of a (versioned) file."

  #
  # Note to developers: you do not need to derive this class.
  #

  names = ("date", "author", "state", "log", "previous", "branches",
           "changes", "tags")

  def __init__(self, versfile, number):
    if not isinstance(versfile, Versfile):
      raise TypeError(versfile)	
    self.versfile = versfile
    self.rev = number
    
  # if an attribute is not present in the dict of the instance, look for it in
  # the repository. 
  def __getattr__(self, name):
    if name in self.names:
      self.versfile._getvf_properties(self, self.rev)
      return self.__dict__[name]
    raise AttributeError()    
  
  def checkout(self):
    return self.versfile._getvf_cofile(self)
    
  # Here are the shortcuts methods.
  def getprevious(self):
    return self.versfile.tree[self.previous]

  def getbranches(self):
    res = []
    for i in self.branches:
      res.append(self.versfile.tree[i])
    return res

  
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
