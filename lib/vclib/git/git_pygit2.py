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

"Version Control lib driver for locally accessible Git repositories"

import sys
import os
import os.path
import re
import tempfile
import vclib
import vcauth
import datetime
import pygit2

from collections.abc import Iterable
from typing import Any

from pygit2.enums import SortMode, BlameFlag


BUFSIZE = 8192
TAG_RE = re.compile(r"^refs/tags/")

_node_typemap = {"tree": vclib.DIR, "blob": vclib.FILE}


# -- functions export to __init__.py -- #


def canonicalize_rootpath(rootpath: str) -> str:
    rp = pygit2.discover_repository(rootpath)
    if rp is None:
        raise vclib.ReposNotFound(f"Cannot find Git Repository: {rootpath}")
    return rp[:-1]


def expand_root_parent(parent_path: str, path_encoding: str) -> dict[str, str]:
    roots: dict[str, str] = {}
    subpaths = vclib.os_listdir(parent_path, path_encoding)
    for rootname in subpaths:
        rootpath = os.path.join(parent_path, rootname)
        rp = pygit2.discover_repository(rootpath)
        if rp is not None:
            roots[rootname] = rp[:-1]
    return roots


def find_root_in_parent(parent_path: str, rootname: str, path_encoding: str) -> str | None:
    """Search PARENT_PATH for a root named ROOTNAME, returning the
    canonicalized ROOTPATH of the root if found; return None if no such
    root is found."""

    assert os.path.isabs(parent_path)
    rootpath = os.path.join(parent_path, rootname)
    rp = pygit2.discover_repository(rootpath)
    return None if rp is None else rp[:-1]


# -- for internal use -- #


def _path_parts(path: str) -> list[str]:
    """Split up a repository path into a list of path components"""
    # clean it up. this removes duplicate '/' characters and any that may
    # exist at the front or end of the path.
    return [pp for pp in path.split("/") if pp]


def _get_tree_entry(tree: pygit2.Tree, key: str) -> pygit2.Tree | pygit2.Blob | None:
    if not key:
        return tree
    obj = tree[key] if key in tree else None
    if obj is not None and not isinstance(
        obj,
        (
            pygit2.Tree,
            pygit2.Blob,
        ),
    ):
        raise vclib.Error(f"Internal error: unexpected object type {type(obj)} in Tree")
    return obj


class DirEntry(vclib.DirEntry):
    rev: str | None
    log: str | None
    author: str | None
    date: int | None
    size: int | None
    lockinfo: None = None


class Revision(vclib.Revision):
    "Hold state for each revision's log entry."

    prev: str | None

    def __init__(
        self,
        commit: str,
        timestamp: int,
        author: str,
        log: str,
        size: int | None,
        filename: str,
        parents: list[str],
    ):
        vclib.Revision.__init__(self, 0, commit, timestamp, author, None, log, size, None)
        self.filename = filename
        self.parents = parents


