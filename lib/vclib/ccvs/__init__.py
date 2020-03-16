# -*-python-*-
#
# Copyright (C) 1999-2020 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
import os
import os.path
import time


def cvs_strptime(timestr):
  return time.strptime(timestr, '%Y/%m/%d %H:%M:%S')[:-1] + (0,)


def canonicalize_rootpath(rootpath):
  assert os.path.isabs(rootpath)
  return os.path.normpath(rootpath)


def _is_cvsroot(path):
  return os.path.exists(os.path.join(path, "CVSROOT", "config"))


def expand_root_parent(parent_path):
  # Each subdirectory of PARENT_PATH that contains a child
  # "CVSROOT/config" is added the set of returned roots.  Or, if the
  # PARENT_PATH itself contains a child "CVSROOT/config", then all its
  # subdirectories are returned as roots.
  assert os.path.isabs(parent_path)
  roots = {}
  subpaths = os.listdir(parent_path)
  for rootname in subpaths:
    rootpath = os.path.join(parent_path, rootname)
    if _is_cvsroot(parent_path) or _is_cvsroot(rootpath):
      roots[rootname] = canonicalize_rootpath(rootpath)
  return roots


def find_root_in_parent(parent_path, rootname):
  """Search PARENT_PATH for a root named ROOTNAME, returning the
  canonicalized ROOTPATH of the root if found; return None if no such
  root is found."""
  # Is PARENT_PATH itself a CVS repository?  If so, we allow ROOTNAME
  # to be any subdir within it.  Otherwise, we expect
  # PARENT_PATH/ROOTNAME to be a CVS repository.
  assert os.path.isabs(parent_path)
  rootpath = os.path.join(parent_path, rootname)
  if (_is_cvsroot(parent_path) and os.path.exists(rootpath)) \
     or _is_cvsroot(rootpath):
    return canonicalize_rootpath(rootpath)
  return None


def CVSRepository(name, rootpath, authorizer, utilities, use_rcsparse):
  rootpath = canonicalize_rootpath(rootpath)
  if use_rcsparse:
    from . import ccvs
    return ccvs.CCVSRepository(name, rootpath, authorizer, utilities)
  else:
    from . import bincvs
    return bincvs.BinCVSRepository(name, rootpath, authorizer, utilities)
