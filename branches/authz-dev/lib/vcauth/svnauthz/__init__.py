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
# (c) 2006 Sergey Lapin <slapin@dataart.com>

import vcauth

from ConfigParser import ConfigParser

class ViewVCAuthorizer(vcauth.GenericViewVCAuthorizer):
  """Subversion authz authorizer module"""
  
  def __init__(self, username, rootname, rootpath, roottype, params={}):
    self.params = params.copy()
    self.available = []

    cp = ConfigParser()
    groups = []

    ### FIXME:  Can't have hard-coded paths in here, obviously.
    cp.read('/etc/apache2/dav_svn.authz')

    # Figure out which groups USERNAME has a part of.
    if cp.has_section('groups'):
      for group in cp.options('groups'):
        for user in cp.get('groups', group).split(','):
          if username == user.strip():
            groups.append(group.strip())

    # Read the other (non-"groups") sections, and figure out in which
    # repositories USERNAME or his groups have read rights.
    for section in cp.sections():
      if section == 'groups':
        continue
      for opt in cp.options(section):
        val = cp.get(section, opt).strip()
        opt = opt.strip()
        if not (val == "r" or val == "rw"):
          continue
        if opt == '*' \
           or opt == username \
           or (opt[0:1] == "@" and opt[1:] in groups):
          root, path = section.split(':')
          if root == rootname:
            self.available.append(path)

    # No available paths means no access.
    if not self.available:
      raise vcauth.ViewVCRootAccessNotAuthorized(rootname, username)

  def _check_path_access(self, path_parts):
    # If access to ROOTNAME is authorized, and PATH_PARTS is, or is
    # the child of, any of the allowed paths under this root,
    # authorize the access.
    path = '/' + path_parts.join('/')
    for allowpath in self.available:
      if path == allowpath or path.find(allowpath + '/') == 0:
       return 1
    return 0

  def check_file_access(self, path_parts, rev=None):
    return self._check_path_access(path_parts)
    
  def check_directory_access(self, path_parts, rev=None):
    return self._check_path_access(path_parts)
