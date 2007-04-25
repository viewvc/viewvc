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

class ViewVCAuthorizer(vcauth.GenericViewVCAuthorizer):
  """The arbitrarily-less-than-fully-permissive authorizer (for testing)."""
  def __init__(self, username):
    self.roots = {}
    
  def register_root(self, rootname, rootpath, roottype):
    self.roots[rootname] = roottype
    
  def check_root_access(self, rootname):    
    if not self.roots.has_key(rootname):
      raise vcauth.ViewVCAuthzUnknownRootError
    if rootname == 'main':
      return 0
    return 1
  
  def check_file_access(self, rootname, path_parts, rev=None):
    if not self.roots.has_key(rootname):
      raise vcauth.ViewVCAuthzUnknownRootError
    if path_parts[-1] == 'index.html':
      return 0
    return 1
  
  def check_directory_access(self, rootname, path_parts, rev=None):
    if not self.roots.has_key(rootname):
      raise vcauth.ViewVCAuthzUnknownRootError
    if 'images' in path_parts:
      return 0
    return 1
