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

"Version Control lib driver for locally accessible Subversion repositories"

import vclib
import os
import os.path
import string
import cStringIO
import signal
import time
import tempfile
import popen
import re
from svn import fs, repos, core, delta


### Require Subversion 1.2.0 or better.
if (core.SVN_VER_MAJOR, core.SVN_VER_MINOR, core.SVN_VER_PATCH) < (1, 2, 0):
  raise Exception, "Version requirement not met (needs 1.2.0 or better)"

  
def _allow_all(root, path, pool):
  """Generic authz_read_func that permits access to all paths"""
  return 1


def _fs_path_join(base, relative):
  # Subversion filesystem paths are '/'-delimited, regardless of OS.
  joined_path = base + '/' + relative
  parts = filter(None, string.split(joined_path, '/'))
  return string.join(parts, '/')


def _cleanup_path(path):
  """Return a cleaned-up Subversion filesystem path"""
  return string.join(filter(None, string.split(path, '/')), '/')
  

def _compare_paths(path1, path2):
  path1_len = len (path1);
  path2_len = len (path2);
  min_len = min(path1_len, path2_len)
  i = 0

  # Are the paths exactly the same?
  if path1 == path2:
    return 0
  
  # Skip past common prefix
  while (i < min_len) and (path1[i] == path2[i]):
    i = i + 1

  # Children of paths are greater than their parents, but less than
  # greater siblings of their parents
  char1 = '\0'
  char2 = '\0'
  if (i < path1_len):
    char1 = path1[i]
  if (i < path2_len):
    char2 = path2[i]
    
  if (char1 == '/') and (i == path2_len):
    return 1
  if (char2 == '/') and (i == path1_len):
    return -1
  if (i < path1_len) and (char1 == '/'):
    return -1
  if (i < path2_len) and (char2 == '/'):
    return 1

  # Common prefix was skipped above, next character is compared to
  # determine order
  return cmp(char1, char2)


def _datestr_to_date(datestr, pool):
  if datestr is None:
    return None
  return core.svn_time_from_cstring(datestr, pool) / 1000000

  
def _fs_rev_props(fsptr, rev, pool):
  author = fs.revision_prop(fsptr, rev, core.SVN_PROP_REVISION_AUTHOR, pool)
  msg = fs.revision_prop(fsptr, rev, core.SVN_PROP_REVISION_LOG, pool)
  date = fs.revision_prop(fsptr, rev, core.SVN_PROP_REVISION_DATE, pool)
  return date, author, msg


def date_from_rev(svnrepos, rev):
  if (rev < 0) or (rev > svnrepos.youngest):
    raise vclib.InvalidRevision(rev)
  datestr = fs.revision_prop(svnrepos.fs_ptr, rev,
                             core.SVN_PROP_REVISION_DATE, svnrepos.pool)
  return _datestr_to_date(datestr, svnrepos.pool)


def get_location(svnrepos, path, rev, old_rev):
  try:
    results = repos.svn_repos_trace_node_locations(svnrepos.fs_ptr, path,
                                                   rev, [old_rev],
                                                   _allow_all, svnrepos.pool)
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
  try:
    if peg_revision == limit_revision:
      return peg_revision, path
    elif peg_revision > limit_revision:
      fsroot = svnrepos._getroot(peg_revision)
      history = fs.node_history(fsroot, path, svnrepos.scratch_pool)
      while history:
        path, peg_revision = fs.history_location(history,
                                                 svnrepos.scratch_pool);
        if peg_revision <= limit_revision:
          return max(peg_revision, limit_revision), _cleanup_path(path)
        history = fs.history_prev(history, 1, svnrepos.scratch_pool)
      return peg_revision, _cleanup_path(path)
    else:
      ### Warning: this is *not* an example of good pool usage.
      orig_id = fs.node_id(svnrepos._getroot(peg_revision), path,
                           svnrepos.scratch_pool)
      while peg_revision != limit_revision:
        mid = (peg_revision + 1 + limit_revision) / 2
        try:
          mid_id = fs.node_id(svnrepos._getroot(mid), path,
                              svnrepos.scratch_pool)
        except core.SubversionException, e:
          if e.apr_err == core.SVN_ERR_FS_NOT_FOUND:
            cmp = -1
          else:
            raise
        else:
          ### Not quite right.  Need a comparison function that only returns
          ### true when the two nodes are the same copy, not just related.
          cmp = fs.compare_ids(orig_id, mid_id)

        if cmp in (0, 1):
          peg_revision = mid
        else:
          limit_revision = mid - 1

      return peg_revision, path
  finally:
    svnrepos._scratch_clear()


def created_rev(svnrepos, full_name, rev):
  fsroot = svnrepos._getroot(rev)
  return fs.node_created_rev(fsroot, full_name, svnrepos.pool)


