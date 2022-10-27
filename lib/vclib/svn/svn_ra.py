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

"Version Control lib driver for remotely accessible Subversion repositories."

import vclib
import os
import tempfile
from urllib.parse import quote as _quote

from .svn_repos import (
    Revision,
    SVNChangedPath,
    _cleanup_path,
    _kind2type,
    _normalize_property,
    _normalize_property_value,
    _path_parts,
    _rev2optrev,
    _split_revprops,
    _to_str,
)
from svn import core, client, ra


# Verify that we have an acceptable version of Subversion.
MIN_SUBVERSION_VERSION = (1, 14, 0)
HAS_SUBVERSION_VERSION = (core.SVN_VER_MAJOR, core.SVN_VER_MINOR, core.SVN_VER_PATCH)
if HAS_SUBVERSION_VERSION < MIN_SUBVERSION_VERSION:
    found_ver = ".".join([str(x) for x in HAS_SUBVERSION_VERSION])
    needs_ver = ".".join([str(x) for x in MIN_SUBVERSION_VERSION])
    raise Exception("Subversion version %s is required (%s found)" % (needs_ver, found_ver))


def _sort_key_path(path):
    """Transform paths into sort key.

    Children of paths are greater than their parents, but less than
    greater siblings of their parents.
    """
    return path.split('/')


def _sort_key_pathb(pathb):
    """Transform bytes paths into sort key.

    Same as _sort_key_path but accept pathb as a path represented in bytes.
    """
    return pathb.split(b'/')


def client_log(url, start_rev, end_rev, log_limit, include_changes, cross_copies, cb_func, ctx):
    include_changes = include_changes and 1 or 0
    cross_copies = cross_copies and 1 or 0
    client.svn_client_log4(
        [url],
        start_rev,
        start_rev,
        end_rev,
        log_limit,
        include_changes,
        not cross_copies,
        0,
        None,
        cb_func,
        ctx,
    )


def setup_client_ctx(config_dir):
    # Ensure that the configuration directory exists.
    core.svn_config_ensure(config_dir)

    # Fetch the configuration (and 'config' bit thereof).
    cfg = core.svn_config_get_config(config_dir)
    config = cfg.get(core.SVN_CONFIG_CATEGORY_CONFIG)

    auth_baton = core.svn_cmdline_create_auth_baton(1, None, None, config_dir, 1, 1, config, None)

    # Create, setup, and return the client context baton.
    ctx = client.svn_client_create_context()
    ctx.config = cfg
    ctx.auth_baton = auth_baton
    return ctx


class LogCollector:
    def __init__(self, path, show_all_logs, lockinfo, access_check_func, encoding="utf-8"):
        # This class uses leading slashes for paths internally
        if not path:
            self.path = "/"
        else:
            self.path = path[0] == "/" and path or "/" + path
        self.logs = []
        self.show_all_logs = show_all_logs
        self.lockinfo = lockinfo
        self.access_check_func = access_check_func
        self.done = False
        self.encoding = encoding

    def add_log(self, log_entry, pool):
        if self.done:
            return
        paths = log_entry.changed_paths
        revision = log_entry.revision
        msg, author, date, revprops = _split_revprops(log_entry.revprops)

        # Changed paths have leading slashes
        changed_paths = [_to_str(p) for p in paths.keys()]
        changed_paths.sort(key=_sort_key_path)
        this_path = None
        if self.path in changed_paths:
            this_path = self.path
            change = paths[self.path.encode("utf-8", "surrogateescape")]
            if change.copyfrom_path:
                this_path = _to_str(change.copyfrom_path)
        for changed_path in changed_paths:
            if changed_path != self.path:
                # If a parent of our path was copied, our "next previous"
                # (huh?) path will exist elsewhere (under the copy source).
                if (self.path.rfind(changed_path) == 0) and self.path[len(changed_path)] == "/":
                    change = paths[changed_path.encode("utf-8", "surrogateescape")]
                    if change.copyfrom_path:
                        this_path = _to_str(change.copyfrom_path) + self.path[len(changed_path) :]
        if self.show_all_logs or this_path:
            if self.access_check_func is None or self.access_check_func(self.path[1:], revision):
                entry = Revision(
                    revision, date, author, msg, None, self.lockinfo, self.path[1:], None, None
                )
                self.logs.append(entry)
            else:
                self.done = True
        if this_path:
            self.path = this_path


