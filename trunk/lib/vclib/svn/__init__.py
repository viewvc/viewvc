# -*-python-*-
#
# Copyright (C) 1999-2002 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://viewcvs.sourceforge.net/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewcvs.sourceforge.net/
#
# -----------------------------------------------------------------------

"Version Control lib driver for locally accessible Subversion repositories."


# ======================================================================

import vclib
import os
import os.path
import string
import cStringIO
import signal
import time
import popen
from svn import fs, repos, core, delta


### Require Subversion 1.1.0 or better.
if (core.SVN_VER_MAJOR, core.SVN_VER_MINOR, core.SVN_VER_PATCH) < (1, 1, 0):
  raise Exception, "Version requirement not met (needs 1.1.0 or better)"

  
def _allow_all(root, path, pool):
  """Generic authz_read_func that permits access to all paths"""
  return 1


def _fs_path_join(base, relative):
  # Subversion filesystem paths are '/'-delimited, regardless of OS.
  joined_path = base + '/' + relative
  parts = filter(None, string.split(joined_path, '/'))
  return string.join(parts, '/')


def _trim_path(path):
  assert path[0] == '/'
  return path[1:]

  
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


def get_location(svnrepos, path, rev):
  try:
    results = repos.svn_repos_trace_node_locations(svnrepos.fs_ptr, path,
                                                   svnrepos.rev, [int(rev)],
                                                   _allow_all, svnrepos.pool)
    return results[int(rev)]
  except:
    raise vclib.ItemNotFound(filter(None, string.split(path, '/')))
  

def created_rev(svnrepos, full_name):
  return fs.node_created_rev(svnrepos.fsroot, full_name, svnrepos.pool)


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
    self.histories[revision] = _trim_path(path)
    
  
def _get_history(svnrepos, full_name, options):
  show_all_logs = options.get('svn_show_all_dir_logs', 0)
  if not show_all_logs:
    # See if the path is a file or directory.
    kind = fs.check_path(svnrepos.fsroot, full_name, svnrepos.pool)
    if kind is core.svn_node_file:
      show_all_logs = 1
      
  # Instantiate a NodeHistory collector object.
  history = NodeHistory(svnrepos.fs_ptr, show_all_logs)

  # Do we want to cross copy history?
  cross_copies = options.get('svn_cross_copies', 0)

  # Get the history items for PATH.
  repos.svn_repos_history(svnrepos.fs_ptr, full_name, history.add_history,
                          1, svnrepos.rev, cross_copies, svnrepos.pool)
  return history.histories


class ChangedPath:
  def __init__(self, filename, pathtype, prop_mods, text_mods,
               base_path, base_rev, action):
    self.filename = filename
    self.pathtype = pathtype
    self.prop_mods = prop_mods
    self.text_mods = text_mods
    self.base_path = base_path
    self.base_rev = base_rev
    self.action = action


def get_revision_info(svnrepos):
  # Get the revision property info
  date, author, msg = _fs_rev_props(svnrepos.fs_ptr, svnrepos.rev,
                                    svnrepos.pool)
  date = _datestr_to_date(date, svnrepos.pool)

  ### TODO: Switch to the new repos.ChangeCollector interface (pass in
  ### a root, get changes with editor.get_changes(), etc.)

  # Now, get the changes for the revision
  editor = repos.RevisionChangeCollector(svnrepos.fs_ptr,
                                         svnrepos.rev,
                                         svnrepos.pool)
  e_ptr, e_baton = delta.make_editor(editor, svnrepos.pool)
  repos.svn_repos_replay(svnrepos.fsroot, e_ptr, e_baton, svnrepos.pool)

  # get all the changes and sort by path
  changelist = editor.changes.items()
  changelist.sort()
  changes = []
  for path, change in changelist:
    if not change.path:
      action = 'deleted'
    elif change.added:
      if change.base_path and change.base_rev:
        action = 'copied'
      else:
        action = 'added'
    else:
      action = 'modified'
    if change.item_kind == core.svn_node_dir:
      pathtype = vclib.DIR
    elif change.item_kind == core.svn_node_file:
      pathtype = vclib.FILE
    else:
      pathtype = None
    changes.append(ChangedPath(path, pathtype, change.prop_changes,
                               change.text_changed, change.base_path,
                               change.base_rev, action))
  return date, author, msg, changes


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
                   copyfrom_path and _trim_path(copyfrom_path),
                   copyfrom_rev)
  return entry
  

