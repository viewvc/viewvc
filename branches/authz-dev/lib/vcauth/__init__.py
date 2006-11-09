# -*-python-*-
#
# Copyright (C) 2006 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

"""Generic API for implementing authorization checks employed by ViewVC."""

import string
import vclib


class GenericViewVCAuthorizer:
  """Abstract class encapsulating version control authorization routines."""
  
  def __init__(self, username):
    """Create a GenericViewVCAuthorizer object which will be used to
    validate that USERNAME has the permissions needed to view version
    control repositories and the items in them."""
    pass

  def register_root(self, rootname, rootpath, roottype):
    """Register the repository name ROOTNAME as one associated with
    the version control repository located at ROOTPATH and for the
    version control type ROOTTYPE.  Authorization checks are done
    against root names."""
    pass
  
  def check_root_access(self, rootname):
    """Return 1 iff the associated username is permitted to read the
    repository associated with ROOTNAME.

    Raise ViewVCAuthzUnknownRootError if ROOTNAME isn't registered."""
    pass
  
  def check_file_access(self, rootname, path_parts, rev=None):
    """Return 1 iff the associated username is permitted to read the
    file PATH_PARTS as it exists in revision REV in the repository
    associated with ROOTNAME.

    Raise ViewVCAuthzUnknownRootError if ROOTNAME isn't registered."""
    pass
        
  def check_directory_access(self, rootname, path_parts, rev=None):
    """Return 1 iff the associated username is permitted to read the
    directory PATH_PARTS as it exists in revision REV in the repository
    associated with ROOTNAME.

    Raise ViewVCAuthzUnknownRootError if ROOTNAME isn't registered."""
    pass


class ViewVCAuthzUnknownRootError(Exception):
  pass



##############################################################################

class ViewVCAuthorizer(GenericViewVCAuthorizer):
  """The uber-permissive authorizer."""
  def __init__(self, username):
    self.roots = {}
    
  def register_root(self, rootname, rootpath, roottype):
    self.roots[rootname] = roottype
    
  def check_root_access(self, rootname):    
    if not self.roots.has_key(rootname):
      raise ViewVCAuthzUnknownRootError
    return 1
  
  def check_file_access(self, rootname, path_parts, rev=None):
    if not self.roots.has_key(rootname):
      raise ViewVCAuthzUnknownRootError
    return 1
  
  def check_directory_access(self, rootname, path_parts, rev=None):
    if not self.roots.has_key(rootname):
      raise ViewVCAuthzUnknownRootError
    return 1
