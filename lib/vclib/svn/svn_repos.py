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

"Version Control lib driver for locally accessible Subversion repositories"

import vclib
import sys
import os
import os.path
import tempfile
from io import BytesIO
from urllib.parse import quote as _quote
from svn import fs, repos, core, client, delta
from . import _strpath

long = int


# Verify that we have an acceptable version of Subversion.
MIN_SUBVERSION_VERSION = (1, 14, 0)
HAS_SUBVERSION_VERSION = (core.SVN_VER_MAJOR, core.SVN_VER_MINOR, core.SVN_VER_PATCH)
if HAS_SUBVERSION_VERSION < MIN_SUBVERSION_VERSION:
    found_ver = ".".join([str(x) for x in HAS_SUBVERSION_VERSION])
    needs_ver = ".".join([str(x) for x in MIN_SUBVERSION_VERSION])
    raise Exception("Subversion version %s is required (%s found)" % (needs_ver, found_ver))


def _allow_all(root, path, pool):
    """Generic authz_read_func that permits access to all paths"""
    return 1


def _path_parts(path):
    """Return a list of PATH's components (using '/' as the delimiter).
    PATH may be of type str or bytes, and the returned value will carry
    the same type."""
    splitchar = isinstance(path, bytes) and b"/" or "/"
    return [p for p in path.split(splitchar) if p]


def _cleanup_path(path):
    """Return a cleaned-up Subversion filesystem path.  PATH may be of
    type str or bytes, and the returned value will carry the same
    type."""
    splitchar = isinstance(path, bytes) and b"/" or "/"
    return splitchar.join(_path_parts(path))


def _fs_path_join(base, relative):
    return _cleanup_path(base + "/" + relative)


def _rev2optrev(rev):
    assert isinstance(rev, int)
    rt = core.svn_opt_revision_t()
    rt.kind = core.svn_opt_revision_number
    rt.value.number = rev
    return rt


def _rootpath2url(rootpath, path):
    rootpath = os.path.abspath(rootpath)
    drive, rootpath = os.path.splitdrive(rootpath)
    if os.sep != "/":
        rootpath = rootpath.replace(os.sep, "/")
    rootpath = _quote(rootpath)
    path = _quote(path)
    if drive:
        url = "file:///" + drive + rootpath + "/" + path
    else:
        url = "file://" + rootpath + "/" + path
    return core.svn_path_canonicalize(url)


# Given a Subversion node kind, return the vclib type (or
# None, if no mapping can be made).
def _kind2type(node_kind):
    return {
        core.svn_node_dir: vclib.DIR,
        core.svn_node_file: vclib.FILE,
    }.get(node_kind)


# Return a stringfied copy of a bytestring Subversion property
# (versioned or unversioned) VALUE if possible; otherwise return the
# original byte string.
def _normalize_property_value(value, encoding_hint=None):
    try:
        value = value.decode("utf-8")
    except UnicodeDecodeError:
        if encoding_hint:
            try:
                value = value.decode(encoding_hint)
            except UnicodeDecodeError:
                pass
    return value


# Given raw bytestring Subversion property (versioned or unversioned)
# NAME and VALUE, return a 2-tuple of the same but readied for Python
# 3 usage.  If NAME can't be stringfied (that is, converted to a
# Unicode string), both the returned NAME and VALUE will be None.
# Otherwise, NAME will be a Unicode string and VALUE will be a Unicode
# string of it could be stringified or a bytestring if it couldn't.
def _normalize_property(name, value, encoding_hint=None):
    try:
        name = name.decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    value = _normalize_property_value(value, encoding_hint)
    return name, value


# Given a dictionary REVPROPS of revision properties, pull special
# ones out of them and return a 4-tuple containing the log message,
# the author, the date (converted from the date string property), and
# a dictionary of any/all other revprops.
def _split_revprops(revprops, encoding_hint=None):
    if not revprops:
        return None, None, None, {}
    msg = author = date = None
    other_props = {}
    for prop in revprops:
        pname, pval = _normalize_property(prop, revprops[prop], encoding_hint)
        if pname == core.SVN_PROP_REVISION_LOG.decode("utf-8"):
            msg = pval
        elif pname == core.SVN_PROP_REVISION_AUTHOR.decode("utf-8"):
            author = pval
        elif pname == core.SVN_PROP_REVISION_DATE.decode("utf-8"):
            date = _datestr_to_date(pval)
        elif pname is not None:
            other_props[pname] = pval
    return msg, author, date, other_props


