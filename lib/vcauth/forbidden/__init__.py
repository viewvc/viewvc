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
import vcauth
import vclib
import fnmatch
import string

class ViewVCAuthorizer(vcauth.GenericViewVCAuthorizer):
  """A simple top-level module authorizer."""
  def __init__(self, username, root, params={}):
    forbidden = params.get('forbidden', '')
    self.root = root
    self.forbidden = map(string.strip,
                         filter(None, string.split(forbidden, ',')))
    
  def check_path_access(self, path_parts, rev=None):
    # No path?  No problem.
    if not path_parts:
      return 1

    # If we have a single path part, we can't tell if this is a file
    # or a directory.  So we ask our version control system.  If it's
    # not a directory, we don't care about it.
    if len(path_parts) == 1:
      if self.root.itemtype(path_parts, rev) != vclib.DIR:
        return 1

    # At this point we're looking a path we believe to be a directory.
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
