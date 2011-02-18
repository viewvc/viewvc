# -*-python-*-
#
# Copyright (C) 1999-2011 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

"Version Control lib driver for Subversion repositories"

import os
import os.path
import re
import urllib

_re_url = re.compile('^(http|https|file|svn|svn\+[^:]+)://')

def canonicalize_rootpath(rootpath):
  try:
    import svn.core
    return svn.core.svn_path_canonicalize(rootpath)
  except:
    if os.name == 'posix':
      rootpath_lower = rootpath.lower()
      if rootpath_lower in ['file://localhost',
                            'file://localhost/',
                            'file://',
                            'file:///'
                            ]:
        return '/'
      if rootpath_lower.startswith('file://localhost/'):
        return os.path.normpath(urllib.unquote(rootpath[16:]))
      elif rootpath_lower.startswith('file:///'):
        return os.path.normpath(urllib.unquote(rootpath[7:]))
    if re.search(_re_url, rootpath):
      return rootpath.rstrip('/')
    return os.path.normpath(rootpath)


def expand_root_parent(parent_path):
  roots = {}
  if re.search(_re_url, parent_path):
    pass
  else:
    # Any subdirectories of PARENT_PATH which themselves have a child
    # "format" are returned as roots.
    subpaths = os.listdir(parent_path)
    for rootname in subpaths:
      rootpath = os.path.join(parent_path, rootname)
      if os.path.exists(os.path.join(rootpath, "format")):
        roots[rootname] = canonicalize_rootpath(rootpath)
  return roots


def SubversionRepository(name, rootpath, authorizer, utilities, config_dir):
  rootpath = canonicalize_rootpath(rootpath)
  if re.search(_re_url, rootpath):
    import svn_ra
    return svn_ra.RemoteSubversionRepository(name, rootpath, authorizer,
                                             utilities, config_dir)
  else:
    import svn_repos
    return svn_repos.LocalSubversionRepository(name, rootpath, authorizer,
                                               utilities, config_dir)
