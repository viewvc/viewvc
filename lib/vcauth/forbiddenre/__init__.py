# -*-python-*-
#
# Copyright (C) 2008-2025 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
import vcauth
import vclib
import re


def _split_regexp(restr):
    """Return a 2-tuple consisting of a compiled regular expression
    object and a boolean flag indicating if that object should be
    interpreted inversely."""
    if restr[0] == "!":
        return re.compile(restr[1:]), 1
    return re.compile(restr), 0


class ViewVCAuthorizer(vcauth.GenericViewVCAuthorizer):
    """A simple regular-expression-based authorizer."""

    def __init__(self, root_lookup_func, username, params={}):
        forbidden = params.get("forbiddenre", "")
        self.forbidden = [_split_regexp(x.strip()) for x in forbidden.split(",") if x.strip()]

    def _check_root_path_access(self, root_path):
        default = 1
        for forbidden, negated in self.forbidden:
            if negated:
                default = 0
                if forbidden.search(root_path):
                    return 1
            elif forbidden.search(root_path):
                return 0
        return default

    def check_root_access(self, rootname):
        return self._check_root_path_access(rootname)

    def check_universal_access(self, rootname):
        # If there aren't any forbidden regexps, we can grant universal
        # read access.  Otherwise, we make no claim.
        if not self.forbidden:
            return 1
        return None

    def check_path_access(self, rootname, path_parts, pathtype, rev=None):
        root_path = rootname
        if path_parts:
            root_path = root_path + "/" + "/".join(path_parts)
            if pathtype == vclib.DIR:
                root_path = root_path + "/"
        else:
            root_path = root_path + "/"
        return self._check_root_path_access(root_path)