def _datestr_to_date(datestr):
    try:
        return core.svn_time_from_cstring(datestr) // 1000000
    except Exception:
        return None


class Revision(vclib.Revision):
    "Hold state for each revision's log entry."

    def __init__(self, rev, date, author, msg, size, lockinfo, filename, copy_path, copy_rev):
        vclib.Revision.__init__(self, rev, str(rev), date, author, None, msg, size, lockinfo)
        self.filename = filename
        self.copy_path = copy_path
        self.copy_rev = copy_rev


class NodeHistory:
    """An iterable object that returns 2-tuples of (revision, path)
    locations along a node's change history, ordered from youngest to
    oldest."""

    def __init__(self, fs_ptr, show_all_logs, limit=0):
        self.histories = []
        self.fs_ptr = fs_ptr
        self.show_all_logs = show_all_logs
        self.oldest_rev = None
        self.limit = limit

    def add_history(self, path, revision, pool):
        # If filtering, only add the path and revision to the histories
        # list if they were actually changed in this revision (where
        # change means the path itself was changed, or one of its parents
        # was copied).  This is useful for omitting bubble-up directory
        # changes.
        if not self.oldest_rev:
            self.oldest_rev = revision
        else:
            assert revision < self.oldest_rev

        if not self.show_all_logs:
            rev_root = fs.revision_root(self.fs_ptr, revision)
            paths = list(fs.paths_changed2(rev_root).keys())
            if path not in paths:
                # Look for a copied parent
                test_path = path
                found = 0
                while 1:
                    off = test_path.rfind("/")
                    if off < 0:
                        break
                    test_path = test_path[0:off]
                    if test_path in paths:
                        copyfrom_rev, copyfrom_path = fs.copied_from(rev_root, test_path)
                        if copyfrom_rev >= 0 and copyfrom_path:
                            found = 1
                            break
                if not found:
                    return
        self.histories.append([revision, _cleanup_path(path)])
        if self.limit and len(self.histories) == self.limit:
            raise core.SubversionException("", core.SVN_ERR_CEASE_INVOCATION)

    def __getitem__(self, idx):
        return self.histories[idx]


def _get_last_history_rev(fsroot, path):
    history = fs.node_history(fsroot, path)
    history = fs.history_prev(history, 0)
    history_path, history_rev = fs.history_location(history)
    return history_rev


