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

import vcauth
from typing import Union, Dict
from vclib import UnsupportedFeature, Repository


class GitRepository(Repository):
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


def canonicalize_rootpath(rootpath: str) -> str:
    raise UnsupportedFeature("Git driver is not available")


def expand_root_parent(parent_path: str, path_encoding: str) -> Dict[str, str]:
    raise UnsupportedFeature("Git driver is not available")


def find_root_in_parent(parent_path: str, rootname: str, path_encoding: str) -> Union[str, None]:
    """Search PARENT_PATH for a root named ROOTNAME, returning the
    canonicalized ROOTPATH of the root if found; return None if no such
    root is found."""

    raise UnsupportedFeature("Git driver is not available")
