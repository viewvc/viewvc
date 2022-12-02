# -*-python-*-
#
# Copyright (C) 1999-2021 The ViewCVS Group. All Rights Reserved.
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
from vclib import _getfspath, os_listdir


def cvs_strptime(timestr):
    return time.strptime(timestr, "%Y/%m/%d %H:%M:%S")[:-1] + (0,)


def canonicalize_rootpath(rootpath):
    assert os.path.isabs(rootpath)
    return os.path.normpath(rootpath)


def _is_cvsroot(path, path_encoding):
    return os.path.exists(_getfspath(os.path.join(path, "CVSROOT", "config"),
                                     path_encoding))


def expand_root_parent(parent_path, path_encoding):
    # Each subdirectory of PARENT_PATH that contains a child
    # "CVSROOT/config" is added the set of returned roots.  Or, if the
    # PARENT_PATH itself contains a child "CVSROOT/config", then all its
    # subdirectories are returned as roots.
    assert os.path.isabs(parent_path)
    roots = {}
    subpaths = os_listdir(parent_path, path_encoding)
    if _is_cvsroot(parent_path, path_encoding):
        # The children are all roots
        for rootname in subpaths:
            rootpath = os.path.join(parent_path, rootname)
            roots[rootname] = canonicalize_rootpath(rootpath)
    else:
        for rootname in subpaths:
            rootpath = os.path.join(parent_path, rootname)
            if _is_cvsroot(rootpath, path_encoding):
                roots[rootname] = canonicalize_rootpath(rootpath)
    return roots


def find_root_in_parent(parent_path, rootname, path_encoding):
    """Search PARENT_PATH for a root named ROOTNAME, returning the
    canonicalized ROOTPATH of the root if found; return None if no such
    root is found."""
    # Is PARENT_PATH itself a CVS repository?  If so, we allow ROOTNAME
    # to be any subdir within it.  Otherwise, we expect
    # PARENT_PATH/ROOTNAME to be a CVS repository.
    assert os.path.isabs(parent_path)
    rootpath = os.path.join(parent_path, rootname)
    if ((_is_cvsroot(parent_path, path_encoding)
         and os.path.exists(_getfspath(rootpath, path_encoding)))
        or _is_cvsroot(rootpath, path_encoding)):
        return canonicalize_rootpath(rootpath)
    return None


def CVSRepository(name, rootpath, authorizer, utilities, use_rcsparse,
                  content_encoding, path_encoding):
    rootpath = canonicalize_rootpath(rootpath)
    if use_rcsparse:
        from . import ccvs

        return ccvs.CCVSRepository(name, rootpath, authorizer, utilities,
                                   content_encoding, path_encoding)
    else:
        from . import bincvs

        return bincvs.BinCVSRepository(name, rootpath, authorizer, utilities,
                                       content_encoding, path_encoding)
