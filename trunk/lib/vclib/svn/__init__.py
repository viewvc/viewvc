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

# Subversion swig libs
from svn import fs, repos, core, delta

# Subversion filesystem paths are '/'-delimited, regardless of OS.
def _fs_path_join(base, relative):
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
  def __init__(self, fs_ptr, filter_path=0):
    self.histories = {}
    self.fs_ptr = fs_ptr
    self.filter_path = filter_path

  def add_history(self, path, revision, pool):
    # If filtering, only add the path and revision to the histories
    # list if they were actually changed in this revision.  This is
    # useful for omitting bubble-up directory changes.
    if self.filter_path:
      rev_root = fs.revision_root(self.fs_ptr, revision, pool)
      changed_paths = fs.paths_changed(rev_root, pool)
      if path not in changed_paths.keys():
        return
    self.histories[revision] = _trim_path(path)
    
  
def _get_history(svnrepos, full_name, options):
  filter_path = 0
  if options.get('svn_show_all_dir_logs', 0):
    # See if the path is a file or directory.
    kind = fs.check_path(svnrepos.fsroot, full_name, svnrepos.pool)
    if kind is core.svn_node_dir:
      filter_path = 1
      
  # Instantiate a NodeHistory collector object.
  history = NodeHistory(svnrepos.fs_ptr, filter_path)

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
  

def _fetch_log(svnrepos, full_name, which_rev, options):
  revs = []

  if which_rev is not None:
    if (which_rev < 0) or (which_rev > svnrepos.youngest):
      raise vclib.InvalidRevision(which_rev)
    rev = _log_helper(svnrepos, which_rev, full_name, svnrepos.pool)
    if rev:
      revs.append(rev)
  else:
    history_set = _get_history(svnrepos, full_name, options)
    history_revs = history_set.keys()
    history_revs.sort()
    history_revs.reverse()
    subpool = core.svn_pool_create(svnrepos.pool)
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
    file.log_error = 0
    file.rev = str(rev)
    file.date = date
    file.author = author
    file.log = msg
    if file.kind == vclib.FILE:
      file.size = fs.file_length(svnrepos.fsroot, path, subpool)
  core.svn_pool_destroy(subpool)


def do_diff(svnrepos, path1, rev1, path2, rev2, diffoptions):
  root1 = fs.revision_root(svnrepos.fs_ptr, rev1, svnrepos.pool)
  root2 = fs.revision_root(svnrepos.fs_ptr, rev2, svnrepos.pool)
  return fs.FileDiff(root1, path1, root2, path2, svnrepos.pool, diffoptions)


class StreamPipe:
  def __init__(self, stream):
    self._stream = stream
    self._eof = 0
    
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

  
class SubversionRepository(vclib.Repository):
  def __init__(self, name, rootpath, rev=None):
    if not os.path.isdir(rootpath):
      raise vclib.ReposNotFound(name)

    # Initialize some stuff that __del__ will look for.
    self.pool = None
    self.apr_init = 0

    # Initialize APR and get our top-level pool.
    core.apr_initialize()
    self.apr_init = 1
    self.pool = core.svn_pool_create(None)

    # Open the repository and init some other variables.
    self.repos = repos.svn_repos_open(rootpath, self.pool)
    self.name = name
    self.rootpath = rootpath
    self.fs_ptr = repos.svn_repos_fs(self.repos)
    self.rev = rev
    self.youngest = fs.youngest_rev(self.fs_ptr, self.pool)
    if self.rev is None:
      self.rev = self.youngest
    if (self.rev < 0) or (self.rev > self.youngest):
      raise vclib.InvalidRevision(self.rev)
    self.fsroot = fs.revision_root(self.fs_ptr, self.rev, self.pool)

  def __del__(self):
    if self.pool:
      core.svn_pool_destroy(self.pool)
    if self.apr_init:
      core.apr_terminate()
    
  def itemtype(self, path_parts):
    basepath = self._getpath(path_parts)
    kind = fs.check_path(self.fsroot, basepath, self.pool)
    if kind == core.svn_node_dir:
      return vclib.DIR
    if kind == core.svn_node_file:
      return vclib.FILE
    raise vclib.ItemNotFound(path_parts)

  def openfile(self, path_parts, rev=None):
    assert rev is None or int(rev) == self.rev
    path = self._getpath(path_parts)
    fp = StreamPipe(fs.file_contents(self.fsroot, path, self.pool))
    revision = str(_get_last_history_rev(self, path, self.pool))
    return fp, revision

  def listdir(self, path_parts, options):
    basepath = self._getpath(path_parts)
    if self.itemtype(path_parts) != vclib.DIR:
      raise vclib.Error("Path '%s' is not a directory." % basepath)

    entries = [ ]

    for entry in fs.dir_entries(self.fsroot, basepath, self.pool).values():
      if entry.kind == core.svn_node_dir:
        kind = vclib.DIR
      elif entry.kind == core.svn_node_file:
        kind = vclib.FILE              
      entries.append(vclib.DirEntry(entry.name, kind))

    return entries

  def dirlogs(self, path_parts, entries, options):
    get_logs(self, self._getpath(path_parts), entries)

  def filelog(self, path_parts, rev, options):
    full_name = self._getpath(path_parts)

    if rev is not None:
      try:
        rev = int(rev)
      except ValueError:
        vclib.InvalidRevision(rev)

    revs = _fetch_log(self, full_name, rev, options)

    revs.sort()
    prev = None
    for rev in revs:
      rev.prev = prev
      prev = rev

    return revs

  def _getpath(self, path_parts):
    return string.join(path_parts, '/')