def temp_checkout(svnrepos, path, rev):
    """Check out file revision to temporary file"""
    fd, temp = tempfile.mkstemp()
    fp = os.fdopen(fd, "wb")
    try:
        root = svnrepos._getroot(rev)
        stream = fs.file_contents(root, path)
        try:
            while 1:
                chunk = core.svn_stream_read(stream, core.SVN_STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                fp.write(chunk)
        finally:
            core.svn_stream_close(stream)
    finally:
        fp.close()
    return temp


class FileContentsPipe:
    def __init__(self, root, path):
        self.readable = True
        self._stream = fs.file_contents(root, path)
        self._eof = 0

    def read(self, len=None):
        chunk = None
        if not self._eof:
            if len is None:
                buffer = BytesIO()
                try:
                    while 1:
                        hunk = core.svn_stream_read(self._stream, 8192)
                        if not hunk:
                            break
                        buffer.write(hunk)
                    chunk = buffer.getvalue()
                finally:
                    buffer.close()

            else:
                chunk = core.svn_stream_read(self._stream, len)
        if not chunk:
            self._eof = 1
        return chunk

    def readline(self):
        chunk = None
        if not self._eof:
            chunk, self._eof = core.svn_stream_readline(self._stream, b"\n")
            if not self._eof:
                chunk = chunk + b"\n"
        if not chunk:
            self._eof = 1
        return chunk

    def readlines(self):
        lines = []
        while True:
            line = self.readline()
            if not line:
                break
            lines.append(line)
        return lines

    def close(self):
        return core.svn_stream_close(self._stream)

    def eof(self):
        return self._eof


class BlameSource:
    def __init__(self, local_url, rev, first_rev, include_text, config_dir, encoding):
        self.idx = -1
        self.first_rev = first_rev
        self.blame_data = []
        self.include_text = include_text
        self.encoding = encoding

        ctx = client.svn_client_create_context()
        core.svn_config_ensure(config_dir)
        ctx.config = core.svn_config_get_config(config_dir)
        ctx.auth_baton = core.svn_auth_open([])
        try:
            # TODO: Is this use of FIRST_REV always what we want?  Should we
            # pass 1 here instead and do filtering later?
            client.blame2(
                local_url,
                _rev2optrev(rev),
                _rev2optrev(first_rev),
                _rev2optrev(rev),
                self._blame_cb,
                ctx,
            )
        except core.SubversionException as e:
            if e.apr_err == core.SVN_ERR_CLIENT_IS_BINARY_FILE:
                raise vclib.NonTextualFileContents
            raise

    def _blame_cb(self, line_no, rev, author, date, text, pool):
        prev_rev = None
        if rev > self.first_rev:
            prev_rev = rev - 1
        if not self.include_text:
            text = None
        if author is not None:
            try:
                author = author.decode(self.encoding, "xmlcharrefreplace")
            except Exception:
                author = author.decode(self.encoding, "backslashreplace")
        self.blame_data.append(vclib.Annotation(text, line_no + 1, rev, prev_rev, author, None))

    def __getitem__(self, idx):
        if idx != self.idx + 1:
            raise BlameSequencingError()
        self.idx = idx
        return self.blame_data[idx]


class BlameSequencingError(Exception):
    pass


class SVNChangedPath(vclib.ChangedPath):
    """Wrapper around vclib.ChangedPath which handles path splitting."""

    def __init__(
        self, path, rev, pathtype, base_path, base_rev, action, copied, text_changed, props_changed
    ):
        path_parts = _path_parts(path or "")
        base_path_parts = _path_parts(base_path or "")
        vclib.ChangedPath.__init__(
            self,
            path_parts,
            rev,
            pathtype,
            base_path_parts,
            base_rev,
            action,
            copied,
            text_changed,
            props_changed,
        )


class LocalSubversionRepository(vclib.Repository):
    def __init__(self, name, rootpath, authorizer, utilities, config_dir,
                 content_encoding, path_encoding):
        if sys.platform == 'win32':
            if (not (os.path.isdir(rootpath)
                and os.path.isfile(os.path.join(rootpath, "format")))):
                raise vclib.ReposNotFound(name)
        else:
            rootpathb = rootpath.encode(path_encoding, 'surrogateescape')
            if (not (os.path.isdir(rootpathb)
                and os.path.isfile(os.path.join(rootpathb, b"format")))):
                raise vclib.ReposNotFound(name)

        # Initialize some stuff.
        self.rootpath = rootpath
        self.name = name
        self.auth = authorizer
        self.diff_cmd = utilities.diff or "diff"
        self.config_dir = config_dir or None
        self.content_encoding = content_encoding

        # See if this repository is even viewable, authz-wise.
        if not vclib.check_root_access(self):
            raise vclib.ReposNotFound(name)

    def open(self):
        # Open the repository and init some other variables.
        self.repos = repos.svn_repos_open(self.rootpath)
        self.fs_ptr = repos.svn_repos_fs(self.repos)
        self.youngest = fs.youngest_rev(self.fs_ptr)
        self._fsroots = {}
        self._revinfo_cache = {}

        # See if a universal read access determination can be made.
        if self.auth and self.auth.check_universal_access(self.name) == 1:
            self.auth = None

    def rootname(self):
        return self.name

    def roottype(self):
        return vclib.SVN

    def authorizer(self):
        return self.auth

    def itemtype(self, path_parts, rev):
        rev = self._getrev(rev)
        basepath = self._getpath(path_parts)
        pathtype = self._gettype(basepath, rev)
        if pathtype is None:
            raise vclib.ItemNotFound(path_parts)
        if not vclib.check_path_access(self, path_parts, pathtype, rev):
            raise vclib.ItemNotFound(path_parts)
        return pathtype

    def openfile(self, path_parts, rev, options):
        path = self._getpath(path_parts)
        if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
            raise vclib.Error("Path '%s' is not a file." % path)
        rev = self._getrev(rev)
        fsroot = self._getroot(rev)
        revision = str(_get_last_history_rev(fsroot, path))
        fp = FileContentsPipe(fsroot, path)
        return fp, revision

    def listdir(self, path_parts, rev, options):
        path = self._getpath(path_parts)
        if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
            raise vclib.Error("Path '%s' is not a directory." % path)
        rev = self._getrev(rev)
        fsroot = self._getroot(rev)
        dirents = fs.dir_entries(fsroot, path)
        entries = []
        for entry in dirents.values():
            kind = _kind2type(entry.kind)
            ent_path = _strpath(entry.name)
            if vclib.check_path_access(self, path_parts + [ent_path], kind, rev):
                entries.append(vclib.DirEntry(ent_path, kind))
        return entries

    def dirlogs(self, path_parts, rev, entries, options):
        path = self._getpath(path_parts)
        if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
            raise vclib.Error("Path '%s' is not a directory." % path)
        fsroot = self._getroot(self._getrev(rev))
        rev = self._getrev(rev)
        for entry in entries:
            ent_path = entry.name
            entry_path_parts = path_parts + [ent_path]
            if not vclib.check_path_access(self, entry_path_parts, entry.kind, rev):
                continue
            path = self._getpath(entry_path_parts)
            entry_rev = _get_last_history_rev(fsroot, path)
            date, author, msg, revprops, changes = self._revinfo(entry_rev)
            entry.rev = str(entry_rev)
            entry.date = date
            entry.author = author
            entry.log = msg
            if entry.kind == vclib.FILE:
                entry.size = fs.file_length(fsroot, path)
            lock = fs.get_lock(self.fs_ptr, path)
            entry.lockinfo = (
                lock and _normalize_property_value(lock.owner,
                                                   self.content_encoding)
                or None
            )

    def itemlog(self, path_parts, rev, sortby, first, limit, options):
        """see vclib.Repository.itemlog docstring

        Option values recognized by this implementation

          svn_show_all_dir_logs
            boolean, default false. if set for a directory path, will include
            revisions where files underneath the directory have changed

          svn_cross_copies
            boolean, default false. if set for a path created by a copy, will
            include revisions from before the copy

          svn_latest_log
            boolean, default false. if set will return only newest single log
            entry
        """
        assert sortby == vclib.SORTBY_DEFAULT or sortby == vclib.SORTBY_REV

        path = self._getpath(path_parts)
        path_type = self.itemtype(path_parts, rev)  # does auth-check
        rev = self._getrev(rev)
        revs = []
        lockinfo = None

        # See if this path is locked.
        try:
            lock = fs.get_lock(self.fs_ptr, path)
            if lock:
                lockinfo = _normalize_property_value(lock.owner,
                                                     self.content_encoding)
        except NameError:
            pass

        # If our caller only wants the latest log, we'll invoke
        # _log_helper for just the one revision.  Otherwise, we go off
        # into history-fetching mode.  ### TODO: we could stand to have a
        # 'limit' parameter here as numeric cut-off for the depth of our
        # history search.
        if options.get("svn_latest_log", 0):
            revision = self._log_helper(path, rev, lockinfo)
            if revision:
                revision.prev = None
                revs.append(revision)
        else:
            history = self._get_history(path, rev, path_type, first + limit, options)
            if len(history) < first:
                history = []
            if limit:
                history = history[first : (first + limit)]

            for hist_rev, hist_path in history:
                revision = self._log_helper(hist_path, hist_rev, lockinfo)
                if revision:
                    # If we have unreadable copyfrom data, obscure it.
                    if revision.copy_path is not None:
                        cp_parts = _path_parts(revision.copy_path)
                        if not vclib.check_path_access(
                            self, cp_parts, path_type, revision.copy_rev
                        ):
                            revision.copy_path = revision.copy_rev = None
                    revision.prev = None
                    if len(revs):
                        revs[-1].prev = revision
                    revs.append(revision)
        return revs

    def itemprops(self, path_parts, rev):
        path = self._getpath(path_parts)
        self.itemtype(path_parts, rev)  # does auth-check
        rev = self._getrev(rev)
        fsroot = self._getroot(rev)
        proptable = fs.node_proplist(fsroot, path)
        propdict = {}
        for pname in proptable.keys():
            pvalue = proptable[pname]
            pname, pvalue = _normalize_property(pname, pvalue, self.content_encoding)
            if pname:
                propdict[pname] = pvalue
        return propdict

    def annotate(self, path_parts, rev, include_text=False):
        path = self._getpath(path_parts)
        path_type = self.itemtype(path_parts, rev)  # does auth-check
        if path_type != vclib.FILE:
            raise vclib.Error("Path '%s' is not a file." % path)
        rev = self._getrev(rev)
        history = self._get_history(path, rev, path_type, 0, {"svn_cross_copies": 1})
        youngest_rev, youngest_path = history[0]
        oldest_rev, oldest_path = history[-1]
        source = BlameSource(
            _rootpath2url(self.rootpath, path),
            youngest_rev,
            oldest_rev,
            include_text,
            self.config_dir,
            self.content_encoding,
        )
        return source, youngest_rev

    def revinfo(self, rev):
        return self._revinfo(rev, 1)

    def rawdiff(self, path_parts1, rev1, path_parts2, rev2, diff_type,
                options={}, is_text=True):
        p1 = self._getpath(path_parts1)
        p2 = self._getpath(path_parts2)
        r1 = self._getrev(rev1)
        r2 = self._getrev(rev2)
        if not vclib.check_path_access(self, path_parts1, vclib.FILE, rev1):
            raise vclib.ItemNotFound(path_parts1)
        if not vclib.check_path_access(self, path_parts2, vclib.FILE, rev2):
            raise vclib.ItemNotFound(path_parts2)

        args = vclib._diff_args(diff_type, options)
        encoding = self.content_encoding if is_text else None

        def _date_from_rev(rev):
            date, author, msg, revprops, changes = self._revinfo(rev)
            return date

        try:
            temp1 = temp_checkout(self, p1, r1)
            temp2 = temp_checkout(self, p2, r2)
            info1 = p1, _date_from_rev(r1), r1
            info2 = p2, _date_from_rev(r2), r2
            return vclib._diff_fp(temp1, temp2, info1, info2, self.diff_cmd,
                                  args, encoding=encoding)
        except core.SubversionException as e:
            if e.apr_err == core.SVN_ERR_FS_NOT_FOUND:
                raise vclib.InvalidRevision
            raise

    def isexecutable(self, path_parts, rev):
        props = self.itemprops(path_parts, rev)  # does authz-check
        return core.SVN_PROP_EXECUTABLE in props

    def filesize(self, path_parts, rev):
        path = self._getpath(path_parts)
        if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
            raise vclib.Error("Path '%s' is not a file." % path)
        fsroot = self._getroot(self._getrev(rev))
        return fs.file_length(fsroot, path)

    # --- helpers --- #

    def _revinfo(self, rev, include_changed_paths=0):
        """Internal-use, cache-friendly revision information harvester."""

        def _get_changed_paths(fsroot):
            """Return a 3-tuple: found_readable, found_unreadable, changed_paths."""
            editor = repos.ChangeCollector(self.fs_ptr, fsroot)
            e_ptr, e_baton = delta.make_editor(editor)
            repos.svn_repos_replay(fsroot, e_ptr, e_baton)
            changedpaths = {}
            changes = editor.get_changes()

            # Copy the Subversion changes into a new hash, checking
            # authorization and converting them into ChangedPath objects.
            found_readable = found_unreadable = 0
            for path in changes.keys():
                spath = _strpath(path)
                change = changes[path]
                if change.path:
                    change.path = _cleanup_path(change.path)
                if change.base_path:
                    change.base_path = _cleanup_path(change.base_path)
                is_copy = 0
                action = {
                    repos.CHANGE_ACTION_ADD: vclib.ADDED,
                    repos.CHANGE_ACTION_DELETE: vclib.DELETED,
                    repos.CHANGE_ACTION_REPLACE: vclib.REPLACED,
                }.get(change.action, vclib.MODIFIED)
                if (
                    (action == vclib.ADDED or action == vclib.REPLACED)
                    and change.base_path
                    and change.base_rev
                ):
                    is_copy = 1
                pathtype = _kind2type(change.item_kind)
                parts = _path_parts(spath)
                if vclib.check_path_access(self, parts, pathtype, rev):
                    if is_copy and change.base_path and (change.base_path != path):
                        parts = _path_parts(_strpath(change.base_path))
                        if not vclib.check_path_access(self, parts, pathtype, change.base_rev):
                            is_copy = 0
                            change.base_path = None
                            change.base_rev = None
                            found_unreadable = 1
                    if change.base_path:
                        base_path = _strpath(change.base_path)
                    else:
                        base_path = None
                    changedpaths[spath] = SVNChangedPath(
                        spath,
                        rev,
                        pathtype,
                        base_path,
                        change.base_rev,
                        action,
                        is_copy,
                        change.text_changed,
                        change.prop_changes,
                    )
                    found_readable = 1
                else:
                    found_unreadable = 1
            return found_readable, found_unreadable, list(changedpaths.values())

        def _get_change_copyinfo(fsroot, path, change):
            # If we know the copyfrom info, return it...
            if change.copyfrom_known:
                copyfrom_path = change.copyfrom_path
                copyfrom_rev = change.copyfrom_rev
            # ...otherwise, if this change could be a copy (that is, it
            # contains an add action), query the copyfrom info ...
            elif (
                change.change_kind == fs.path_change_replace
                or change.change_kind == fs.path_change_add
            ):
                copyfrom_rev, copyfrom_path = fs.copied_from(fsroot, path)
            # ...else, there's no copyfrom info.
            else:
                copyfrom_rev = core.SVN_INVALID_REVNUM
                copyfrom_path = None
            return copyfrom_path, copyfrom_rev

        def _simple_auth_check(fsroot):
            """Return a 2-tuple: found_readable, found_unreadable."""
            found_unreadable = found_readable = 0
            changes = fs.paths_changed2(fsroot)
            paths = list(changes.keys())
            for path in paths:
                change = changes[path]
                pathtype = _kind2type(change.node_kind)
                parts = _path_parts(_strpath(path))
                if pathtype is None:
                    # Figure out the pathtype so we can query the authz subsystem.
                    if change.change_kind == fs.path_change_delete:
                        # Deletions are annoying, because they might be underneath
                        # copies (make their previous location non-trivial).
                        prev_parts = parts
                        prev_rev = rev - 1
                        parent_parts = parts[:-1]
                        while parent_parts:
                            parent_path = "/" + self._getpath(parent_parts)
                            pchange = changes.get(parent_path)
                            if not (
                                pchange
                                and (
                                    pchange.change_kind == fs.path_change_replace
                                    or pchange.change_kind == fs.path_change_add
                                )
                            ):
                                del parent_parts[-1]
                                continue
                            copyfrom_path, copyfrom_rev = _get_change_copyinfo(
                                fsroot, parent_path, pchange
                            )
                            if copyfrom_path:
                                prev_rev = copyfrom_rev
                                prev_parts = (_path_parts(_strpath(copyfrom_path))
                                              + parts[len(parent_parts) :])
                                break
                            del parent_parts[-1]
                        pathtype = self._gettype(self._getpath(prev_parts), prev_rev)
                    else:
                        pathtype = self._gettype(self._getpath(parts), rev)
                if vclib.check_path_access(self, parts, pathtype, rev):
                    found_readable = 1
                    copyfrom_path, copyfrom_rev = _get_change_copyinfo(fsroot, path, change)
                    if copyfrom_path and copyfrom_path != path:
                        parts = _path_parts(_strpath(copyfrom_path))
                        if not vclib.check_path_access(self, parts, pathtype, copyfrom_rev):
                            found_unreadable = 1
                else:
                    found_unreadable = 1
                if found_readable and found_unreadable:
                    break
            return found_readable, found_unreadable

        def _revinfo_helper(rev, include_changed_paths):
            # Get the revision property info.  (Would use
            # editor.get_root_props(), but something is broken there...)
            revprops = fs.revision_proplist(self.fs_ptr, rev)
            msg, author, date, revprops = _split_revprops(revprops)

            # The iterfaces that use this function expect string values.
            if isinstance(msg, bytes):
                msg = _normalize_property_value(msg, self.content_encoding)
            if isinstance(author, bytes):
                author = _normalize_property_value(author, self.content_encoding)

            # Optimization: If our caller doesn't care about the changed
            # paths, and we don't need them to do authz determinations, let's
            # get outta here.
            if self.auth is None and not include_changed_paths:
                return date, author, msg, revprops, None

            # If we get here, then we either need the changed paths because we
            # were asked for them, or we need them to do authorization checks.
            #
            # If we only need them for authorization checks, though, we
            # won't bother generating fully populated ChangedPath items (the
            # cost is too great).
            fsroot = self._getroot(rev)
            if include_changed_paths:
                found_readable, found_unreadable, changedpaths = _get_changed_paths(fsroot)
            else:
                changedpaths = None
                found_readable, found_unreadable = _simple_auth_check(fsroot)

            # Filter our metadata where necessary, and return the requested data.
            if found_unreadable:
                msg = None
                if not found_readable:
                    author = None
                    date = None
            return date, author, msg, revprops, changedpaths

        # Consult the revinfo cache first.  If we don't have cached info,
        # or our caller wants changed paths and we don't have those for
        # this revision, go do the real work.
        rev = self._getrev(rev)
        cached_info = self._revinfo_cache.get(rev)
        if not cached_info or (include_changed_paths and cached_info[4] is None):
            cached_info = _revinfo_helper(rev, include_changed_paths)
            self._revinfo_cache[rev] = cached_info
        return tuple(cached_info)

    def _log_helper(self, path, rev, lockinfo):
        rev_root = fs.revision_root(self.fs_ptr, rev)
        copyfrom_rev, copyfrom_path = fs.copied_from(rev_root, path)
        date, author, msg, revprops, changes = self._revinfo(rev)
        if fs.is_file(rev_root, path):
            size = fs.file_length(rev_root, path)
        else:
            size = None
        if copyfrom_path:
            copyfrom_path = _cleanup_path(_strpath(copyfrom_path))
        else:
            copyfrom_path = None
        return Revision(rev, date, author, msg, size, lockinfo, path, copyfrom_path, copyfrom_rev)

    def _get_history(self, path, rev, path_type, limit=0, options={}):
        if self.youngest == 0:
            return []

        rev_paths = []
        fsroot = self._getroot(rev)
        show_all_logs = options.get("svn_show_all_dir_logs", 0)
        if not show_all_logs:
            # See if the path is a file or directory.
            kind = fs.check_path(fsroot, path)
            if kind is core.svn_node_file:
                show_all_logs = 1

        # Instantiate a NodeHistory collector object, and use it to collect
        # history items for PATH@REV.
        history = NodeHistory(self.fs_ptr, show_all_logs, limit)
        try:
            repos.svn_repos_history(
                self.fs_ptr, path, history.add_history, 1, rev, options.get("svn_cross_copies", 0)
            )
        except core.SubversionException as e:
            if e.apr_err != core.SVN_ERR_CEASE_INVOCATION:
                raise

        # Now, iterate over those history items, checking for changes of
        # location, pruning as necessitated by authz rules.
        for hist_rev, hist_path in history:
            hist_path = _strpath(hist_path)
            path_parts = _path_parts(hist_path)
            if not vclib.check_path_access(self, path_parts, path_type, hist_rev):
                break
            rev_paths.append([hist_rev, hist_path])
        return rev_paths

    def _getpath(self, path_parts):
        return "/".join(path_parts)

    def _getrev(self, rev):
        if rev is None or rev == "HEAD":
            return self.youngest
        try:
            if isinstance(rev, str):
                while rev[0] == "r":
                    rev = rev[1:]
            rev = int(rev)
        except Exception:
            raise vclib.InvalidRevision(rev)
        if (rev < 0) or (rev > self.youngest):
            raise vclib.InvalidRevision(rev)
        return rev

    def _getroot(self, rev):
        try:
            return self._fsroots[rev]
        except KeyError:
            r = self._fsroots[rev] = fs.revision_root(self.fs_ptr, rev)
            return r

    def _gettype(self, path, rev):
        # Similar to itemtype(), but without the authz check.  Returns
        # None for missing paths.
        try:
            kind = fs.check_path(self._getroot(rev), path)
        except Exception:
            return None
        if kind == core.svn_node_dir:
            return vclib.DIR
        if kind == core.svn_node_file:
            return vclib.FILE
        return None

    # --- custom --- #

    def get_youngest_revision(self):
        return self.youngest

    def get_location(self, path, rev, old_rev):
        try:
            results = repos.svn_repos_trace_node_locations(
                self.fs_ptr, path, rev, [old_rev], _allow_all
            )
        except core.SubversionException as e:
            if e.apr_err == core.SVN_ERR_FS_NOT_FOUND:
                raise vclib.ItemNotFound(path)
            raise
        try:
            old_path = results[old_rev]
        except KeyError:
            raise vclib.ItemNotFound(path)

        return _cleanup_path(_strpath(old_path))

    def created_rev(self, full_name, rev):
        return fs.node_created_rev(self._getroot(rev), full_name)

    def last_rev(self, path, peg_revision, limit_revision=None):
        """Given PATH, known to exist in PEG_REVISION, find the youngest
        revision older than, or equal to, LIMIT_REVISION in which path
        exists.  Return that revision, and the path at which PATH exists in
        that revision."""

        # Here's the plan, man.  In the trivial case (where PEG_REVISION is
        # the same as LIMIT_REVISION), this is a no-brainer.  If
        # LIMIT_REVISION is older than PEG_REVISION, we can use Subversion's
        # history tracing code to find the right location.  If, however,
        # LIMIT_REVISION is younger than PEG_REVISION, we suffer from
        # Subversion's lack of forward history searching.  Our workaround,
        # ugly as it may be, involves a binary search through the revisions
        # between PEG_REVISION and LIMIT_REVISION to find our last live
        # revision.
        peg_revision = self._getrev(peg_revision)
        limit_revision = self._getrev(limit_revision)
        try:
            if peg_revision == limit_revision:
                return peg_revision, path
            elif peg_revision > limit_revision:
                fsroot = self._getroot(peg_revision)
                history = fs.node_history(fsroot, path)
                while history:
                    path, peg_revision = fs.history_location(history)
                    if peg_revision <= limit_revision:
                        return max(peg_revision, limit_revision), _cleanup_path(path)
                    history = fs.history_prev(history, 1)
                return peg_revision, _cleanup_path(path)
            else:
                orig_id = fs.node_id(self._getroot(peg_revision), path)
                while peg_revision != limit_revision:
                    mid = (peg_revision + 1 + limit_revision) // 2
                    try:
                        mid_id = fs.node_id(self._getroot(mid), path)
                    except core.SubversionException as e:
                        if e.apr_err == core.SVN_ERR_FS_NOT_FOUND:
                            cmp = -1
                        else:
                            raise
                    else:
                        # FIXME: Not quite right.  Need a comparison function that
                        # only returns true when the two nodes are the same copy,
                        # not just related.
                        cmp = fs.compare_ids(orig_id, mid_id)

                    if cmp in (0, 1):
                        peg_revision = mid
                    else:
                        limit_revision = mid - 1

                return peg_revision, path
        finally:
            pass

    def get_symlink_target(self, path_parts, rev):
        """Return the target of the symbolic link versioned at PATH_PARTS
        in REV, or None if that object is not a symlink."""

        path = self._getpath(path_parts)
        rev = self._getrev(rev)
        path_type = self.itemtype(path_parts, rev)  # does auth-check
        fsroot = self._getroot(rev)

        # Symlinks must be files with the svn:special property set on them
        # and with file contents which read "link SOME_PATH".
        if path_type != vclib.FILE:
            return None
        props = fs.node_proplist(fsroot, path)
        if core.SVN_PROP_SPECIAL not in props:
            return None
        pathspec = ""
        # FIXME: We're being a touch sloppy here, only checking the first
        # line of the file.
        stream = fs.file_contents(fsroot, path)
        try:
            pathspec, eof = core.svn_stream_readline(stream, b"\n")
        finally:
            core.svn_stream_close(stream)
        if pathspec[:5] != "link ":
            return None
        return pathspec[5:]
