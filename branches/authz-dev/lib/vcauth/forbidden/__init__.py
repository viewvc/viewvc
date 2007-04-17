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
import fnmatch
import string

class ViewVCAuthorizer(vcauth.GenericViewVCAuthorizer):
  """A simple top-level module authorizer."""
  def __init__(self, username, rootname, rootpath, roottype, params={}):
    forbidden = params['forbidden']
    self.forbidden = map(string.strip,
                         filter(None, string.split(forbidden, ',')))
    
  def check_file_access(self, path_parts, rev=None):
    return 1
  
  def check_directory_access(self, path_parts, rev=None):
    if not path_parts:
      return 1
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