def _fetch_log(svnrepos, full_name, which_rev, options, pool):
  revs = []

  if which_rev is not None:
    if (which_rev < 0) or (which_rev > svnrepos.youngest):
      raise vclib.InvalidRevision(which_rev)
    rev = _log_helper(svnrepos, which_rev, full_name, pool)
    if rev:
      revs.append(rev)
  else:
    history_set = _get_history(svnrepos, full_name, options)
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


def _get_last_history_rev(svnrepos, path, pool):
  history = fs.node_history(svnrepos.fsroot, path, pool)
  history = fs.history_prev(history, 0, pool)
  history_path, history_rev = fs.history_location(history, pool);
  return history_rev
  
  
def get_logs(svnrepos, full_name, files):
  subpool = core.svn_pool_create(svnrepos.pool)
  for file in files:
    core.svn_pool_clear(subpool)
    path = _fs_path_join(full_name, file.name)
    rev = _get_last_history_rev(svnrepos, path, subpool)
    datestr, author, msg = _fs_rev_props(svnrepos.fs_ptr, rev, subpool)
    date = _datestr_to_date(datestr, subpool)
    file.rev = str(rev)
    file.date = date
    file.author = author
    file.log = msg
    if file.kind == vclib.FILE:
      file.size = fs.file_length(svnrepos.fsroot, path, subpool)
  core.svn_pool_destroy(subpool)


def get_youngest_revision(svnrepos):
  return svnrepos.youngest

  
def do_diff(svnrepos, path1, rev1, path2, rev2, diffoptions):
  root1 = fs.revision_root(svnrepos.fs_ptr, rev1, svnrepos.pool)
  root2 = fs.revision_root(svnrepos.fs_ptr, rev2, svnrepos.pool)

  date1 = date_from_rev(svnrepos, rev1)
  date2 = date_from_rev(svnrepos, rev2)
  if date1 is not None:
    date1 = time.strftime('%Y/%m/%d %H:%M:%S', time.gmtime(date1))
  else:
    date1 = ''
  if date2 is not None:
    date2 = time.strftime('%Y/%m/%d %H:%M:%S', time.gmtime(date2))
  else:
    date2 = ''

  diffoptions.append("-L")
  diffoptions.append("%s\t%s\t%i" % (path1, date1, rev1))
  diffoptions.append("-L")
  diffoptions.append("%s\t%s\t%i" % (path2, date2, rev2))

  return fs.FileDiff(root1, path1, root2, path2, svnrepos.pool, diffoptions)


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
      chunk = core.svn_stream_readline(self._stream)
    if not chunk:
      self._eof = 1
    return chunk

  def close(self):
    return core.svn_stream_close(self._stream)

  def eof(self):
    return self._eof


class BlameSource:
  def __init__(self, svn_client_path, rootpath, fs_path, rev):
    self.idx = -1
    self.line_number = 1
    self.last = None

    rootpath = os.path.abspath(rootpath)
    url = 'file://' + string.join([rootpath, fs_path], "/")
    self.fp = popen.popen(svn_client_path,
                          ('blame', "%s@%d" % (url, int(rev))), 'rb', 1)
    
  def __getitem__(self, idx):
    if idx == self.idx:
      return self.last
    if self.fp.eof():
      raise IndexError("No more annotations")
    if idx != self.idx + 1:
      raise BlameSequencingError()
    line = self.fp.readline()
    if not line:
      raise IndexError("No more annotations")
    rev, author = line[:17].split(None, 1)
    text = line[18:]
    rev = int(rev)
    if rev > 1:
      prev_rev = rev - 1
    item = _item(text=text, line_number=idx+1, rev=rev,
                 prev_rev=prev_rev, author=author, date=None)
    self.last = item
    self.idx = idx
    return item
  