class Revision(vclib.Revision):
  "Hold state for each revision's log entry."
  def __init__(self, rev, date, author, msg, size,
               filename, copy_path, copy_rev):
    vclib.Revision.__init__(self, rev, str(rev), date, author, None, msg, size)
    self.filename = filename
    self.copy_path = copy_path
    self.copy_rev = copy_rev


class NodeHistory:
  def __init__(self, fs_ptr, show_all_logs):
    self.histories = {}
    self.fs_ptr = fs_ptr
    self.show_all_logs = show_all_logs
    
  def add_history(self, path, revision, pool):
    # If filtering, only add the path and revision to the histories
    # list if they were actually changed in this revision (where
    # change means the path itself was changed, or one of its parents
    # was copied).  This is useful for omitting bubble-up directory
    # changes.
    if not self.show_all_logs:
      rev_root = fs.revision_root(self.fs_ptr, revision, pool)
      changed_paths = fs.paths_changed(rev_root, pool)
      paths = changed_paths.keys()
      if path not in paths:
        # Look for a copied parent
        test_path = path
        found = 0
        subpool = core.svn_pool_create(pool)
        while 1:
          core.svn_pool_clear(subpool)
          off = string.rfind(test_path, '/')
          if off < 0:
            break
          test_path = test_path[0:off]
          if test_path in paths:
            copyfrom_rev, copyfrom_path = \
                          fs.copied_from(rev_root, test_path, subpool)
            if copyfrom_rev >= 0 and copyfrom_path:
              found = 1
              break
        core.svn_pool_destroy(subpool)
        if not found:
          return
    self.histories[revision] = _cleanup_path(path)
    
  
def _get_history(svnrepos, full_name, rev, options={}):
  fsroot = svnrepos._getroot(rev)
  show_all_logs = options.get('svn_show_all_dir_logs', 0)
  if not show_all_logs:
    # See if the path is a file or directory.
    kind = fs.check_path(fsroot, full_name, svnrepos.pool)
    if kind is core.svn_node_file:
      show_all_logs = 1
      
  # Instantiate a NodeHistory collector object.
  history = NodeHistory(svnrepos.fs_ptr, show_all_logs)

  # Do we want to cross copy history?
  cross_copies = options.get('svn_cross_copies', 0)

  # Get the history items for PATH.
  repos.svn_repos_history(svnrepos.fs_ptr, full_name, history.add_history,
                          1, rev, cross_copies, svnrepos.pool)
  return history.histories


class ChangedPath:
  def __init__(self, filename, pathtype, prop_mods, text_mods,
               base_path, base_rev, action, is_copy):
    self.filename = filename
    self.pathtype = pathtype
    self.prop_mods = prop_mods
    self.text_mods = text_mods
    self.base_path = base_path
    self.base_rev = base_rev
    self.action = action
    self.is_copy = is_copy


class ChangedPathSet:
  def __init__(self):
    self.changes = { }

  def add_change(self, change):
    if change.path:
      change.path = _cleanup_path(change.path)
    if change.base_path:
      change.base_path = _cleanup_path(change.base_path)
    path = change.path
    action = 'modified'
    is_copy = 0
    if not change.path:
      action = 'deleted'
      path = change.base_path
    elif change.added:
      action = 'added'
      replace_check_path = path
      if change.base_path and change.base_rev:
        is_copy = 1
        replace_check_path = change.base_path
      if self.changes.has_key(replace_check_path) \
             and self.changes[replace_check_path].action == 'deleted':
        action = 'replaced'
    if change.item_kind == core.svn_node_dir:
      pathtype = vclib.DIR
    elif change.item_kind == core.svn_node_file:
      pathtype = vclib.FILE
    else:
      pathtype = None
    self.changes[path] = ChangedPath(path, pathtype, change.prop_changes,
                                     change.text_changed, change.base_path,
                                     change.base_rev, action, is_copy)

  def get_changes(self):
    changes = self.changes.values()
    changes.sort(lambda a, b: _compare_paths(a.filename, b.filename))
    return changes
    
  
def get_revision_info(svnrepos, rev):
  fsroot = svnrepos._getroot(rev)

  # Get the changes for the revision
  cps = ChangedPathSet()
  editor = repos.ChangeCollector(svnrepos.fs_ptr, fsroot,
                                 svnrepos.pool, cps.add_change)
  e_ptr, e_baton = delta.make_editor(editor, svnrepos.pool)
  repos.svn_repos_replay(fsroot, e_ptr, e_baton, svnrepos.pool)

  # Now get the revision property info.  Would use
  # editor.get_root_props(), but something is broken there...
  datestr, author, msg = _fs_rev_props(svnrepos.fs_ptr, rev, svnrepos.pool)
  date = _datestr_to_date(datestr, svnrepos.pool)

  return date, author, msg, cps.get_changes()


