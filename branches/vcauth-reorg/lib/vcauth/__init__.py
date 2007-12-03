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
  
  def __init__(self, username=None, params={}):
    """Create a GenericViewVCAuthorizer object which will be used to
    validate that USERNAME has the permissions needed to view version
    control repository ROOT (in whole or in part).  PARAMS is a
    dictionary of custom parameters for the authorizer."""
    pass

  def check_root_access(self, root):
    """Return 1 iff the associated username is permitted to read ROOT
    (which is a vclib.Repository() object)."""
    pass
  
  def check_path_access(self, root, path_parts, rev=None):
    """Return 1 iff the associated username is permitted to read
    revision REV of the path PATH_PARTS in repository ROOT."""
    pass



##############################################################################

class ViewVCAuthorizer(GenericViewVCAuthorizer):
  """The uber-permissive authorizer."""
  def check_root_access(self, root):
    return 1
    
  def check_path_access(self, root, path_parts, rev=None):
    return 1
