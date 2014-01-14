# -*-python-*-
#
# Copyright (C) 1999-2013 The ViewCVS Group. All Rights Reserved.
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
import sys
import os
import string
import re
import tempfile
import time
import urllib
from svn_repos import Revision, SVNChangedPath, _datestr_to_date, \
                      _compare_paths, _path_parts, _cleanup_path, \
                      _rev2optrev, _fix_subversion_exception, \
                      _split_revprops, _canonicalize_path
from svn import core, delta, client, wc, ra


### Require Subversion 1.3.1 or better. (for svn_ra_get_locations support)
if (core.SVN_VER_MAJOR, core.SVN_VER_MINOR, core.SVN_VER_PATCH) < (1, 3, 1):
  raise Exception, "Version requirement not met (needs 1.3.1 or better)"


### BEGIN COMPATABILITY CODE ###

try:
  SVN_INVALID_REVNUM = core.SVN_INVALID_REVNUM
except AttributeError: # The 1.4.x bindings are missing core.SVN_INVALID_REVNUM
  SVN_INVALID_REVNUM = -1

def list_directory(url, peg_rev, rev, flag, ctx):
  try:
    dirents, locks = client.svn_client_ls3(url, peg_rev, rev, flag, ctx)
  except TypeError: # 1.4.x bindings are goofed
    dirents = client.svn_client_ls3(None, url, peg_rev, rev, flag, ctx)
    locks = {}
  return dirents, locks  

def get_directory_props(ra_session, path, rev):
  try:
    dirents, fetched_rev, props = ra.svn_ra_get_dir(ra_session, path, rev)
  except ValueError: # older bindings are goofed
    props = ra.svn_ra_get_dir(ra_session, path, rev)
  return props

def client_log(url, start_rev, end_rev, log_limit, include_changes,
               cross_copies, cb_func, ctx):
  include_changes = include_changes and 1 or 0
  cross_copies = cross_copies and 1 or 0
  try:
    client.svn_client_log4([url], start_rev, start_rev, end_rev,
                           log_limit, include_changes, not cross_copies,
                           0, None, cb_func, ctx)
  except AttributeError:
    # Wrap old svn_log_message_receiver_t interface with a
    # svn_log_entry_t one.
    def cb_convert(paths, revision, author, date, message, pool):
      class svn_log_entry_t:
        pass
      log_entry = svn_log_entry_t()
      log_entry.changed_paths = paths
      log_entry.revision = revision
      log_entry.revprops = { core.SVN_PROP_REVISION_LOG : message,
                             core.SVN_PROP_REVISION_AUTHOR : author,
                             core.SVN_PROP_REVISION_DATE : date,
                             }
      cb_func(log_entry, pool)
    client.svn_client_log2([url], start_rev, end_rev, log_limit,
                           include_changes, not cross_copies, cb_convert, ctx)


def setup_client_ctx(config_dir):
  # Ensure that the configuration directory exists.
  core.svn_config_ensure(config_dir)

  # Fetch the configuration (and 'config' bit thereof).
  cfg = core.svn_config_get_config(config_dir)
  config = cfg.get(core.SVN_CONFIG_CATEGORY_CONFIG)

  # Here's the compat-sensitive part: try to use
  # svn_cmdline_create_auth_baton(), and fall back to making our own
  # if that fails.
  try:
    auth_baton = core.svn_cmdline_create_auth_baton(1, None, None, config_dir,
                                                    1, 1, config, None)
  except AttributeError:
    auth_baton = core.svn_auth_open([
      client.svn_client_get_simple_provider(),
      client.svn_client_get_username_provider(),
      client.svn_client_get_ssl_server_trust_file_provider(),
      client.svn_client_get_ssl_client_cert_file_provider(),
      client.svn_client_get_ssl_client_cert_pw_file_provider(),
      ])
    if config_dir is not None:
      core.svn_auth_set_parameter(auth_baton,
                                  core.SVN_AUTH_PARAM_CONFIG_DIR,
                                  config_dir)

  # Create, setup, and return the client context baton.
  ctx = client.svn_client_create_context()
  ctx.config = cfg
  ctx.auth_baton = auth_baton
  return ctx

