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

GitRepository: type

try:
    from .git_pygit2 import (
        canonicalize_rootpath,
        expand_root_parent,
        find_root_in_parent,
        GitRepository,
    )
except ImportError:
    from .git_null import (
        canonicalize_rootpath,
        expand_root_parent,
        find_root_in_parent,
        GitRepository,
    )

__all__ = ["canonicalize_rootpath", "expand_root_parent", "find_root_in_parent", "GitRepository"]
