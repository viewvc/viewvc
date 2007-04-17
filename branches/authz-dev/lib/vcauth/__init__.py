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
  
  def __init__(self, username, rootname, rootpath, roottype, params={}):
    """Create a GenericViewVCAuthorizer object which will be used to
    validate that USERNAME has the permissions needed to view version
    control repository named ROOTNAME (of type ROOTTYPE, and located at
    ROOTPATH).  PARAMS is a dictionary of custom parameters for the
    authorizer.

    Raise ViewVCRootAccessNotAuthorized error if USERNAME isn't
    allowed to see this repository at all."""
    pass

  def check_file_access(self, path_parts, rev=None):
    """Return 1 iff the associated username is permitted to read
    revision REV of the file PATH_PARTS in the repository associated
    with this authorizer."""
    pass
        
  def check_directory_access(self, path_parts, rev=None):
    """Return 1 iff the associated username is permitted to read
    revision REV of the directory PATH_PARTS in the repository associated
    with this authorizer."""
    pass


class ViewVCRootAccessNotAuthorized(Exception):
  def __init__(self, rootname, username):
    self.rootname = rootname
    self.username = username
  def __str__(self):
    return "Access to root '%s' by user '%s' is denied." \
           % (self.rootname, self.username)



##############################################################################

class ViewVCAuthorizer(GenericViewVCAuthorizer):
  """The uber-permissive authorizer."""
  def __init__(self):
    pass
    
  def check_file_access(self, path_parts, rev=None):
    return 1
  
  def check_directory_access(self, path_parts, rev=None):
    return 1