### END COMPATABILITY CODE ###


class LogCollector:
  
  def __init__(self, path, show_all_logs, lockinfo, access_check_func):
    # This class uses leading slashes for paths internally
    if not path:
      self.path = '/'
    else:
      self.path = path[0] == '/' and path or '/' + path
    self.logs = []
    self.show_all_logs = show_all_logs
    self.lockinfo = lockinfo
    self.access_check_func = access_check_func
    self.done = False
    
  def add_log(self, log_entry, pool):
    if self.done:
      return
    paths = log_entry.changed_paths
    revision = log_entry.revision
    msg, author, date, revprops = _split_revprops(log_entry.revprops)
    
    # Changed paths have leading slashes
    changed_paths = paths.keys()
    changed_paths.sort(lambda a, b: _compare_paths(a, b))
    this_path = None
    if self.path in changed_paths:
      this_path = self.path
      change = paths[self.path]
      if change.copyfrom_path:
        this_path = change.copyfrom_path
    for changed_path in changed_paths:
      if changed_path != self.path:
        # If a parent of our path was copied, our "next previous"
        # (huh?) path will exist elsewhere (under the copy source).
        if (string.rfind(self.path, changed_path) == 0) and \
               self.path[len(changed_path)] == '/':
          change = paths[changed_path]
          if change.copyfrom_path:
            this_path = change.copyfrom_path + self.path[len(changed_path):]
    if self.show_all_logs or this_path:
      if self.access_check_func is None \
         or self.access_check_func(self.path[1:], revision):
        entry = Revision(revision, date, author, msg, None, self.lockinfo,
                         self.path[1:], None, None)
        self.logs.append(entry)
      else:
        self.done = True
    if this_path:
      self.path = this_path
    
def cat_to_tempfile(svnrepos, path, rev):
  """Check out file revision to temporary file"""
  temp = tempfile.mktemp()
  stream = core.svn_stream_from_aprfile(temp)
  url = svnrepos._geturl(path)
  client.svn_client_cat(core.Stream(stream), url, _rev2optrev(rev),
                        svnrepos.ctx)
  core.svn_stream_close(stream)
  return temp

class SelfCleanFP:
  def __init__(self, path):
    self._fp = open(path, 'r')
    self._path = path
    self._eof = 0
    
  def read(self, len=None):
    if len:
      chunk = self._fp.read(len)
    else:
      chunk = self._fp.read()
    if chunk == '':
      self._eof = 1
    return chunk
  
  def readline(self):
    chunk = self._fp.readline()
    if chunk == '':
      self._eof = 1
    return chunk

  def readlines(self):
    lines = self._fp.readlines()
    self._eof = 1
    return lines
    
  def close(self):
    self._fp.close()
    os.remove(self._path)

  def __del__(self):
    self.close()
    
  def eof(self):
    return self._eof