class BlameSequencingError(Exception):
  pass

  
class SubversionRepository(vclib.Repository):
  def __init__(self, name, rootpath, svn_path, rev=None):
    if not os.path.isdir(rootpath):
      raise vclib.ReposNotFound(name)

    # Initialize some stuff.
    self.pool = None
    self.apr_init = 0
    self.rootpath = rootpath
    self.name = name
    self.rev = rev
    self.svn_client_path = os.path.normpath(os.path.join(svn_path, 'svn'))

    # Register a handler for SIGTERM so we can have a chance to
    # cleanup.  If ViewCVS takes too long to start generating CGI
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
    if self.rev is None:
      self.rev = self.youngest
    if (self.rev < 0) or (self.rev > self.youngest):
      raise vclib.InvalidRevision(self.rev)
    self.fsroot = fs.revision_root(self.fs_ptr, self.rev, self.pool)

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
    
  def itemtype(self, path_parts):
    basepath = self._getpath(path_parts)
    kind = fs.check_path(self.fsroot, basepath, self.scratch_pool)
    self._scratch_clear()
    if kind == core.svn_node_dir:
      return vclib.DIR
    if kind == core.svn_node_file:
      return vclib.FILE
    raise vclib.ItemNotFound(path_parts)

  def openfile(self, path_parts, rev=None):
    assert rev is None or int(rev) == self.rev
    path = self._getpath(path_parts)
    revision = str(_get_last_history_rev(self, path, self.scratch_pool))
    self._scratch_clear()
    fp = FileContentsPipe(self.fsroot, path, self.pool)
    return fp, revision

  def listdir(self, path_parts, options):
    basepath = self._getpath(path_parts)
    if self.itemtype(path_parts) != vclib.DIR:
      raise vclib.Error("Path '%s' is not a directory." % basepath)

    dirents = fs.dir_entries(self.fsroot, basepath, self.scratch_pool)
    entries = [ ]
    for entry in dirents.values():
      if entry.kind == core.svn_node_dir:
        kind = vclib.DIR
      elif entry.kind == core.svn_node_file:
        kind = vclib.FILE              
      entries.append(vclib.DirEntry(entry.name, kind))
    self._scratch_clear()
    return entries

  def dirlogs(self, path_parts, entries, options):
    get_logs(self, self._getpath(path_parts), entries)

  def itemlog(self, path_parts, rev, options):
    full_name = self._getpath(path_parts)

    if rev is not None:
      try:
        rev = int(rev)
      except ValueError:
        vclib.InvalidRevision(rev)

    revs = _fetch_log(self, full_name, rev, options, self.scratch_pool)
    self._scratch_clear()
    
    revs.sort()
    prev = None
    for rev in revs:
      rev.prev = prev
      prev = rev

    return revs

  def annotate(self, path_parts, rev=None):
    if not rev:
      rev = self.rev
    path = self._getpath(path_parts)
    revision = str(_get_last_history_rev(self, path, self.scratch_pool))
    source = BlameSource(self.svn_client_path, self.rootpath, path, rev)
    return source, revision
    
  def rawdiff(self, path1, rev1, path2, rev2, type, options={}):
    """see vclib.Repository.rawdiff docstring
    
    option values returned by this implementation
      diffobj - reference to underlying FileDiff object
    """
    p1 = self._getpath(path1)
    p2 = self._getpath(path2)
    args = vclib._diff_args(type, options)

    # Need to keep a reference to the FileDiff object around long
    # enough to use.  It destroys its underlying temporary files when
    # the class is destroyed.
    diffobj = options['diffobj'] = \
      do_diff(self, p1, int(rev1), p2, int(rev2), args)
  
    try:
      return diffobj.get_pipe()
    except vclib.svn.core.SubversionException, e:
      if e.apr_err == vclib.svn.core.SVN_ERR_FS_NOT_FOUND:
        raise vclib.InvalidRevision
      raise e

  def _getpath(self, path_parts):
    return string.join(path_parts, '/')


class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
