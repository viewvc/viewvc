# -*-python-*-
#
# Copyright (C) 1999-2008 The ViewCVS Group. All Rights Reserved.
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


def canonicalize_rootpath(rootpath):
  return os.path.normpath(rootpath)


def expand_root_parent(parent_path):
  # Each subdirectory of PARENT_PATH that contains a child
  # "CVSROOT/config" is added the set of returned roots.  Or, if the
  # PARENT_PATH itself contains a child "CVSROOT/config", then all its
  # subdirectories are returned as roots.
  roots = {}
  subpaths = os.listdir(parent_path)
  cvsroot = os.path.exists(os.path.join(parent_path, "CVSROOT", "config"))
  for rootname in subpaths:
    rootpath = os.path.join(parent_path, rootname)
    if cvsroot \
       or (os.path.exists(os.path.join(rootpath, "CVSROOT", "config"))):
      roots[rootname] = canonicalize_rootpath(rootpath)
  return roots


def CVSRepository(name, rootpath, authorizer, utilities, use_rcsparse):
  rootpath = canonicalize_rootpath(rootpath)
  if use_rcsparse:
    import ccvs
    return ccvs.CCVSRepository(name, rootpath, authorizer, utilities)
  else:
    import bincvs
    return bincvs.BinCVSRepository(name, rootpath, authorizer, utilities)