def _log_helper(svnrepos, rev, path, pool):
  rev_root = fs.revision_root(svnrepos.fs_ptr, rev, pool)

  # Was this path@rev the target of a copy?
  copyfrom_rev, copyfrom_path = fs.copied_from(rev_root, path, pool)

  # Assemble our LogEntry
  datestr, author, msg = _fs_rev_props(svnrepos.fs_ptr, rev, pool)
  date = _datestr_to_date(datestr, pool)
  if fs.is_file(rev_root, path, pool):
    size = fs.file_length(rev_root, path, pool)
  else:
    size = None
  entry = Revision(rev, date, author, msg, size, path,
                   copyfrom_path and _cleanup_path(copyfrom_path),
                   copyfrom_rev)
  return entry
  

def _fetch_log(svnrepos, full_name, which_rev, options, pool):
  revs = []

  if options.get('svn_latest_log', 0):
    rev = _log_helper(svnrepos, which_rev, full_name, pool)
    if rev:
      revs.append(rev)
  else:
    history_set = _get_history(svnrepos, full_name, which_rev, options)
    history_revs = history_set.keys()
    history_revs.sort()
    history_revs.reverse()
    subpool = core.svn_pool_create(pool)
    for history_rev in history_revs:
      core.svn_pool_clear(subpool)
      rev = _log_helper(svnrepos, history_rev, history_set[history_rev],
                        subpool)
      if rev:
        revs.append(rev)
    core.svn_pool_destroy(subpool)
  return revs


def _get_last_history_rev(fsroot, path, pool):
  history = fs.node_history(fsroot, path, pool)
  history = fs.history_prev(history, 0, pool)
  history_path, history_rev = fs.history_location(history, pool);
  return history_rev
  
  
def get_logs(svnrepos, full_name, rev, files):
  fsroot = svnrepos._getroot(rev)
  subpool = core.svn_pool_create(svnrepos.pool)
  for file in files:
    core.svn_pool_clear(subpool)
    path = _fs_path_join(full_name, file.name)
    rev = _get_last_history_rev(fsroot, path, subpool)
    datestr, author, msg = _fs_rev_props(svnrepos.fs_ptr, rev, subpool)
    date = _datestr_to_date(datestr, subpool)
    file.rev = str(rev)
    file.date = date
    file.author = author
    file.log = msg
    if file.kind == vclib.FILE:
      file.size = fs.file_length(fsroot, path, subpool)
  core.svn_pool_destroy(subpool)


def get_youngest_revision(svnrepos):
  return svnrepos.youngest

def temp_checkout(svnrepos, path, rev, pool):
  """Check out file revision to temporary file"""
  temp = tempfile.mktemp()
  fp = open(temp, 'wb')
  try:
    root = svnrepos._getroot(rev)
    stream = fs.file_contents(root, path, pool)
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
  def __init__(self, root, path, pool):
    self._pool = core.svn_pool_create(pool)
    self._stream = fs.file_contents(root, path, self._pool)
    self._eof = 0

  def __del__(self):
    core.svn_pool_destroy(self._pool)
    
  def read(self, len=None):
    chunk = None
    if not self._eof:
      if len is None:
        buffer = cStringIO.StringIO()
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
      chunk, self._eof = core.svn_stream_readline(self._stream, '\n',
                                                  self._pool)
      if not self._eof:
        chunk = chunk + '\n'
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


_re_blameinfo = re.compile(r"\s*(\d+)\s*(.*)")

class BlameSource:
  def __init__(self, svn_client_path, rootpath, fs_path, rev, first_rev):
    self.idx = -1
    self.line_number = 1
    self.last = None
    self.first_rev = first_rev
    
    rootpath = os.path.abspath(rootpath)
    url = 'file://' + string.join([rootpath, fs_path], "/")
    fp = popen.popen(svn_client_path,
                     ('blame', "-r%d" % int(rev), "%s@%d" % (url, int(rev))),
                     'rb', 1)
    self.fp = fp
    
  def __getitem__(self, idx):
    if idx == self.idx:
      return self.last
    if idx != self.idx + 1:
      raise BlameSequencingError()
    line = self.fp.readline()
    if not line:
      raise IndexError("No more annotations")
    m = _re_blameinfo.match(line[:17])
    if not m:
      raise vclib.Error("Could not parse blame output at line %i\n%s"
                        % (idx+1, line))
    rev, author = m.groups()
    text = line[18:]
    rev = int(rev)
    prev_rev = None
    if rev > self.first_rev:
      prev_rev = rev - 1
    item = _item(text=text, line_number=idx+1, rev=rev,
                 prev_rev=prev_rev, author=author, date=None)
    self.last = item
    self.idx = idx
    return item


