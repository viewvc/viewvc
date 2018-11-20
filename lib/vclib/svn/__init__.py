# -*-python-*-
#
# Copyright (C) 1999-2018 The ViewCVS Group. All Rights Reserved.
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

from vclib import ReposNotFound

MODULE_SWIG_BINDINGS = 'swig_py'
MODULE_COMMAND_LINE  = 'cmdline'
access_module          = None
default_access_module  = MODULE_SWIG_BINDINGS
fallback_access_module = MODULE_COMMAND_LINE

_re_url = re.compile('^(http|https|file|svn|svn\+[^:]+)://')

def _canonicalize_path(path):
  global access_module, _canonicalize_path
  if (   access_module == MODULE_SWIG_BINDINGS
      or (    access_module is None
          and default_access_module == MODULE_SWIG_BINDINGS)):
    try:
      import svn.core
      access_module = MODULE_SWIG_BINDINGS
      _canonicalize_path = svn.core.svn_path_canonicalize
      return svn.core.svn_path_canonicalize(path)
    except AttributeError:
      # svn_path_canonicalize() appeared in 1.4.0 bindings
      pass
    except ImportError:
      # and it may be not available swig Python binding.
      # use (experimental) fallback implementation
      access_module = fallback_access_module

  # There's so much more that we *could* do here, but if we're
  # here at all its because there's a really old Subversion in
  # place, and those older Subversion versions cared quite a bit
  # less about the specifics of path canonicalization.
  def _canonicalize_path_internal(path):
    if _re_url.search(path):
      return path.rstrip('/')
    else:
      return os.path.normpath(path)
  _canonicalize_path = _canonicalize_path_internal
  return _canonicalize_path_internal(path)

def canonicalize_rootpath(rootpath):
  # Try to canonicalize the rootpath using Subversion semantics.
  rootpath = _canonicalize_path(rootpath)

  # ViewVC's support for local repositories is more complete and more
  # performant than its support for remote ones, so if we're on a
  # Unix-y system and we have a file:/// URL, convert it to a local
  # path instead.
  if os.name == 'posix':
    rootpath_lower = rootpath.lower()
    if rootpath_lower in ['file://localhost',
                          'file://localhost/',
                          'file://',
                          'file:///'
                          ]:
      return '/'
    if rootpath_lower.startswith('file://localhost/'):
      rootpath = os.path.normpath(urllib.unquote(rootpath[16:]))
    elif rootpath_lower.startswith('file:///'):
      rootpath = os.path.normpath(urllib.unquote(rootpath[7:]))

  # Ensure that we have an absolute path (or URL), and return.
  if not re.search(_re_url, rootpath):
    assert os.path.isabs(rootpath)
  return rootpath


def expand_root_parent(parent_path):
  roots = {}
  if re.search(_re_url, parent_path):
    pass
  else:
    # Any subdirectories of PARENT_PATH which themselves have a child
    # "format" are returned as roots.
    assert os.path.isabs(parent_path)
    subpaths = os.listdir(parent_path)
    for rootname in subpaths:
      rootpath = os.path.join(parent_path, rootname)
      if os.path.exists(os.path.join(rootpath, "format")):
        roots[rootname] = canonicalize_rootpath(rootpath)
  return roots


def find_root_in_parent(parent_path, rootname):
  """Search PARENT_PATH for a root named ROOTNAME, returning the
  canonicalized ROOTPATH of the root if found; return None if no such
  root is found."""

  if not re.search(_re_url, parent_path):
    assert os.path.isabs(parent_path)
    rootpath = os.path.join(parent_path, rootname)
    format_path = os.path.join(rootpath, "format")
    if os.path.exists(format_path):
      return canonicalize_rootpath(rootpath)
  return None


def SubversionRepository(name, rootpath, authorizer, utilities, config_dir):
  rootpath = canonicalize_rootpath(rootpath)
  if access_module == MODULE_SWIG_BINDINGS:
    if re.search(_re_url, rootpath):
      import svn_ra
      return svn_ra.RemoteSubversionRepository(name, rootpath, authorizer,
                                               utilities, config_dir)
    else:
      import svn_repos
      return svn_repos.LocalSubversionRepository(name, rootpath, authorizer,
                                                 utilities, config_dir)
  elif access_module == MODULE_COMMAND_LINE:
    import svn_commandline
    return svn_commandline.CmdLineSubversionRepository(name, rootpath,
                                                       authorizer,
                                                       utilities, config_dir)
  else:
    raise ReposNotFound('no module to access Subversion Repository is'
                        'available')