class RemoteSubversionRepository(vclib.Repository):
  def __init__(self, name, rootpath, authorizer, utilities, config_dir):
    self.name = name
    self.rootpath = rootpath
    self.auth = authorizer
    self.diff_cmd = utilities.diff or 'diff'
    self.config_dir = config_dir or None

    # See if this repository is even viewable, authz-wise.
    if not vclib.check_root_access(self):
      raise vclib.ReposNotFound(name)

  def open(self):
    # Setup the client context baton, complete with non-prompting authstuffs.
    self.ctx = setup_client_ctx(self.config_dir)
    
    ra_callbacks = ra.svn_ra_callbacks_t()
    ra_callbacks.auth_baton = self.ctx.auth_baton
    self.ra_session = ra.svn_ra_open(self.rootpath, ra_callbacks, None,
                                     self.ctx.config)
    self.youngest = ra.svn_ra_get_latest_revnum(self.ra_session)
    self._dirent_cache = { }
    self._revinfo_cache = { }

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
        if kind == core.svn_node_file:
          pathtype = vclib.FILE
        elif kind == core.svn_node_dir:
          pathtype = vclib.DIR
      except:
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
    url = self._geturl(path)
    ### rev here should be the last history revision of the URL
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
    for name in dirents.keys():
      entry = dirents[name]
      if entry.kind == core.svn_node_dir:
        kind = vclib.DIR
      elif entry.kind == core.svn_node_file:
        kind = vclib.FILE
      else:
        kind = None
      entries.append(vclib.DirEntry(name, kind))
    return entries

  def dirlogs(self, path_parts, rev, entries, options):
    path = self._getpath(path_parts)
    if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
      raise vclib.Error("Path '%s' is not a directory." % path)
    rev = self._getrev(rev)
    dirents, locks = self._get_dirents(path, rev)
    for entry in entries:
      entry_path_parts = path_parts + [entry.name]
      dirent = dirents.get(entry.name, None)
      # dirents is authz-sanitized, so ensure the entry is found therein.
      if dirent is None:
        continue
      # Get authz-sanitized revision metadata.
      entry.date, entry.author, entry.log, revprops, changes = \
                  self._revinfo(dirent.created_rev)
      entry.rev = str(dirent.created_rev)
      entry.size = dirent.size
      entry.lockinfo = None
      if locks.has_key(entry.name):
        entry.lockinfo = locks[entry.name].owner

  def itemlog(self, path_parts, rev, sortby, first, limit, options):
    assert sortby == vclib.SORTBY_DEFAULT or sortby == vclib.SORTBY_REV   
    path_type = self.itemtype(path_parts, rev) # does auth-check
    path = self._getpath(path_parts)
    rev = self._getrev(rev)
    url = self._geturl(path)

    # If this is a file, fetch the lock status and size (as of REV)
    # for this item.
    lockinfo = size_in_rev = None
    if path_type == vclib.FILE:
      basename = path_parts[-1]
      list_url = self._geturl(self._getpath(path_parts[:-1]))
      dirents, locks = list_directory(list_url, _rev2optrev(rev),
                                      _rev2optrev(rev), 0, self.ctx)
      if locks.has_key(basename):
        lockinfo = locks[basename].owner
      if dirents.has_key(basename):
        size_in_rev = dirents[basename].size
    
    # Special handling for the 'svn_latest_log' scenario.
    ### FIXME: Don't like this hack.  We should just introduce
    ### something more direct in the vclib API.
    if options.get('svn_latest_log', 0):
      dir_lh_rev, dir_c_rev = self._get_last_history_rev(path_parts, rev)
      date, author, log, revprops, changes = self._revinfo(dir_lh_rev)
      return [vclib.Revision(dir_lh_rev, str(dir_lh_rev), date, author,
                             None, log, size_in_rev, lockinfo)]

    def _access_checker(check_path, check_rev):
      return vclib.check_path_access(self, _path_parts(check_path),
                                     path_type, check_rev)
      
    # It's okay if we're told to not show all logs on a file -- all
    # the revisions should match correctly anyway.
    lc = LogCollector(path, options.get('svn_show_all_dir_logs', 0),
                      lockinfo, _access_checker)

    cross_copies = options.get('svn_cross_copies', 0)
    log_limit = 0
    if limit:
      log_limit = first + limit
    client_log(url, _rev2optrev(rev), _rev2optrev(1), log_limit, 1,
               cross_copies, lc.add_log, self.ctx)
    revs = lc.logs
    revs.sort()
    prev = None
    for rev in revs:
      # Swap out revision info with stuff from the cache (which is
      # authz-sanitized).
      rev.date, rev.author, rev.log, revprops, changes \
                = self._revinfo(rev.number)
      rev.prev = prev
      prev = rev
    revs.reverse()

    if len(revs) < first:
      return []
    if limit:
      return revs[first:first+limit]
    return revs

  def itemprops(self, path_parts, rev):
    path = self._getpath(path_parts)
    path_type = self.itemtype(path_parts, rev) # does auth-check
    rev = self._getrev(rev)
    url = self._geturl(path)
    pairs = client.svn_client_proplist2(url, _rev2optrev(rev),
                                        _rev2optrev(rev), 0, self.ctx)
    return pairs and pairs[0][1] or {}
  
  def annotate(self, path_parts, rev, include_text=False):
    path = self._getpath(path_parts)
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file." % path)
    rev = self._getrev(rev)
    url = self._geturl(path)

    # Examine logs for the file to determine the oldest revision we are
    # permitted to see.
    log_options = {
      'svn_cross_copies' : 1,
      'svn_show_all_dir_logs' : 1,
      }
    revs = self.itemlog(path_parts, rev, vclib.SORTBY_REV, 0, 0, log_options)
    oldest_rev = revs[-1].number

    # Now calculate the annotation data.  Note that we'll not
    # inherently trust the provided author and date, because authz
    # rules might necessitate that we strip that information out.
    blame_data = []

    def _blame_cb(line_no, revision, author, date,
                  line, pool, blame_data=blame_data):
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

      # Strip text if the caller doesn't want it.
      if not include_text:
        line = None
      blame_data.append(vclib.Annotation(line, line_no + 1, revision, prev_rev,
                                         author, date))
      
    client.blame2(url, _rev2optrev(rev), _rev2optrev(oldest_rev),
                  _rev2optrev(rev), _blame_cb, self.ctx)
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
    except core.SubversionException, e:
      _fix_subversion_exception(e)
      if e.apr_err == vclib.svn.core.SVN_ERR_FS_NOT_FOUND:
        raise vclib.InvalidRevision
      raise

  def isexecutable(self, path_parts, rev):
    props = self.itemprops(path_parts, rev) # does authz-check
    return props.has_key(core.SVN_PROP_EXECUTABLE)
  
  def filesize(self, path_parts, rev):
    path = self._getpath(path_parts)
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file." % path)
    rev = self._getrev(rev)
    dirents, locks = self._get_dirents(self._getpath(path_parts[:-1]), rev)
    dirent = dirents.get(path_parts[-1], None)
    return dirent.size
    
  def _getpath(self, path_parts):
    return string.join(path_parts, '/')

  def _getrev(self, rev):
    if rev is None or rev == 'HEAD':
      return self.youngest
    try:
      if type(rev) == type(''):
        while rev[0] == 'r':
          rev = rev[1:]
      rev = int(rev)
    except:
      raise vclib.InvalidRevision(rev)
    if (rev < 0) or (rev > self.youngest):
      raise vclib.InvalidRevision(rev)
    return rev

  def _geturl(self, path=None):
    if not path:
      return self.rootpath
    path = self.rootpath + '/' + urllib.quote(path)
    return _canonicalize_path(path)

  def _get_dirents(self, path, rev):
    """Return a 2-type of dirents and locks, possibly reading/writing
    from a local cache of that information.  This functions performs
    authz checks, stripping out unreadable dirents."""

    dir_url = self._geturl(path)
    path_parts = _path_parts(path)    
    if path:
      key = str(rev) + '/' + path
    else:
      key = str(rev)

    # Ensure that the cache gets filled...
    dirents_locks = self._dirent_cache.get(key)
    if not dirents_locks:
      tmp_dirents, locks = list_directory(dir_url, _rev2optrev(rev),
                                          _rev2optrev(rev), 0, self.ctx)
      dirents = {}
      for name, dirent in tmp_dirents.items():
        dirent_parts = path_parts + [name]
        kind = dirent.kind 
        if (kind == core.svn_node_dir or kind == core.svn_node_file) \
           and vclib.check_path_access(self, dirent_parts,
                                       kind == core.svn_node_dir \
                                         and vclib.DIR or vclib.FILE, rev):
          lh_rev, c_rev = self._get_last_history_rev(dirent_parts, rev)
          dirent.created_rev = lh_rev
          dirents[name] = dirent
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
    client_log(url, optrev, _rev2optrev(last_changed_rev), 1, 1, 0,
               lc.add_log, self.ctx)
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
      action_map = { 'D' : vclib.DELETED,
                     'A' : vclib.ADDED,
                     'R' : vclib.REPLACED,
                     'M' : vclib.MODIFIED,
                     }

      # Easy out: if we won't use the changed-path info, just return a
      # changes-less tuple.
      if not need_changes:
        return revs.append([date, author, msg, revprops, None])

      # Subversion 1.5 and earlier didn't offer the 'changed_paths2'
      # hash, and in Subversion 1.6, it's offered but broken.
      try: 
        changed_paths = log_entry.changed_paths2
        paths = (changed_paths or {}).keys()
      except:
        changed_paths = log_entry.changed_paths
        paths = (changed_paths or {}).keys()
      paths.sort(lambda a, b: _compare_paths(a, b))

      # If we get this far, our caller needs changed-paths, or we need
      # them for authz-related sanitization.
      changes = []
      found_readable = found_unreadable = 0
      for path in paths:
        change = changed_paths[path]

        # svn_log_changed_path_t (which we might get instead of the
        # svn_log_changed_path2_t we'd prefer) doesn't have the
        # 'node_kind' member.        
        pathtype = None
        if hasattr(change, 'node_kind'):
          if change.node_kind == core.svn_node_dir:
            pathtype = vclib.DIR
          elif change.node_kind == core.svn_node_file:
            pathtype = vclib.FILE
            
        # svn_log_changed_path2_t only has the 'text_modified' and
        # 'props_modified' bits in Subversion 1.7 and beyond.  And
        # svn_log_changed_path_t is without.
        text_modified = props_modified = 0
        if hasattr(change, 'text_modified'):
          if change.text_modified == core.svn_tristate_true:
            text_modified = 1
        if hasattr(change, 'props_modified'):
          if change.props_modified == core.svn_tristate_true:
            props_modified = 1
            
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
        parts = _path_parts(path)
        if vclib.check_path_access(self, parts, vclib.FILE, revision):
          if is_copy and base_path and (base_path != path):
            parts = _path_parts(base_path)
            if not vclib.check_path_access(self, parts, vclib.FILE, base_rev):
              is_copy = 0
              base_path = None
              base_rev = None
              found_unreadable = 1
          changes.append(SVNChangedPath(path, revision, pathtype, base_path,
                                        base_rev, action, is_copy,
                                        text_modified, props_modified))
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
    client_log(self.rootpath, optrev, optrev, 1, need_changes, 0,
               _log_cb, self.ctx)
    return tuple(revs[0])

  def _revinfo(self, rev, include_changed_paths=0):
    """Internal-use, cache-friendly revision information harvester."""

    # Consult the revinfo cache first.  If we don't have cached info,
    # or our caller wants changed paths and we don't have those for
    # this revision, go do the real work.
    rev = self._getrev(rev)
    cached_info = self._revinfo_cache.get(rev)
    if not cached_info \
       or (include_changed_paths and cached_info[4] is None):
      cached_info = self._revinfo_fetch(rev, include_changed_paths)
      self._revinfo_cache[rev] = cached_info
    return cached_info

  ##--- custom --##

  def get_youngest_revision(self):
    return self.youngest
  
  def get_location(self, path, rev, old_rev):
    try:
      results = ra.get_locations(self.ra_session, path, rev, [old_rev])
    except core.SubversionException, e:
      _fix_subversion_exception(e)
      if e.apr_err == core.SVN_ERR_FS_NOT_FOUND:
        raise vclib.ItemNotFound(path)
      raise
    try:
      old_path = results[old_rev]
    except KeyError:
      raise vclib.ItemNotFound(path)
    old_path = _cleanup_path(old_path)
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
      direction = 1
      while peg_revision != limit_revision:
        mid = (peg_revision + 1 + limit_revision) / 2
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
    path_type = self.itemtype(path_parts, rev) # does auth-check
    rev = self._getrev(rev)
    url = self._geturl(path)

    # Symlinks must be files with the svn:special property set on them
    # and with file contents which read "link SOME_PATH".
    if path_type != vclib.FILE:
      return None
    pairs = client.svn_client_proplist2(url, _rev2optrev(rev),
                                        _rev2optrev(rev), 0, self.ctx)
    props = pairs and pairs[0][1] or {}
    if not props.has_key(core.SVN_PROP_SPECIAL):
      return None
    pathspec = ''
    ### FIXME: We're being a touch sloppy here, first by grabbing the
    ### whole file and then by checking only the first line
    ### of it.
    fp = SelfCleanFP(cat_to_tempfile(self, path, rev))
    pathspec = fp.readline()
    fp.close()
    if pathspec[:5] != 'link ':
      return None
    return pathspec[5:]