class GitRepository(vclib.Repository):
    def __init__(
        self,
        name: str,
        rootpath: str,
        authorizer: vcauth.GenericViewVCAuthorizer | None,
        utilities,
        content_encoding: str,
        path_encoding: str,
        default_branch: str | None = None,
    ):

        self.filesystem_encoding = sys.getfilesystemencoding()
        self.path_encoding = path_encoding
        if self.path_encoding == self.filesystem_encoding:
            self._to_pygit2_str = self._pygit2_str_conversion_noop
            self._from_pygit2_str = self._pygit2_str_conversion_noop
        else:
            self._to_pygit2_str = self._to_pygit2_str_reencode
            self._from_pygit2_str = self._from_pygit2_str_reencode
        # As pygit2.discover_repository() always returns path with
        # trailing '/' if it finds a repository, we normarize the
        # root path with trailing '/'.
        try:
            rp = pygit2.discover_repository(self._to_pygit2_str(rootpath))
        except vclib.Error:
            rp = None
        if rp is None:
            raise vclib.ReposNotFound(name)
        self.rootpath: str = self._from_pygit2_str(rp)
        self._pygit2_rootpath = rp

        # Initialize some stuff.
        self.name = name
        self.auth = authorizer
        self.diff_cmd = utilities.diff or "diff"
        self.content_encoding = content_encoding
        self.default_branch = default_branch

        # See if this repository is even viewable, authz-wise.
        if not vclib.check_root_access(self):
            raise vclib.ReposNotFound(name)

    def open(self):
        "Open the repository and init some other variables."
        self.repos = pygit2.Repository(self._pygit2_rootpath)
        self.local_branches = list(self.repos.branches.local)
        self.remote_branches = list(self.repos.branches.remote)
        self.tags = [r[10:] for r in self.repos.references if TAG_RE.match(r)]
        if self.default_branch:
            # branch ref is always point to 'head' commit.
            self.youngest, self.youngest_ref = self.repos.resolve_refish(self.default_branch)
        else:
            for branch in ("main", "trunk", "master"):
                if branch in self.local_branches:
                    self.default_branch = branch
                    self.youngest, self.youngest_ref = self.repos.resolve_refish(
                        self.default_branch
                    )
                    break
            else:
                self.default_branch = None
                # if default branch is not determined,
                # we use head reference.
                self.youngest_ref = self.repos.head
                self.youngest = self.repos.get(self.repos.head.target)

        # See if a universal read access determination can be made.
        if self.auth and self.auth.check_universal_access(self.name) == 1:
            self.auth = None
        self._revinfo_cache = {}

    def rootname(self) -> str:
        return self.name

    def roottype(self) -> str:
        return vclib.GIT

    def authorizer(self) -> vcauth.GenericViewVCAuthorizer | None:
        return self.auth

    def itemtype(self, path_parts: list[str], rev: str) -> str:
        commits, ppath, nodeobj = self._getnode(path_parts, rev)
        try:
            kind = _node_typemap[nodeobj.type_str]
        except KeyError:
            raise vclib.Error(f'Internal Error: unexpected object type "{nodeobj.type_str}"')
        if not vclib.check_path_access(self, path_parts, kind, rev):
            raise vclib.ItemNotFound(path_parts)
        return kind

    def openfile(self, path_parts: list[str], rev: str, options) -> tuple[pygit2.BlobIO, str]:
        commit, ppath, nodeobj = self._getnode(path_parts, rev)
        if not isinstance(nodeobj, pygit2.Blob):
            raise vclib.Error(f"Path '{self._getpath(path_parts)}' is not a file.")
        return pygit2.BlobIO(nodeobj), str(commit.id)

    def listdir(self, path_parts: list[str], rev: str, options) -> list[DirEntry]:
        commit, ppath, nodeobj = self._getnode(path_parts, rev)
        if not isinstance(nodeobj, pygit2.Tree):
            raise vclib.Error(f"Path '{self._getpath(path_parts)}' is not a directory.")
        entries = []
        for entry in nodeobj:
            kind = _node_typemap[entry.type_str]
            assert entry.name is not None
            node_name = self._from_pygit2_str(entry.name)
            if vclib.check_path_access(self, path_parts + [node_name], kind, str(commit.id)):
                entries.append(DirEntry(node_name, kind))
        return entries

    def dirlogs(self, path_parts: list[str], rev: str, entries: list[DirEntry], options):
        """see vclib.Repository.dirlogs docstring

        Option values recognized by this implementation

         git_simplify_first_parent
           boolean, default true. if set will return only first parent
           history on merge commit
        """

        commit, ppath, nodeobj = self._getnode(path_parts, rev)
        if not isinstance(nodeobj, pygit2.Tree):
            raise vclib.Error(f"Path '{self._getpath(path_parts)}' is not a directory.")
        # libgit2 does not have effective API for this purpose.
        # (See https://github.com/libgit2/pygit2/issues/231)
        # Below is incomplete algorithm using revwalk API, it does not
        # handle merging parents correctly.
        latests = dict([(ent.name, ent) for ent in entries])
        walker = self.repos.walk(commit.id, SortMode.TOPOLOGICAL)
        if options.get("git_simplify_first_parent", 1):
            walker.simplify_first_parent()
        cur_commit = next(walker)
        latest_tree = _get_tree_entry(cur_commit.tree, ppath)
        assert isinstance(latest_tree, pygit2.Tree)
        cur_node = latest_tree
        for prev_commit in walker:
            prev_node = _get_tree_entry(prev_commit.tree, ppath)
            if not isinstance(prev_node, pygit2.Tree):
                auth_ts, author = self._signature_props(cur_commit.author)
                msg = cur_commit.message
                for ent in latests:
                    p_ent = self._to_pygit2_str(ent)
                    latests[ent].rev = str(cur_commit.id)
                    latests[ent].date = int(auth_ts.timestamp())
                    latests[ent].author = author
                    latests[ent].log = msg
                    entobj = latest_tree[p_ent]
                    if isinstance(entobj, pygit2.Blob):
                        latests[ent].size = entobj.size
                return
            elif cur_node.id != prev_node.id:
                auth_ts, author = self._signature_props(cur_commit.author)
                msg = cur_commit.message
                for ent in list(latests.keys()):
                    p_ent = self._to_pygit2_str(ent)
                    latest_entobj = latest_tree[p_ent]
                    prev_entobj = prev_node[p_ent] if ent in prev_node else None
                    if (
                        prev_entobj is None
                        or prev_entobj.id != latest_entobj.id
                        or prev_entobj.filemode != latest_entobj.filemode
                    ):
                        latests[ent].rev = str(cur_commit.id)
                        latests[ent].date = int(auth_ts.timestamp())
                        latests[ent].author = author
                        latests[ent].log = msg
                        entobj = latest_tree[p_ent]
                        if isinstance(entobj, pygit2.Blob):
                            latests[ent].size = entobj.size
                        del latests[ent]
                    if not latests:
                        return
            cur_commit = prev_commit
        auth_ts, author = self._signature_props(cur_commit.author)
        msg = cur_commit.message
        for ent in latests:
            p_ent = self._to_pygit2_str(ent)
            latests[ent].rev = str(cur_commit.id)
            latests[ent].date = int(auth_ts.timestamp())
            latests[ent].author = author
            latests[ent].log = msg
            entobj = latest_tree[p_ent]
            if isinstance(entobj, pygit2.Blob):
                latests[ent].size = entobj.size
        return

    def itemlog(
        self, path_parts: list[str], rev: str, sortby: int, first: int, limit: int, options
    ) -> list[Revision]:
        """see vclib.Repository.itemlog docstring

        Option values recognized by this implementation

         git_simplify_first_parent
           boolean, default true. if set will return only first parent
           history on merge commit

         git_latest_log
           boolean, default false. if set will return only newest single log
           entry
        """
        # To do: it need to re-consider about sort method mapping.
        if sortby in (vclib.SORTBY_DEFAULT, vclib.SORTBY_REV):
            sort_opts = SortMode.NONE
        elif sortby == vclib.SORTBY_DATE:
            sort_opts = SortMode.TOPOLOGICAL | SortMode.TIME

        commit, ppath, nodeobj = self._getnode(path_parts, rev)
        path = self._getpath(path_parts)

        walker = self.repos.walk(commit.id, sort_opts)
        if options.get("git_simplify_first_parent", 1):
            walker.simplify_first_parent()
        if options.get("git_latest_log", 0):
            # ignore specified start and limit parameter
            first = 0
            limit = 1
            end = 1
        elif limit:
            end = first + limit
        else:
            end = 0
        cur_commit = next(walker)
        cur_node = nodeobj
        revs = []
        cur_rev: Revision | None = None
        cnt = 0
        for prev_commit in walker:
            prev_node = _get_tree_entry(prev_commit.tree, ppath)
            if prev_node is None:
                if cur_rev is not None:
                    cur_rev.prev = str(prev_commit.id)
                    revs.append(cur_rev)
                if cnt >= first and (not limit or cnt < end):
                    cur_rev = self._log_helper(cur_commit, cur_node, path)
                    cur_rev.prev = None
                    revs.append(cur_rev)
                # no more history
                return revs
            if cur_node.id != prev_node.id or cur_node.filemode != prev_node.filemode:
                if cur_rev is not None:
                    cur_rev.prev = str(prev_commit.id)
                    revs.append(cur_rev)
                if limit and cnt >= end:
                    return revs
                if cnt >= first:
                    cur_rev = self._log_helper(cur_commit, cur_node, path)
                cnt += 1
                cur_node = prev_node
            cur_commit = prev_commit
        # At end of loop, cur_commit is the commit the path was added
        if cur_rev is not None:
            cur_rev.prev = str(prev_commit.id)
            revs.append(cur_rev)
        if cnt >= first and (not limit or cnt < end):
            cur_rev = self._log_helper(cur_commit, cur_node, path)
            cur_rev.prev = None
            revs.append(cur_rev)
        return revs

    def itemprops(self, path_parts: list[str], rev: str) -> dict[str, Any]:
        self.itemtype(path_parts, rev)  # does auth-check
        return {}  # git doesn't support properties

    def annotate(
        self, path_parts: list[str], rev: str, include_text: bool = False
    ) -> tuple[Iterable[vclib.Annotation], str]:

        def gen_annotation(
            blame: pygit2.Blame, path_parts: list[str], file: pygit2.BlobIO | None
        ) -> Iterable[vclib.Annotation]:
            ln = 0
            for bh in blame:
                assert ln + 1 == bh.final_start_line_number
                cur_rev = self._getrev(str(bh.final_commit_id))
                parents = self._getcommit(cur_rev).parent_ids
                prev_rev = str(parents[0]) if parents else None
                if prev_rev is not None:
                    try:
                        if self.itemtype(path_parts, prev_rev) != vclib.FILE:
                            prev_rev = None
                    except Exception:
                        prev_rev = None
                cdate, author, _, _, _ = self._revinfo(cur_rev, False)
                cnt = bh.lines_in_hunk
                while cnt > 0:
                    ln += 1
                    cnt -= 1
                    text = file.readline() if file is not None else None
                    yield (vclib.Annotation(text, ln, cur_rev, prev_rev, author, cdate))

        path = self._getpath(path_parts)
        path_type = self.itemtype(path_parts, rev)  # does auth-check
        if path_type != vclib.FILE:
            raise vclib.Error(f"Path '{path}' is not a file.")
        rev = self._getrev(rev)
        ppath = self._to_pygit2_str(path)
        try:
            git_blame = self.repos.blame(ppath, BlameFlag.NORMAL, None, rev)
        except UnicodeEncodeError:
            raise vclib.Error(
                f"Cannot annotate file '{path}' because of the limitation in pygit2 module"
            )
        except Exception as e:
            raise vclib.Error(
                f"Cannot annotate file '{path} because of "
                "unknown error from pygit2.Repository.blame(): "
                f"{e}"
            )
        file = self.openfile(path_parts, rev, None)[0] if include_text else None
        return gen_annotation(git_blame, path_parts, file), rev

    def revinfo(
        self, rev: str
    ) -> tuple[int | None, str | None, str | None, dict[str, Any], list[vclib.ChangedPath] | None]:
        return self._revinfo(rev, True)

    def rawdiff(
        self,
        path_parts1: list[str],
        rev1: str,
        path_parts2: list[str],
        rev2: str,
        diff_type: int,
        options: dict = {},
        is_text: bool = True,
    ) -> vclib._diff_fp:

        def _date_from_rev(rev: str) -> int:
            msg, author, timestamp, props = self._getcommitprops(rev)
            return timestamp

        p1 = self._getpath(path_parts1)
        p2 = self._getpath(path_parts2)
        r1 = self._getrev(rev1)
        r2 = self._getrev(rev2)
        if not vclib.check_path_access(self, path_parts1, vclib.FILE, rev1):
            raise vclib.ItemNotFound(path_parts1)
        if not vclib.check_path_access(self, path_parts2, vclib.FILE, rev2):
            raise vclib.ItemNotFound(path_parts2)
        encoding = self.content_encoding if is_text else None

        args = vclib._diff_args(diff_type, options)

        temp1 = self._temp_checkout(path_parts1, r1)
        temp2 = self._temp_checkout(path_parts2, r2)
        info1 = p1, _date_from_rev(r1), r1
        info2 = p2, _date_from_rev(r2), r2
        return vclib._diff_fp(temp1, temp2, info1, info2, self.diff_cmd, args, encoding=encoding)

    def isexecutable(self, path_parts: list[str], rev: str) -> bool:
        commit, ppath, nodeobj = self._getnode(path_parts, rev)
        if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
            raise vclib.Error(f"Path '{self._getpath(path_parts)}' is not a file.")
        return nodeobj.filemode.name == "BLOB_EXECUTABLE"

    def filesize(self, path_parts: list[str], rev: str) -> int:
        commit, ppath, nodeobj = self._getnode(path_parts, rev)
        if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
            raise vclib.Error(f"Path '{self._getpath(path_parts)}' is not a file.")
        assert isinstance(nodeobj, pygit2.Blob)
        return nodeobj.size

    # --- helpers --- #

    @staticmethod
    def _signature_props(sig: pygit2.Signature) -> tuple[datetime.datetime, str]:
        tz = datetime.timezone(datetime.timedelta(minutes=sig.offset))
        timestamp = datetime.datetime.fromtimestamp(sig.time, tz=tz)
        return timestamp, f"{sig.name} <{sig.email}>"

    def _getcommitprops(self, rev: pygit2.Commit | str) -> tuple[str, str, int, dict[str, Any]]:
        if isinstance(rev, str):
            commit = self.repos.get(rev)
        else:
            assert isinstance(rev, pygit2.Commit)
            commit = rev
        # On pygit2, commit.message is already properly decoded even if
        # commit.message_encoding is not None.
        msg = commit.message
        auth_ts, author = self._signature_props(commit.author)
        tz = datetime.timezone(datetime.timedelta(minutes=commit.commit_time_offset))
        commit_ts = datetime.datetime.fromtimestamp(commit.commit_time, tz=tz)
        committer_ts, committer = self._signature_props(commit.committer)
        parents = ",".join([str(parent_id) for parent_id in commit.parent_ids])
        return (
            msg,
            author,
            int(auth_ts.timestamp()),
            {
                "commit_date": commit_ts.strftime("%Y-%m-%d %H:%M:%S %z"),
                "committer_date": committer_ts.strftime("%Y-%m-%d %H:%M:%S %z"),
                "committer": committer,
                "parents": parents,
            },
        )

    def _revinfo(
        self, rev: str, include_changed_paths: bool = False
    ) -> tuple[int | None, str | None, str | None, dict[str, Any], list[vclib.ChangedPath] | None]:
        """Internal-use, cache-friendly revision information harvester."""

        def _collect_changedpaths(
            found_readable: bool,
            found_unreadable: bool,
            changes: dict[str, vclib.ChangedPath],
            parent_pp: list[str],
            rev: str,
            t1: pygit2.Tree,
            t2: pygit2.Tree | None,
        ) -> tuple[bool, bool]:
            """Return a 2-tuple: found_readable, found_unreadable,
            with collwcting changed paths"""

            t1_ent = set([entobj.name for entobj in t1 if entobj.name is not None])
            t2_ent = (
                set([entobj.name for entobj in t2 if entobj.name is not None])
                if t2 is not None
                else set()
            )
            try:
                prev_rev = self.repos.get(rev).parents[0].id
            except Exception:
                # To do: prev_rev should not be None, but what is apropriate?
                prev_rev = "Not a revision"
            for ent in t1_ent - t2_ent:
                # Added entries
                pp = parent_pp + [self._from_pygit2_str(ent)]
                path = self._getpath(pp)
                try:
                    kind = self.itemtype(pp, rev)
                    found_readable = True
                    changes[path] = vclib.ChangedPath(
                        pp, rev, kind, [], prev_rev, vclib.ADDED, False, False, False
                    )
                except vclib.ItemNotFound:
                    found_unreadable = True
            for ent in t2_ent - t1_ent:
                # Removed entries
                pp = parent_pp + [self._from_pygit2_str(ent)]
                path = self._getpath(pp)
                try:
                    kind = self.itemtype(pp, rev)
                    found_readable = True
                    # To do: base_rev should be a commit that base_path was
                    # last modified.
                    changes[path] = vclib.ChangedPath(
                        pp, rev, kind, pp, prev_rev, vclib.DELETED, False, False, False
                    )
                except vclib.ItemNotFound:
                    found_unreadable = True
            for ent in t1_ent & t2_ent:
                # If t2 is None then t2_ent is empty set. So the assertion
                # below never fails. Only for type checking....
                assert t2 is not None
                e1 = t1[ent]
                e2 = t2[ent]
                if e1.id == e2.id and e1.filemode == e2.filemode:
                    continue
                pp = parent_pp + [self._from_pygit2_str(ent)]
                path = self._getpath(pp)

                if e1.type_str == "blob" and e2.type_str == "blob":
                    text_modified = e1.id != e2.id
                    if e1.filemode == e1.filemode:
                        try:
                            kind = self.itemtype(pp, rev)
                            found_readable = True
                            # To do: base_rev should be a commit that
                            # base_path was last modified.
                            changes[path] = vclib.ChangedPath(
                                pp,
                                rev,
                                kind,
                                pp,
                                prev_rev,
                                vclib.MODIFIED,
                                False,
                                text_modified,
                                False,
                            )
                        except vclib.ItemNotFound:
                            found_unreadable = True

                    elif e1.filemode.name == "LINK" or e2.filemode.name == "LINK":
                        try:
                            kind = self.itemtype(pp, rev)
                            found_readable = True
                            # To do: base_rev should be a commit that
                            # base_path was last modified.
                            changes[path] = vclib.ChangedPath(
                                pp, rev, kind, pp, prev_rev, vclib.REPLACED, False, False, False
                            )
                        except vclib.ItemNotFound:
                            found_unreadable = True

                    else:
                        try:
                            kind = self.itemtype(pp, rev)
                            found_readable = True
                            # To do: base_rev should be a commit that
                            # base_path was last modified.
                            changes[path] = vclib.ChangedPath(
                                pp,
                                rev,
                                kind,
                                pp,
                                prev_rev,
                                vclib.MODIFIED,
                                False,
                                text_modified,
                                True,
                            )
                        except vclib.ItemNotFound:
                            found_unreadable = True

                elif e1.type != e2.type:
                    try:
                        kind = self.itemtype(pp, rev)
                        found_readable = True
                        # To do: base_rev should be a commit that
                        # base_path was last modified.
                        changes[path] = vclib.ChangedPath(
                            pp, rev, kind, pp, prev_rev, vclib.REPLACED, False, False, False
                        )
                    except vclib.ItemNotFound:
                        found_unreadable = True

                else:
                    # both are trees.
                    assert isinstance(e1, pygit2.Tree) and isinstance(e2, pygit2.Tree)
                    crv = _collect_changedpaths(
                        found_readable, found_unreadable, changes, pp, rev, e1, e2
                    )
                    found_readable, found_unreadable = crv

            return found_readable, found_unreadable

        def _simple_auth_check(
            found_readable: bool,
            found_unreadable: bool,
            parent_pp: list[str],
            rev: str,
            t1: pygit2.Tree,
            t2: pygit2.Tree | None,
        ) -> tuple[bool, bool]:
            """Return a 2-tuple: found_readable, found_unreadable,
            without collwcting changed paths"""

            if found_readable and found_unreadable:
                return found_readable, found_unreadable

            t1_ent = set([entobj.name for entobj in t1 if entobj.name is not None])
            t2_ent = (
                set([entobj.name for entobj in t2 if entobj.name is not None])
                if t2 is not None
                else set()
            )
            for ent in t1_ent - t2_ent:
                # Added entries
                pp = parent_pp + [self._from_pygit2_str(ent)]
                try:
                    self.itemtype(pp, rev)
                    found_readable = True
                    if found_unreadable:
                        return found_readable, found_unreadable
                except vclib.ItemNotFound:
                    found_unreadable = True
                    if found_readable:
                        return found_readable, found_unreadable
            for ent in t2_ent - t1_ent:
                # Removed entries
                pp = parent_pp + [self._from_pygit2_str(ent)]
                try:
                    self.itemtype(pp, rev)
                    found_readable = True
                    if found_unreadable:
                        return found_readable, found_unreadable
                except vclib.ItemNotFound:
                    found_unreadable = True
                    if found_readable:
                        return found_readable, found_unreadable
            for ent in t1_ent & t2_ent:
                # If t2 is None then t2_ent is empty set. So the assertion
                # below never fails. Only for type checking....
                assert t2 is not None
                e1 = t1[ent]
                e2 = t2[ent]
                if e1.id == e2.id and e1.filemode == e2.filemode:
                    continue
                pp = parent_pp + [self._from_pygit2_str(ent)]

                if e1.type_str == "blob" or e2.type_str == "blob":
                    try:
                        self.itemtype(pp, rev)
                        found_readable = True
                        if found_unreadable:
                            return found_readable, found_unreadable
                    except vclib.ItemNotFound:
                        found_unreadable = True
                        if found_readable:
                            return found_readable, found_unreadable
                else:
                    # both are trees.
                    assert isinstance(e1, pygit2.Tree) and isinstance(e2, pygit2.Tree)
                    crv = _simple_auth_check(found_readable, found_unreadable, pp, rev, e1, e2)
                    found_readable, found_unreadable = crv
                    if found_readable and found_unreadable:
                        return found_readable, found_unreadable

            return found_readable, found_unreadable

        def _revinfo_helper(
            rev: str, include_changed_paths: bool
        ) -> tuple[
            int | None, str | None, str | None, dict[str, Any], list[vclib.ChangedPath] | None
        ]:
            msg: str | None
            author: str | None
            auth_ts: int | None
            revprops: dict[str, Any]
            # Get the revision property info.
            commit = self.repos.get(rev)
            msg, author, auth_ts, revprops = self._getcommitprops(commit)

            # Optimization: If our caller doesn't care about the changed
            # paths, and we don't need them to do authz determinations, let's
            # get outta here.
            if self.auth is None and not include_changed_paths:
                return auth_ts, author, msg, revprops, None

            # If we get here, then we either need the changed paths because we
            # were asked for them, or we need them to do authorization checks.
            #
            # If we only need them for authorization checks, though, we
            # won't bother generating fully populated ChangedPath items (the
            # cost is too great).

            t1 = commit.tree
            t2 = commit.parents[0].tree if commit.parents else None
            if include_changed_paths:
                changes: dict[str, vclib.ChangedPath] = {}
                changedinfo = _collect_changedpaths(False, False, changes, [], rev, t1, t2)
                found_readable, found_unreadable = changedinfo
                changedpaths = list(changes.values())
            else:
                changedinfo = _simple_auth_check(False, False, [], rev, t1, t2)
                changedpaths = None

            # Filter our metadata where necessary, and return the requested data.
            if found_unreadable:
                msg = None
                if not found_readable:
                    author = None
                    auth_ts = None
                    revprops = {}
            return auth_ts, author, msg, revprops, changedpaths

        # Consult the revinfo cache first.  If we don't have cached info,
        # or our caller wants changed paths and we don't have those for
        # this revision, go do the real work.
        rev = self._getrev(rev)
        cached_info = self._revinfo_cache.get(rev)
        if not cached_info or (include_changed_paths and cached_info[4] is None):
            cached_info = _revinfo_helper(rev, include_changed_paths)
            self._revinfo_cache[rev] = cached_info
        return cached_info

    def _log_helper(
        self, commit: pygit2.Commit, node: pygit2.Blob | pygit2.Tree, path: str
    ) -> Revision:
        """get attributes for Revision from commit object and path,
        then return a Revision object"""

        cid = str(commit.id)
        auth_ts, author = self._signature_props(commit.author)
        msg = commit.message
        size = node.size if isinstance(node, pygit2.Blob) else None
        parents = [str(oid) for oid in commit.parent_ids]
        return Revision(cid, int(auth_ts.timestamp()), author, msg, size, path, parents)

    @staticmethod
    def _getpath(path_parts: list[str]) -> str:
        """get repository internal"""
        return "/".join(path_parts)

    def _to_pygit2_str_reencode(self, nstr: str) -> str:
        """transcode vclib interface str to pygit2 interface str"""
        try:
            return nstr.encode(self.path_encoding, "surrogateescape").decode(
                self.filesystem_encoding, "surrogateescape"
            )
        except UnicodeError:
            raise vclib.Error(f"Cannot encode to path encoding {self.path_encoding}: {nstr}")

    def _from_pygit2_str_reencode(self, pstr: str) -> str:
        """transcode pygit2 interface str to vclib interface str"""
        try:
            return pstr.encode(self.filesystem_encoding, "surrogateescape").decode(
                self.path_encoding, "surrogateescape"
            )
        except UnicodeError:
            raise vclib.Error(f"Cannot encode to system encoding {self.path_encoding}: {pstr}")

    def _pygit2_str_conversion_noop(self, nstr: str) -> str:
        """do nothing because vclib interface str == pygit2 interface str"""
        return nstr

    def _getrev(self, rev: str | pygit2.Oid) -> str:
        """get cannonical commit ID string for specified rev"""
        if rev is None or rev == "HEAD":
            return str(self.youngest.id)
        str_rev = str(rev) if isinstance(rev, pygit2.Oid) else rev
        try:
            commit, commit_ref = self.repos.resolve_refish(str_rev)
        except Exception:
            raise vclib.InvalidRevision(rev)
        return str(commit.id)

    def _getcommit(self, rev: str | pygit2.Oid) -> pygit2.Commit:
        if rev is None or rev == "HEAD":
            return self.repos.resolve_refish("HEAD")[0]
        try:
            commit = self.repos.resolve_refish(rev)[0]
        except Exception:
            raise vclib.InvalidRevision(rev)
        if commit is None:
            raise vclib.InvalidRevision(rev)
        return commit

    def _getnode(
        self, path_parts: list[str], rev: str | pygit2.Oid
    ) -> tuple[pygit2.Commit, str, pygit2.Blob | pygit2.Tree]:
        rev = self._getrev(rev)
        commit = self._getcommit(rev)
        nodeobj: pygit2.Object | None
        if not path_parts:
            nodeobj = commit.tree
            ppath = ""
        else:
            ppath = self._to_pygit2_str(self._getpath(path_parts))
            nodeobj = commit.tree[ppath]
            if nodeobj is None:
                raise vclib.ItemNotFound(ppath)
        assert isinstance(nodeobj, pygit2.Blob | pygit2.Tree)
        return commit, ppath, nodeobj

    def _temp_checkout(self, path_parts: list[str], rev: str) -> str:
        """Check out file revision to temporary file"""
        fd, temp = tempfile.mkstemp()
        try:
            with os.fdopen(fd, "wb") as fp:
                stream, _ = self.openfile(path_parts, rev, None)
                try:
                    while 1:
                        chunk = stream.read(BUFSIZE)
                        if not chunk:
                            break
                        fp.write(chunk)
                except OSError as e:
                    raise vclib.Error(f"I/O error while extracting temporary file: {e}")
                finally:
                    stream.close()
        except Exception:
            try:
                os.remove(temp)
            except Exception:
                pass
            raise
        return temp

    # --- custom --- #

    def get_youngest_revision(self) -> str:
        return str(self.youngest.id)

    def get_location(self, path: str, rev: str, old_rev: str) -> str:
        # As we does not implement move or copy calculation between
        # commits, old location is always same path.
        return path

    def created_rev(self, full_name: str, rev: str) -> str:
        commit = self._getcommit(rev)
        pfull_name = self._to_pygit2_str(full_name)
        nodeobj = _get_tree_entry(commit.tree, pfull_name)
        if nodeobj is None:
            raise vclib.ItemNotFound(_path_parts(full_name))
        path_parts = _path_parts(full_name)
        self.itemtype(path_parts, rev)  # does auth-check
        # while this method does not have parameter 'sortby' and
        # 'options', use default sort order and simplify first parent.
        walker = self.repos.walk(commit.id, SortMode.NONE)
        walker.simplify_first_parent()
        cur_commit = next(walker)
        for prev_commit in walker:
            prev_node = _get_tree_entry(prev_commit.tree, pfull_name)
            if (
                prev_node is None
                or prev_node.id != nodeobj.id
                or prev_node.filemode != nodeobj.filemode
            ):
                return str(cur_commit.id)
            cur_commit = prev_commit
        return str(cur_commit.id)

    def last_rev(self, path: str, peg_revision: str, limit_revision: int | None = None) -> str:
        raise vclib.UnsupportedFeature

    def get_symlink_target(self, path_parts: list[str], rev: str) -> str | None:
        """Return the target of the symbolic link versioned at PATH_PARTS
        in REV, or None if that object is not a symlink."""

        commit, ppath, nodeobj = self._getnode(path_parts, rev)
        self.itemtype(path_parts, rev)  # does auth-check
        # Symlinks must be files (blob objects) with the filemode set
        # on "LINK" and with file contents is a target path.
        if not isinstance(nodeobj, pygit2.Blob) or nodeobj.filemode.name != "LINK":
            return None
        return nodeobj.data.decode(self.path_encoding, "surrogateescape")

    def get_branches(self, path_parts: list[str]) -> list[str]:
        """Return list of local branch names which contains path specified by
        path_parts"""

        if not path_parts:
            return self.local_branches
        path = self._getpath(path_parts)
        ppath = self._to_pygit2_str(path)
        branches: list[str] = []
        for branch in self.local_branches:
            try:
                brev = self.repos.branches.local[branch].target
            except KeyError:
                brev = None
            if brev is not None and ppath in self.repos.get(brev).tree:
                try:
                    self.itemtype(path_parts, str(brev))  # does auth-check
                    branches.append(branch)
                except vclib.ItemNotFound:
                    pass
        return branches

    def get_tags(self, path_parts: list[str]) -> list[str]:
        """Return list of tag names which contains path specified by
        path_parts"""

        if not path_parts:
            return self.tags
        path = self._getpath(path_parts)
        ppath = self._to_pygit2_str(path)
        tags: list[str] = []
        for tag in self.tags:
            try:
                trev = self.repos.resolve_refish(tag)[0]
            except KeyError:
                trev = None
            if trev is not None and ppath in trev.tree:
                try:
                    self.itemtype(path_parts, str(trev.id))  # does auth-check
                    tags.append(tag)
                except vclib.ItemNotFound:
                    pass
        return tags
