# -*-python-*-
#
# Copyright (C) 2006-2010 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
import vcauth
import vclib
import fnmatch
import string

class ViewVCAuthorizer(vcauth.GenericViewVCAuthorizer):
  """A simple top-level module authorizer."""
  def __init__(self, username, params={}):
    forbidden = params.get('forbidden', '')
    self.forbidden = map(string.strip,
                         filter(None, string.split(forbidden, ',')))

  def check_root_access(self, rootname):
    return 1

  def check_universal_access(self, rootname):
    # If there aren't any forbidden paths, we can grant universal read
    # access.  Otherwise, we make no claim.
    if not self.forbidden:
      return 1
    return None
    
  def check_path_access(self, rootname, path_parts, pathtype, rev=None):
    # No path?  No problem.
    if not path_parts:
      return 1

    # Not a directory?  We aren't interested.
    if pathtype != vclib.DIR:
      return 1

    # At this point we're looking at a directory path.
    module = path_parts[0]
    default = 1
    for pat in self.forbidden:
      if pat[0] == '!':
        default = 0
        if fnmatch.fnmatchcase(module, pat[1:]):
          return 1
      elif fnmatch.fnmatchcase(module, pat):
        return 0
    return default
