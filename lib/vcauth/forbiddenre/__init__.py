# -*-python-*-
#
# Copyright (C) 2008-2010 The ViewCVS Group. All Rights Reserved.
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
import re


def _split_regexp(restr):
  """Return a 2-tuple consisting of a compiled regular expression
  object and a boolean flag indicating if that object should be
  interpreted inversely."""
  if restr[0] == '!':
    return re.compile(restr[1:]), 1
  return re.compile(restr), 0


class ViewVCAuthorizer(vcauth.GenericViewVCAuthorizer):
  """A simple regular-expression-based authorizer."""
  def __init__(self, username, params={}):
    forbidden = params.get('forbiddenre', '')
    self.forbidden = map(lambda x: _split_regexp(string.strip(x)),
                         filter(None, string.split(forbidden, ',')))
                         
  def _check_root_path_access(self, root_path):
    default = 1
    for forbidden, negated in self.forbidden:
      if negated:
        default = 0
        if forbidden.search(root_path):
          return 1
      elif forbidden.search(root_path):
        return 0
    return default
      
  def check_root_access(self, rootname):
    return self._check_root_path_access(rootname)
  
  def check_universal_access(self, rootname):
    # If there aren't any forbidden regexps, we can grant universal
    # read access.  Otherwise, we make no claim.
    if not self.forbidden:
      return 1
    return None
    
  def check_path_access(self, rootname, path_parts, pathtype, rev=None):
    root_path = rootname
    if path_parts:
      root_path = root_path + '/' + string.join(path_parts, '/')
      if pathtype == vclib.DIR:
        root_path = root_path + '/'
    else:
      root_path = root_path + '/'
    return self._check_root_path_access(root_path)
    
