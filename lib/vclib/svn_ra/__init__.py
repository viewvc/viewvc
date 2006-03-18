# -*-python-*-
#
# Copyright (C) 1999-2006 The ViewCVS Group. All Rights Reserved.
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
import popen2
import time
from vclib.svn import Revision, ChangedPath, _datestr_to_date, _compare_paths, _cleanup_path
from svn import core, delta, client, wc, ra


### Require Subversion 1.3.0 or better. (for svn_ra_get_locations support)
if (core.SVN_VER_MAJOR, core.SVN_VER_MINOR, core.SVN_VER_PATCH) < (1, 3, 0):
  raise Exception, "Version requirement not met (needs 1.3.0 or better)"

  
def _rev2optrev(rev):
  assert type(rev) is int
  rt = core.svn_opt_revision_t()
  rt.kind = core.svn_opt_revision_number
  rt.value.number = rev
  return rt


def date_from_rev(svnrepos, rev):
  datestr = ra.svn_ra_rev_prop(svnrepos.ra_session, rev,
                               'svn:date', svnrepos.pool)
  return _datestr_to_date(datestr, svnrepos.pool)


def get_location(svnrepos, path, rev, old_rev):
  try:
    results = ra.get_locations(svnrepos.ra_session, path, rev,
                               [old_rev], svnrepos.pool)
  except core.SubversionException, e:
    if e.apr_err == core.SVN_ERR_FS_NOT_FOUND:
      raise vclib.ItemNotFound(path)
    raise

  try:
    old_path = results[old_rev]
  except KeyError:
    raise vclib.ItemNotFound(path)

  return _cleanup_path(old_path)


def last_rev(svnrepos, path, peg_revision, limit_revision=None):
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
  peg_revision = svnrepos._getrev(peg_revision)
  limit_revision = svnrepos._getrev(limit_revision)
  if peg_revision == limit_revision:
    return peg_revision, path
  elif peg_revision > limit_revision:
    path = get_location(svnrepos, path, peg_revision, limit_revision)
    return limit_revision, path
  else:
    ### Warning: this is *not* an example of good pool usage.
    direction = 1
    while peg_revision != limit_revision:
      mid = (peg_revision + 1 + limit_revision) / 2
      try:
        path = get_location(svnrepos, path, peg_revision, mid)
      except vclib.ItemNotFound:
        limit_revision = mid - 1
      else:
        peg_revision = mid
    return peg_revision, path


def created_rev(svnrepos, full_name, rev):
  kind = ra.svn_ra_check_path(svnrepos.ra_session, full_name, rev,
                              svnrepos.pool)
  if kind == core.svn_node_dir:
    props = ra.svn_ra_get_dir(svnrepos.ra_session, full_name,
                              rev, svnrepos.pool)
    return int(props[core.SVN_PROP_ENTRY_COMMITTED_REV])
  return core.SVN_INVALID_REVNUM


class LastHistoryCollector:
  def __init__(self):
    self.has_history = 0

  def add_history(self, paths, revision, author, date, message, pool):
    if not self.has_history:
      self.has_history = 1
      self.revision = revision
      self.author = author
      self.date = date
      self.message = message
      self.changes = []

      if not paths:
        return
      changed_paths = paths.keys()
      changed_paths.sort(lambda a, b: _compare_paths(a, b))
      action_map = { 'D' : 'deleted',
                     'A' : 'added',
                     'R' : 'replaced',
                     'M' : 'modified',
                     }
      for changed_path in changed_paths:
        change = paths[changed_path]
        action = action_map.get(change.action, 'modified')
        ### Wrong, diddily wrong wrong wrong.  Can you say,
        ### "Manufacturing data left and right because it hurts to
        ### figure out the right stuff?"
        if change.copyfrom_path and change.copyfrom_rev:
          self.changes.append(ChangedPath(changed_path[1:], None, 0, 0,
                                          change.copyfrom_path,
                                          change.copyfrom_rev, action, 1))
        else:
          self.changes.append(ChangedPath(changed_path[1:], None, 0, 0,
                                          changed_path[1:], 0, action, 0))

  def get_history(self):
    if not self.has_history:
      return None, None, None, None, None
    return self.revision, self.author, self.date, self.message, self.changes


def _get_rev_details(svnrepos, rev, pool):
  lhc = LastHistoryCollector()
  client.svn_client_log([svnrepos.rootpath],
                        _rev2optrev(rev), _rev2optrev(rev),
                        1, 0, lhc.add_history, svnrepos.ctx, pool)
  return lhc.get_history()

  
