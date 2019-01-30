# -*-python-*-
#
# Copyright (C) 2006-2015 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

import vcauth
import os.path
import debug
import svn.repos

class ViewVCAuthorizer(vcauth.GenericViewVCAuthorizer):
  """Native Subversion authorizer module"""

  def __init__(self, root_lookup_func, username, params={}):
    self.root_authz_info = { }  # {root -> svn_authz_t}
    self.root_lookup_func = root_lookup_func

    # Get the authz file location from exactly one of our related
    # passed-in parameters.
    self.authz_file = params.get('authzfile')
    self.rel_authz_file = params.get('root_relative_authzfile')
    if not (self.authz_file or self.rel_authz_file):
      raise debug.ViewVCException("No authzfile configured")
    if self.authz_file and self.rel_authz_file:
      raise debug.ViewVCException("Multiple authzfile locations defined")

    # See if the admin wants us to do case normalization of usernames.
    self.force_username_case = params.get('force_username_case')
    if self.force_username_case == 'upper':
      self.username = username and username.upper() or username
    elif self.force_username_case == 'lower':
      self.username = username and username.lower() or username
    elif not self.force_username_case:
      self.username = username
    else:
      raise debug.ViewVCException("Invalid value for force_username_case "
                                  "option")

  def _get_authz_file(self, rootname):
    if self.rel_authz_file:
      roottype, rootpath = self.root_lookup_func(rootname)
      return os.path.join(rootpath, self.rel_authz_file)
    else:
      return self.authz_file

  def _get_authz_info(self, rootname):
    if not self.root_authz_info.has_key(rootname):
      try:
        self.root_authz_info[rootname] = \
            svn.repos.authz_read(self._get_authz_file(rootname), False)
      except Exception, e:
        raise debug.ViewVCException("Unable to parse configured authzfile "
                                    "file: %s" % (str(e)))
    return self.root_authz_info[rootname]

  def check_root_access(self, rootname):
    # TODO: Can we decline access to a root altogether?
    return 1

  def check_universal_access(self, rootname):
    return None

  def check_path_access(self, rootname, path_parts, pathtype, rev=None):
    return svn.repos.authz_check_access(self._get_authz_info(rootname),
                                        rootname,
                                        '/' + '/'.join(path_parts),
                                        self.username,
                                        svn.repos.svn_authz_read)