class BlameSequencingError(Exception):
  pass

  
class SubversionRepository(vclib.Repository):
  def __init__(self, name, rootpath, svn_path):
    if not os.path.isdir(rootpath):
      raise vclib.ReposNotFound(name)

    # Initialize some stuff.
    self.pool = None
    self.apr_init = 0
    self.rootpath = rootpath
    self.name = name
    self.svn_client_path = os.path.normpath(os.path.join(svn_path, 'svn'))

    # Register a handler for SIGTERM so we can have a chance to
    # cleanup.  If ViewVC takes too long to start generating CGI
    # output, Apache will grow impatient and SIGTERM it.  While we
    # don't mind getting told to bail, we want to gracefully close the
    # repository before we bail.
    def _sigterm_handler(signum, frame, self=self):
      self._close()
      sys.exit(-1)
    try:
      signal.signal(signal.SIGTERM, _sigterm_handler)
    except ValueError:
      # This is probably "ValueError: signal only works in main
      # thread", which will get thrown by the likes of mod_python
      # when trying to install a signal handler from a thread that
      # isn't the main one.  We'll just not care.
      pass

    # Initialize APR and get our top-level pool.
    core.apr_initialize()
    self.apr_init = 1
    self.pool = core.svn_pool_create(None)
    self.scratch_pool = core.svn_pool_create(self.pool)
    
    # Open the repository and init some other variables.
    self.repos = repos.svn_repos_open(rootpath, self.pool)
    self.fs_ptr = repos.svn_repos_fs(self.repos)
    self.youngest = fs.youngest_rev(self.fs_ptr, self.pool)
    self._fsroots = {}

  def __del__(self):
    self._close()
    
  def _close(self):
    if self.pool:
      core.svn_pool_destroy(self.pool)
      self.pool = None
    if self.apr_init:
      core.apr_terminate()
      self.apr_init = 0

  def _scratch_clear(self):
    core.svn_pool_clear(self.scratch_pool)

  def itemtype(self, path_parts, rev):
    rev = self._getrev(rev)
    basepath = self._getpath(path_parts)
    kind = fs.check_path(self._getroot(rev), basepath, self.scratch_pool)
    self._scratch_clear()
    if kind == core.svn_node_dir:
      return vclib.DIR
    if kind == core.svn_node_file:
      return vclib.FILE
    raise vclib.ItemNotFound(path_parts)

  def openfile(self, path_parts, rev):
    path = self._getpath(path_parts)
    rev = self._getrev(rev)
    fsroot = self._getroot(rev)
    revision = str(_get_last_history_rev(fsroot, path, self.scratch_pool))
    self._scratch_clear()
    fp = FileContentsPipe(fsroot, path, self.pool)
    return fp, revision

  def listdir(self, path_parts, rev, options):
    basepath = self._getpath(path_parts)
    if self.itemtype(path_parts, rev) != vclib.DIR:
      raise vclib.Error("Path '%s' is not a directory." % basepath)

    rev = self._getrev(rev)
    fsroot = self._getroot(rev)
    dirents = fs.dir_entries(fsroot, basepath, self.scratch_pool)
    entries = [ ]
    for entry in dirents.values():
      if entry.kind == core.svn_node_dir:
        kind = vclib.DIR
      elif entry.kind == core.svn_node_file:
        kind = vclib.FILE              
      entries.append(vclib.DirEntry(entry.name, kind))
    self._scratch_clear()
    return entries

  def dirlogs(self, path_parts, rev, entries, options):
    get_logs(self, self._getpath(path_parts), self._getrev(rev), entries)

  def itemlog(self, path_parts, rev, options):
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
    path = self._getpath(path_parts)
    rev = self._getrev(rev)

    revs = _fetch_log(self, path, rev, options, self.scratch_pool)
    self._scratch_clear()
    
    revs.sort()
    prev = None
    for rev in revs:
      rev.prev = prev
      prev = rev

    return revs

  def annotate(self, path_parts, rev):
    path = self._getpath(path_parts)
    rev = self._getrev(rev)
    fsroot = self._getroot(rev)

    history_set = _get_history(self, path, rev, {'svn_cross_copies': 1})
    history_revs = history_set.keys()
    history_revs.sort()
    revision = history_revs[-1]
    first_rev = history_revs[0]
    source = BlameSource(self.svn_client_path, self.rootpath,
                         path, rev, first_rev)
    return source, revision
    
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

  def _getroot(self, rev):
    try:
      return self._fsroots[rev]
    except KeyError:
      r = self._fsroots[rev] = fs.revision_root(self.fs_ptr, rev, self.pool)
      return r

class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
