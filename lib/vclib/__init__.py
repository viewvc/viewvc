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
  def getfile(self, path):
    """
    return the versioned file at <path> ( instance of Versfile )
    Path should be of the form:
    ["Subdir1","Subdir2","filename"]
    """

  def getfiles(self, path):
    """
    return a dictionary of versioned files. (instance of Versfile )
    """

  def getsubdirs(self, path):
    """
    return the list of the subdirectories in <path> as a list of strings
    """
  
  # Private methods ( accessed by Versfile and Revision )
  
  def _getvf_info(self, target, path):
    """
    This method will had to <target> (expect to be an instance of Versfile)
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

  def _getvf_properties(self, target, path, revisionnumber):
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

  def _getvf_cofile(self, target, path):
    """
    should return a file object representing the checked out revision.
    Notice that _getvf_co can also add the properties in <target> the
    way _getvf_properties does.  

    Developers: method to be overloaded.
    """


# ======================================================================
    
class Versfile:
  """
  class representing a versioned file.
  
  Developers: You do not need to derive this class.
  """

  names = ("head", "age", "author", "log", "branch", "tags")

  def __init__(self, repository, path, tree=None):
    """
    Called by Repository.getfile
    """
    if not isinstance(repository, Repository):
      raise TypeError(repository)
    self.repository = repository
    self.path = path
    
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
  """
  This class represents a revision of a versioned file.
  
  Developers: You do not need to derive this class.
  """

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
      self.versfile._getvf_properties(self,self.rev)
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
