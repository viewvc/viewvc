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


class LogEntry:
  "Hold state for each revision's log entry."
  def __init__(self, rev, date, author, msg, filename, copy_path, copy_rev):
    self.rev = str(rev)
    self.date = date
    self.author = author
    self.state = '' # should we populate this?
    self.changed = 0
    self.log = msg
    self.filename = filename
    self.copy_path = copy_path
    self.copy_rev = copy_rev


class NodeHistory:
  def __init__(self):
    self.histories = {}

  def add_history(self, path, revision, pool):
    self.histories[revision] = path
    
  
def _get_history(svnrepos, full_name):
  # Instantiate a NodeHistory collector object.
  history = NodeHistory()

  # Do we want to cross copy history?
  cross_copies = getattr(svnrepos, 'cross_copies', 1)

  # Get the history items for PATH.
  repos.svn_repos_history(svnrepos.fs_ptr, full_name, history.add_history,
                          1, svnrepos.rev, cross_copies, svnrepos.pool)
  return history.histories


def _unparse_action(change_kind):
  if change_kind == fs.path_change_add:
    return "added"
  elif change_kind == fs.path_change_delete:
    return "deleted"
  elif change_kind == fs.path_change_replace:
    return "replaced"
  elif change_kind == fs.path_change_modify:
    return "modified"
  else:
    return None
  

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
  entry = LogEntry(rev, date, author, msg, _trim_path(path), 
                   copyfrom_path and _trim_path(copyfrom_path),
                   copyfrom_rev)
  if fs.is_file(rev_root, path, pool):
    entry.size = fs.file_length(rev_root, path, pool)
  return entry
  

def fetch_log(svnrepos, full_name, which_rev=None):
  alltags = {           # all the tags seen in the files of this dir
    'MAIN' : '1',
    'HEAD' : '1',
    }
  logs = {}

  if which_rev is not None:
    if (which_rev < 0) or (which_rev > svnrepos.youngest):
      raise vclib.InvalidRevision(which_rev)
    entry = _log_helper(svnrepos, which_rev, full_name, svnrepos.pool)
    if entry:
      logs[which_rev] = entry
  else:
    history_set = _get_history(svnrepos, full_name)
    history_revs = history_set.keys()
    history_revs.sort()
    history_revs.reverse()
    subpool = core.svn_pool_create(svnrepos.pool)
    for history_rev in history_revs:
      core.svn_pool_clear(subpool)
      entry = _log_helper(svnrepos, history_rev, history_set[history_rev],
                          subpool)
      if entry:
        logs[history_rev] = entry        
    core.svn_pool_destroy(subpool)
  return alltags, logs


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


def do_diff(svnrepos, path1, rev1, path2, rev2, diffoptions):
  root1 = fs.revision_root(svnrepos.fs_ptr, rev1, svnrepos.pool)
  root2 = fs.revision_root(svnrepos.fs_ptr, rev2, svnrepos.pool)
  return fs.FileDiff(root1, path1, root2, path2, svnrepos.pool, diffoptions)


class StreamPipe:
  def __init__(self, stream):
    self._stream = stream
    self._eof = 0
    
  def read(self, len):
    chunk = None
    if not self._eof:
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
    core.apr_initialize()
    self.pool = core.svn_pool_create(None)
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
    core.svn_pool_destroy(self.pool)
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

  def listdir(self, path_parts):
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

  def _getpath(self, path_parts):
    return string.join(path_parts, '/')