def cat_to_tempfile(svnrepos, path, rev):
    """Check out file revision to temporary file"""
    fd, temp = tempfile.mkstemp()
    fp = os.fdopen(fd, "wb")
    url = svnrepos._geturl(path)
    client.svn_client_cat(fp, url, _rev2optrev(rev), svnrepos.ctx)
    fp.close()
    return temp


class SelfCleanFP:
    def __init__(self, path):
        self.readable = True
        self._fp = open(path, "rb")
        self._path = path
        self._eof = 0

    def read(self, len=None):
        if len:
            chunk = self._fp.read(len)
        else:
            chunk = self._fp.read()
        if chunk == b"":
            self._eof = 1
        return chunk

    def readline(self):
        chunk = self._fp.readline()
        if chunk == b"":
            self._eof = 1
        return chunk

    def readlines(self):
        lines = self._fp.readlines()
        self._eof = 1
        return lines

    def close(self):
        self._fp.close()
        if self._path:
            try:
                os.remove(self._path)
                self._path = None
            except OSError:
                pass

    def __del__(self):
        self.close()

    def eof(self):
        return self._eof


class RemoteSubversionRepository(vclib.Repository):
    def __init__(self, name, rootpath, authorizer, utilities, config_dir, encoding):
        self.name = name
        self.rootpath = rootpath
        self.auth = authorizer
        self.diff_cmd = utilities.diff or "diff"
        self.config_dir = config_dir or None
        self.content_encoding = encoding

        # See if this repository is even viewable, authz-wise.
        if not vclib.check_root_access(self):
            raise vclib.ReposNotFound(name)

    def open(self):
        # Setup the client context baton, complete with non-prompting authstuffs.
        self.ctx = setup_client_ctx(self.config_dir)

        ra_callbacks = ra.svn_ra_callbacks_t()
        ra_callbacks.auth_baton = self.ctx.auth_baton
        self.ra_session = ra.svn_ra_open(self.rootpath, ra_callbacks, None, self.ctx.config)
        self.youngest = ra.svn_ra_get_latest_revnum(self.ra_session)
        self._dirent_cache = {}
        self._revinfo_cache = {}

        # See if a universal read access determination can be made.
        if self.auth and self.auth.check_universal_access(self.name) == 1:
            self.auth = None

    def rootname(self):
        return self.name

    def rootpath(self):
        return self.rootpath

    def roottype(self):
        return vclib.SVN

    def authorizer(self):
        return self.auth

    def itemtype(self, path_parts, rev):
        pathtype = None
        if not len(path_parts):
            pathtype = vclib.DIR
        else:
            path = self._getpath(path_parts)
            rev = self._getrev(rev)
            try:
                kind = ra.svn_ra_check_path(self.ra_session, path, rev)
                pathtype = _kind2type(kind)
            except Exception:
                pass
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
        # rev here should be the last history revision of the URL
        fp = SelfCleanFP(cat_to_tempfile(self, path, rev))
        lh_rev, c_rev = self._get_last_history_rev(path_parts, rev)
        return fp, lh_rev

    def listdir(self, path_parts, rev, options):
        path = self._getpath(path_parts)
        if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
            raise vclib.Error("Path '%s' is not a directory." % path)
        rev = self._getrev(rev)
        entries = []
        dirents, locks = self._get_dirents(path, rev)
        for name, entry in dirents.items():
            pathtype = _kind2type(entry.kind)
            entries.append(vclib.DirEntry(name, pathtype))
        return entries

    def dirlogs(self, path_parts, rev, entries, options):
        path = self._getpath(path_parts)
        if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
            raise vclib.Error("Path '%s' is not a directory." % path)
        rev = self._getrev(rev)
        dirents, locks = self._get_dirents(path, rev)
        for entry in entries:
            dirent = dirents.get(entry.name, None)
            # dirents is authz-sanitized, so ensure the entry is found therein.
            if dirent is None:
                continue
            # Get authz-sanitized revision metadata.
            entry.date, entry.author, entry.log, revprops, changes = self._revinfo(
                dirent.created_rev
            )
            entry.rev = str(dirent.created_rev)
            entry.size = dirent.size
            entry.lockinfo = None
            if entry.name in locks:
                entry.lockinfo = locks[entry.name].owner

    def itemlog(self, path_parts, rev, sortby, first, limit, options):
        assert sortby == vclib.SORTBY_DEFAULT or sortby == vclib.SORTBY_REV
        path_type = self.itemtype(path_parts, rev)  # does auth-check
        path = self._getpath(path_parts)
        rev = self._getrev(rev)
        url = self._geturl(path)

        # If this is a file, fetch the lock status and size (as of REV)
        # for this item.
        lockinfo = size_in_rev = None
        if path_type == vclib.FILE:
            basename = path_parts[-1].encode("utf-8", "surrogateescape")
            list_url = self._geturl(self._getpath(path_parts[:-1]))
            dirents, locks = client.svn_client_ls3(
                list_url, _rev2optrev(rev), _rev2optrev(rev), 0, self.ctx
            )
            if basename in locks:
                lockinfo = locks[basename].owner
            if basename in dirents:
                size_in_rev = dirents[basename].size

        # Special handling for the 'svn_latest_log' scenario.
        #
        # FIXME: Don't like this hack.  We should just introduce something
        # more direct in the vclib API.
        if options.get("svn_latest_log", 0):
            dir_lh_rev, dir_c_rev = self._get_last_history_rev(path_parts, rev)
            date, author, log, revprops, changes = self._revinfo(dir_lh_rev)
            return [
                vclib.Revision(
                    dir_lh_rev, str(dir_lh_rev), date, author, None, log, size_in_rev, lockinfo
                )
            ]

        def _access_checker(check_path, check_rev):
            return vclib.check_path_access(self, _path_parts(check_path), path_type, check_rev)

        # It's okay if we're told to not show all logs on a file -- all
        # the revisions should match correctly anyway.
        lc = LogCollector(path, options.get("svn_show_all_dir_logs", 0), lockinfo, _access_checker)

        cross_copies = options.get("svn_cross_copies", 0)
        log_limit = 0
        if limit:
            log_limit = first + limit
        client_log(
            url, _rev2optrev(rev), _rev2optrev(1), log_limit, 1, cross_copies, lc.add_log, self.ctx
        )
        revs = lc.logs
        revs.sort()
        prev = None
        for rev in revs:
            # Swap out revision info with stuff from the cache (which is
            # authz-sanitized).
            rev.date, rev.author, rev.log, revprops, changes = self._revinfo(rev.number)
            rev.prev = prev
            prev = rev
        revs.reverse()

        if len(revs) < first:
            return []
        if limit:
            return revs[first : (first + limit)]
        return revs

    def itemprops(self, path_parts, rev):
        path = self._getpath(path_parts)
        self.itemtype(path_parts, rev)  # does auth-check
        rev = self._getrev(rev)
        url = self._geturl(path)
        pairs = client.svn_client_proplist2(url, _rev2optrev(rev), _rev2optrev(rev), 0, self.ctx)
        propdict = {}
        if pairs:
            for pname in pairs[0][1].keys():
                pvalue = pairs[0][1][pname]
                pname, pvalue = _normalize_property(pname, pvalue, self.content_encoding)
                if pname:
                    propdict[pname] = pvalue
        return propdict

    def annotate(self, path_parts, rev, include_text=False):
        path = self._getpath(path_parts)
        if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
            raise vclib.Error("Path '%s' is not a file." % path)
        rev = self._getrev(rev)
        url = self._geturl(path)

        # Examine logs for the file to determine the oldest revision we are
        # permitted to see.
        log_options = {
            "svn_cross_copies": 1,
            "svn_show_all_dir_logs": 1,
        }
        revs = self.itemlog(path_parts, rev, vclib.SORTBY_REV, 0, 0, log_options)
        oldest_rev = revs[-1].number

        # Now calculate the annotation data.  Note that we'll not
        # inherently trust the provided author and date, because authz
        # rules might necessitate that we strip that information out.
        blame_data = []

        def _blame_cb(line_no, revision, author, date, line, pool, blame_data=blame_data):
            prev_rev = None
            if revision > 1:
                prev_rev = revision - 1

            # If we have an invalid revision, clear the date and author
            # values.  Otherwise, if we have authz filtering to do, use the
            # revinfo cache to do so.
            if revision < 0:
                date = author = None
            elif self.auth:
                date, author, msg, revprops, changes = self._revinfo(revision)
            else:
                author = _normalize_property_value(author, self.content_encoding)

            # Strip text if the caller doesn't want it.
            if not include_text:
                line = None
            blame_data.append(vclib.Annotation(line, line_no + 1, revision, prev_rev, author, date))

        client.blame2(
            url, _rev2optrev(rev), _rev2optrev(oldest_rev), _rev2optrev(rev), _blame_cb, self.ctx
        )
        return blame_data, rev

    def revinfo(self, rev):
        return self._revinfo(rev, 1)

    def rawdiff(self, path_parts1, rev1, path_parts2, rev2, type, options={}):
        p1 = self._getpath(path_parts1)
        p2 = self._getpath(path_parts2)
        r1 = self._getrev(rev1)
        r2 = self._getrev(rev2)
        if not vclib.check_path_access(self, path_parts1, vclib.FILE, rev1):
            raise vclib.ItemNotFound(path_parts1)
        if not vclib.check_path_access(self, path_parts2, vclib.FILE, rev2):
            raise vclib.ItemNotFound(path_parts2)

        args = vclib._diff_args(type, options)

        def _date_from_rev(rev):
            date, author, msg, revprops, changes = self._revinfo(rev)
            return date

        try:
            temp1 = cat_to_tempfile(self, p1, r1)
            temp2 = cat_to_tempfile(self, p2, r2)
            info1 = p1, _date_from_rev(r1), r1
            info2 = p2, _date_from_rev(r2), r2
            return vclib._diff_fp(temp1, temp2, info1, info2, self.diff_cmd, args)
        except core.SubversionException as e:
            if e.apr_err == vclib.svn.core.SVN_ERR_FS_NOT_FOUND:
                raise vclib.InvalidRevision
            raise

    def isexecutable(self, path_parts, rev):
        props = self.itemprops(path_parts, rev)  # does authz-check
        return core.SVN_PROP_EXECUTABLE in props

    def filesize(self, path_parts, rev):
        path = self._getpath(path_parts)
        if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
            raise vclib.Error("Path '%s' is not a file." % path)
        rev = self._getrev(rev)
        dirents, locks = self._get_dirents(self._getpath(path_parts[:-1]), rev)
        dirent = dirents.get(path_parts[-1], None)
        return dirent.size

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

    def _geturl(self, path=None):
        if not path:
            return self.rootpath
        path = self.rootpath + "/" + _quote(path)
        return core.svn_path_canonicalize(path)

    def _get_dirents(self, path, rev):
        """Return a 2-type of dirents and locks, possibly reading/writing
        from a local cache of that information.  This functions performs
        authz checks, stripping out unreadable dirents."""

        dir_url = self._geturl(path)
        path_parts = _path_parts(path)
        if path:
            key = str(rev) + "/" + path
        else:
            key = str(rev)

        # Ensure that the cache gets filled...
        dirents_locks = self._dirent_cache.get(key)
        if not dirents_locks:
            tmp_dirents, locks = client.svn_client_ls3(
                dir_url, _rev2optrev(rev), _rev2optrev(rev), 0, self.ctx
            )
            dirents = {}
            for name, dirent in tmp_dirents.items():
                dirent_parts = path_parts + [_to_str(name)]
                kind = dirent.kind
                if (
                    kind == core.svn_node_dir or kind == core.svn_node_file
                ) and vclib.check_path_access(
                    self, dirent_parts, (kind == core.svn_node_dir and vclib.DIR or vclib.FILE), rev
                ):
                    lh_rev, c_rev = self._get_last_history_rev(dirent_parts, rev)
                    dirent.created_rev = lh_rev
                    dirents[_to_str(name)] = dirent
            dirents_locks = [dirents, locks]
            self._dirent_cache[key] = dirents_locks

        # ...then return the goodies from the cache.
        return dirents_locks[0], dirents_locks[1]

    def _get_last_history_rev(self, path_parts, rev):
        """Return the a 2-tuple which contains:
        - the last interesting revision equal to or older than REV in
          the history of PATH_PARTS.
        - the created_rev of of PATH_PARTS as of REV."""

        path = self._getpath(path_parts)
        url = self._geturl(self._getpath(path_parts))
        optrev = _rev2optrev(rev)

        # Get the last-changed-rev.
        revisions = []

        def _info_cb(path, info, pool, retval=revisions):
            revisions.append(info.last_changed_rev)

        client.svn_client_info(url, optrev, optrev, _info_cb, 0, self.ctx)
        last_changed_rev = revisions[0]

        # Now, this object might not have been directly edited since the
        # last-changed-rev, but it might have been the child of a copy.
        # To determine this, we'll run a potentially no-op log between
        # LAST_CHANGED_REV and REV.
        lc = LogCollector(path, 1, None, None)
        client_log(url, optrev, _rev2optrev(last_changed_rev), 1, 1, 0, lc.add_log, self.ctx)
        revs = lc.logs
        if revs:
            revs.sort()
            return revs[0].number, last_changed_rev
        else:
            return last_changed_rev, last_changed_rev

    def _revinfo_fetch(self, rev, include_changed_paths=0):
        need_changes = include_changed_paths or self.auth
        revs = []

        def _log_cb(log_entry, pool, retval=revs):
            # If Subversion happens to call us more than once, we choose not
            # to care.
            if retval:
                return

            revision = log_entry.revision
            msg, author, date, revprops = _split_revprops(log_entry.revprops)
            action_map = {
                "D": vclib.DELETED,
                "A": vclib.ADDED,
                "R": vclib.REPLACED,
                "M": vclib.MODIFIED,
            }

            # Easy out: if we won't use the changed-path info, just return a
            # changes-less tuple.
            if not need_changes:
                return revs.append([date, author, msg, revprops, None])

            # Subversion 1.5 and earlier didn't offer the 'changed_paths2'
            # hash, and in Subversion 1.6, it's offered but broken.
            try:
                changed_paths = log_entry.changed_paths2
                paths = list((changed_paths or {}).keys())
            except Exception:
                changed_paths = log_entry.changed_paths
                paths = list((changed_paths or {}).keys())
            paths.sort(key=_sort_key_pathb)

            # If we get this far, our caller needs changed-paths, or we need
            # them for authz-related sanitization.
            changes = []
            found_readable = found_unreadable = 0
            for path in paths:
                change = changed_paths[path]
                pathtype = _kind2type(change.node_kind)
                text_modified = (change.text_modified == core.svn_tristate_true and 1 or 0)
                props_modified = (change.props_modified == core.svn_tristate_true and 1 or 0)

                # Wrong, diddily wrong wrong wrong.  Can you say,
                # "Manufacturing data left and right because it hurts to
                # figure out the right stuff?"
                action = action_map.get(change.action, vclib.MODIFIED)
                if change.copyfrom_path and change.copyfrom_rev:
                    is_copy = 1
                    base_path = change.copyfrom_path
                    base_rev = change.copyfrom_rev
                elif action == vclib.ADDED or action == vclib.REPLACED:
                    is_copy = 0
                    base_path = base_rev = None
                else:
                    is_copy = 0
                    base_path = path
                    base_rev = revision - 1

                # Check authz rules (sadly, we have to lie about the path type)
                parts = _path_parts(_to_str(path))
                if vclib.check_path_access(self, parts, vclib.FILE, revision):
                    if is_copy and base_path and (base_path != path):
                        parts = _path_parts(_to_str(base_path))
                        if not vclib.check_path_access(self, parts, vclib.FILE, base_rev):
                            is_copy = 0
                            base_path = None
                            base_rev = None
                            found_unreadable = 1
                    changes.append(
                        SVNChangedPath(
                            _to_str(path),
                            revision,
                            pathtype,
                            _to_str(base_path),
                            base_rev,
                            action,
                            is_copy,
                            text_modified,
                            props_modified,
                        )
                    )
                    found_readable = 1
                else:
                    found_unreadable = 1

                # If our caller doesn't want changed-path stuff, and we have
                # the info we need to make an authz determination already,
                # quit this loop and get on with it.
                if (not include_changed_paths) and found_unreadable and found_readable:
                    break

            # Filter unreadable information.
            if found_unreadable:
                msg = None
                if not found_readable:
                    author = None
                    date = None

            # Drop unrequested changes.
            if not include_changed_paths:
                changes = None

            # Add this revision information to the "return" array.
            retval.append([date, author, msg, revprops, changes])

        optrev = _rev2optrev(rev)
        client_log(self.rootpath, optrev, optrev, 1, need_changes, 0, _log_cb, self.ctx)
        return tuple(revs[0])

    def _revinfo(self, rev, include_changed_paths=0):
        """Internal-use, cache-friendly revision information harvester."""

        # Consult the revinfo cache first.  If we don't have cached info,
        # or our caller wants changed paths and we don't have those for
        # this revision, go do the real work.
        rev = self._getrev(rev)
        cached_info = self._revinfo_cache.get(rev)
        if not cached_info or (include_changed_paths and cached_info[4] is None):
            cached_info = self._revinfo_fetch(rev, include_changed_paths)
            self._revinfo_cache[rev] = cached_info
        return cached_info

    # --- custom --- #

    def get_youngest_revision(self):
        return self.youngest

    def get_location(self, path, rev, old_rev):
        try:
            results = ra.get_locations(self.ra_session, path, rev, [old_rev])
        except core.SubversionException as e:
            if e.apr_err == core.SVN_ERR_FS_NOT_FOUND:
                raise vclib.ItemNotFound(path)
            raise
        try:
            old_path = results[old_rev]
        except KeyError:
            raise vclib.ItemNotFound(path)
        old_path = _cleanup_path(_to_str(old_path))
        old_path_parts = _path_parts(old_path)
        # Check access (lying about path types)
        if not vclib.check_path_access(self, old_path_parts, vclib.FILE, old_rev):
            raise vclib.ItemNotFound(path)
        return old_path

    def created_rev(self, path, rev):
        lh_rev, c_rev = self._get_last_history_rev(_path_parts(path), rev)
        return lh_rev

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
        if peg_revision == limit_revision:
            return peg_revision, path
        elif peg_revision > limit_revision:
            path = self.get_location(path, peg_revision, limit_revision)
            return limit_revision, path
        else:
            while peg_revision != limit_revision:
                mid = (peg_revision + 1 + limit_revision) // 2
                try:
                    path = self.get_location(path, peg_revision, mid)
                except vclib.ItemNotFound:
                    limit_revision = mid - 1
                else:
                    peg_revision = mid
            return peg_revision, path

    def get_symlink_target(self, path_parts, rev):
        """Return the target of the symbolic link versioned at PATH_PARTS
        in REV, or None if that object is not a symlink."""

        path = self._getpath(path_parts)
        path_type = self.itemtype(path_parts, rev)  # does auth-check
        rev = self._getrev(rev)
        url = self._geturl(path)

        # Symlinks must be files with the svn:special property set on them
        # and with file contents which read "link SOME_PATH".
        if path_type != vclib.FILE:
            return None
        pairs = client.svn_client_proplist2(url, _rev2optrev(rev), _rev2optrev(rev), 0, self.ctx)
        props = pairs and pairs[0][1] or {}
        if core.SVN_PROP_SPECIAL not in props:
            return None
        pathspec = ""
        # FIXME: We're being a touch sloppy here, first by grabbing the
        # whole file and then by checking only the first line of it.
        fp = SelfCleanFP(cat_to_tempfile(self, path, rev))
        pathspec = fp.readline()
        fp.close()
        if pathspec[:5] != "link ":
            return None
        return pathspec[5:]
