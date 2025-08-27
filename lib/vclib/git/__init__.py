# -*-python-*-
#
# Copyright (C) 1999-2025 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

import os.path
import vcauth
from typing import Union, Dict
from vclib import os_listdir, ReposNotFound, UnsupportedFeature, Repository

_git_available: bool = False
GitRepository: type

try:
    import pygit2
    from .git_repos import GitRepository as _pygit2GitRepository

    _git_available = True
    GitRepository = _pygit2GitRepository
except ImportError:

    class _GitRepository(Repository):
        def __init__(
            self,
            name: str,
            rootpath: str,
            authorizer: Union[vcauth.GenericViewVCAuthorizer, None],
            utilities,
            content_encoding: str,
            path_encoding: str,
            default_branch: Union[str, None] = None,
        ):
            raise UnsupportedFeature("Git driver is not available")

    GitRepository = _GitRepository

__all__ = ["canonicalize_rootpath", "expand_root_parent", "find_root_in_parent", "GitRepository"]


def canonicalize_rootpath(rootpath: str) -> str:
    if not _git_available:
        raise UnsupportedFeature("Git driver is not available")
    rp = pygit2.discover_repository(rootpath)
    if rp is None:
        raise ReposNotFound(f"Cannot find Git Repository: {rootpath}")
    return rp[:-1]


def expand_root_parent(parent_path: str, path_encoding: str) -> Dict[str, str]:
    if not _git_available:
        raise UnsupportedFeature("Git driver is not available")
    roots: Dict[str, str] = {}
    subpaths = os_listdir(parent_path, path_encoding)
    for rootname in subpaths:
        rootpath = os.path.join(parent_path, rootname)
        rp = pygit2.discover_repository(rootpath)
        if rp is not None:
            roots[rootname] = rp[:-1]
    return roots


def find_root_in_parent(parent_path, rootname, path_encoding):
    """Search PARENT_PATH for a root named ROOTNAME, returning the
    canonicalized ROOTPATH of the root if found; return None if no such
    root is found."""

    if not _git_available:
        raise UnsupportedFeature("Git driver is not available")
    assert os.path.isabs(parent_path)
    rootpath = os.path.join(parent_path, rootname)
    rp = pygit2.discover_repository(rootpath)
    return None if rp is None else rp[:-1]