def get_revision_info(svnrepos, rev):
  rev, author, date, log, changes = \
       _get_rev_details(svnrepos, rev, svnrepos.pool)
  return _datestr_to_date(date, svnrepos.pool), author, log, changes


class LogCollector:
  def __init__(self, path, show_all_logs):
    # This class uses leading slashes for paths internally
    if not path:
      self.path = '/'
    else:
      self.path = path[0] == '/' and path or '/' + path
    self.logs = []
    self.show_all_logs = show_all_logs
    
  def add_log(self, paths, revision, author, date, message, pool):
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
      date = _datestr_to_date(date, pool)
      entry = Revision(revision, date, author, message, None,
                       self.path[1:], None, None)
      self.logs.append(entry)
    if this_path:
      self.path = this_path
    

def get_logs(svnrepos, full_name, rev, files):
  dirents = svnrepos._get_dirents(full_name, rev)
  subpool = core.svn_pool_create(svnrepos.pool)
  rev_info_cache = { }
  for file in files:
    core.svn_pool_clear(subpool)
    entry = dirents[file.name]
    if rev_info_cache.has_key(entry.created_rev):
      rev, author, date, log = rev_info_cache[entry.created_rev]
    else:
      ### i think this needs some get_last_history action to be accurate
      rev, author, date, log, changes = \
           _get_rev_details(svnrepos, entry.created_rev, subpool)
      rev_info_cache[entry.created_rev] = rev, author, date, log
    file.rev = rev
    file.author = author
    file.date = _datestr_to_date(date, subpool)
    file.log = log
    file.size = entry.size
  core.svn_pool_destroy(subpool)    

def get_youngest_revision(svnrepos):
  return svnrepos.youngest

def temp_checkout(svnrepos, path, rev, pool):
  """Check out file revision to temporary file"""
  temp = tempfile.mktemp()
  stream = core.svn_stream_from_aprfile(temp, pool)
  url = svnrepos.rootpath + (path and '/' + path)
  client.svn_client_cat(core.Stream(stream), url, _rev2optrev(rev),
                        svnrepos.ctx, pool)
  core.svn_stream_close(stream)
  return temp

class SelfCleanFP:
  def __init__(self, path):
    self._fp = open(path, 'r')
    self._path = path
    self._eof = 0
    
  def read(self, len):
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

  def close(self):
    self._fp.close()
    os.remove(self._path)

  def __del__(self):
    self.close()
    
  def eof(self):
    return self._eof


class SubversionRepository(vclib.Repository):
  def __init__(self, name, rootpath):
    # Init the client app
    core.apr_initialize()
    pool = core.svn_pool_create(None)
    core.svn_config_ensure(None, pool)

    # Start populating our members
    self.pool = pool
    self.name = name
    self.rootpath = rootpath

    # Setup the client context baton, complete with non-prompting authstuffs.
    ctx = client.svn_client_ctx_t()
    providers = []
    providers.append(client.svn_client_get_simple_provider(pool))
    providers.append(client.svn_client_get_username_provider(pool))
    providers.append(client.svn_client_get_ssl_server_trust_file_provider(pool))
    providers.append(client.svn_client_get_ssl_client_cert_file_provider(pool))
    providers.append(client.svn_client_get_ssl_client_cert_pw_file_provider(pool))
    ctx.auth_baton = core.svn_auth_open(providers, pool)
    ctx.config = core.svn_config_get_config(None, pool)
    self.ctx = ctx

    ra_callbacks = ra.svn_ra_callbacks_t()
    ra_callbacks.auth_baton = ctx.auth_baton
    self.ra_session = ra.svn_ra_open(self.rootpath, ra_callbacks, None,
                                     ctx.config, pool)
    self.youngest = ra.svn_ra_get_latest_revnum(self.ra_session, pool)
    self._dirent_cache = { }

  def __del__(self):
    core.svn_pool_destroy(self.pool)
    core.apr_terminate()
    
  def itemtype(self, path_parts, rev):
    path = self._getpath(path_parts[:-1])
    rev = self._getrev(rev)
    if not len(path_parts):
      return vclib.DIR
    dirents = self._get_dirents(path, rev)
    try:
      entry = dirents[path_parts[-1]]
      if entry.kind == core.svn_node_dir:
        return vclib.DIR
      if entry.kind == core.svn_node_file:
        return vclib.FILE
    except KeyError:
      raise vclib.ItemNotFound(path_parts)

  def openfile(self, path_parts, rev):
    rev = self._getrev(rev)
    url = self.rootpath
    if len(path_parts):
      url = self.rootpath + '/' + self._getpath(path_parts)
    tmp_file = tempfile.mktemp()
    stream = core.svn_stream_from_aprfile(tmp_file, self.pool)
    ### rev here should be the last history revision of the URL
    client.svn_client_cat(core.Stream(stream), url,
                          _rev2optrev(rev), self.ctx, self.pool)
    core.svn_stream_close(stream)
    return SelfCleanFP(tmp_file), rev

  def listdir(self, path_parts, rev, options):
    path = self._getpath(path_parts)
    rev = self._getrev(rev)
    entries = [ ]
    dirents = self._get_dirents(path, rev)
    for name in dirents.keys():
      entry = dirents[name]
      if entry.kind == core.svn_node_dir:
        kind = vclib.DIR
      elif entry.kind == core.svn_node_file:
        kind = vclib.FILE
      entries.append(vclib.DirEntry(name, kind))
    return entries

  def dirlogs(self, path_parts, rev, entries, options):
    get_logs(self, self._getpath(path_parts), self._getrev(rev), entries)

  def itemlog(self, path_parts, rev, options):
    full_name = self._getpath(path_parts)
    rev = self._getrev(rev)

    # It's okay if we're told to not show all logs on a file -- all
    # the revisions should match correctly anyway.
    lc = LogCollector(full_name, options.get('svn_show_all_dir_logs', 0))
    dir_url = self.rootpath
    if full_name:
      dir_url = dir_url + '/' + full_name

    cross_copies = options.get('svn_cross_copies', 0)
    client.svn_client_log([dir_url], _rev2optrev(rev), _rev2optrev(1),
                          1, not cross_copies, lc.add_log,
                          self.ctx, self.pool)
    revs = lc.logs
    revs.sort()
    prev = None
    for rev in revs:
      rev.prev = prev
      prev = rev

    return revs

  def annotate(self, path_parts, rev):
    path = self._getpath(path_parts)
    rev = self._getrev(rev)
    url = self.rootpath + (path and '/' + path)

    blame_data = []

    def _blame_cb(line_no, revision, author, date,
                  line, pool, blame_data=blame_data):
      prev_rev = None
      if revision > 1:
        prev_rev = revision - 1
      blame_data.append(_item(text=line, line_number=line_no+1,
                              rev=revision, prev_rev=prev_rev,
                              author=author, date=None))
      
    client.svn_client_blame(url, _rev2optrev(1), _rev2optrev(rev),
                            _blame_cb, self.ctx, self.pool)

    return blame_data, rev
    
  def rawdiff(self, path_parts1, rev1, path_parts2, rev2, type, options={}):
    p1 = self._getpath(path_parts1)
    p2 = self._getpath(path_parts2)
    r1 = self._getrev(rev1)
    r2 = self._getrev(rev2)
    args = vclib._diff_args(type, options)

    try:
      temp1 = temp_checkout(self, p1, r1, self.pool)
      temp2 = temp_checkout(self, p2, r2, self.pool)
      info1 = p1, date_from_rev(self, r1), r1
      info2 = p2, date_from_rev(self, r2), r2
      return vclib._diff_fp(temp1, temp2, info1, info2, args)
    except vclib.svn.core.SubversionException, e:
      if e.apr_err == vclib.svn.core.SVN_ERR_FS_NOT_FOUND:
        raise vclib.InvalidRevision
      raise

  def _getpath(self, path_parts):
    return string.join(path_parts, '/')

  def _getrev(self, rev):
    if rev is None or rev == 'HEAD':
      return self.youngest
    try:
      rev = int(rev)
    except ValueError:
      raise vclib.InvalidRevision(rev)
    if (rev < 0) or (rev > self.youngest):
      raise vclib.InvalidRevision(rev)
    return rev

  def _get_dirents(self, path, rev):
    if path:
      key = str(rev) + '/' + path
      dir_url = self.rootpath + '/' + path
    else:
      key = str(rev)
      dir_url = self.rootpath
    dirents = self._dirent_cache.get(key)
    if dirents:
      return dirents
    dirents = client.svn_client_ls(dir_url, _rev2optrev(rev), 0,
                                   self.ctx, self.pool)
    self._dirent_cache[key] = dirents
    return dirents
    
    
class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
