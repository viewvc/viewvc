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
from svn import fs, _repos, util

# Subversion filesystem paths are '/'-delimited, regardless of OS.
def fs_path_join(base, relative):
  joined_path = base + '/' + relative
  parts = filter(None, string.split(joined_path, '/'))
  return string.join(parts, '/')

  
def _datestr_to_date(datestr, pool):
  return util.svn_time_from_nts(datestr, pool) / 1000000

  
def _fs_rev_props(fsptr, rev, pool):
  author = fs.revision_prop(fsptr, rev, util.SVN_PROP_REVISION_AUTHOR, pool)
  msg = fs.revision_prop(fsptr, rev, util.SVN_PROP_REVISION_LOG, pool)
  date = fs.revision_prop(fsptr, rev, util.SVN_PROP_REVISION_DATE, pool)
  return date, author, msg


class LogEntry:
  "Hold state for each revision's log entry."
  def __init__(self, rev, date, author, msg):
    self.rev = rev
    self.date = date
    self.author = author
    self.state = '' # should we populate this?
    self.changed = 0
    self.log = msg


class LogReceiver:
  "Handler for Subversion log message chunks"
  def __init__(self):
    self.logs = { }

  def receive(self, revision, author, datestr, msg, pool):
    date = _datestr_to_date(datestr, pool)
    self.logs[revision] = LogEntry(revision, date, author, msg)


def get_logs(repos, full_name, files):
  fileinfo = { }
  alltags = {           # all the tags seen in the files of this dir
    'MAIN' : '1',
    'HEAD' : '1',
    }
  for file in files:
    path = fs_path_join(full_name, file)
    rev = fs.node_created_rev(repos.fsroot, path, repos.pool)
    datestr, author, msg = _fs_rev_props(repos.fs_ptr, rev, repos.pool)
    date = _datestr_to_date(datestr, repos.pool)
    new_entry = LogEntry(rev, date, author, msg)
    new_entry.filename = file
    fileinfo[file] = new_entry
  return fileinfo, alltags


def fetch_log(repos, full_name, which_rev=None):
  receiver = LogReceiver();
  alltags = {           # all the tags seen in the files of this dir
    'MAIN' : '1',
    'HEAD' : '1',
    }
  if which_rev is not None:
    datestr, author, msg = _fs_rev_props(repos.fs_ptr, which_rev, repos.pool)
    receiver.receive(which_rev, author, datestr, msg, repos.pool)
  else:
    _repos.get_logs(repos.repos, [ full_name ], repos.rev, 0, 0, 1,
                   receiver.receive, repos.pool)
  return alltags, receiver.logs


def get_file_contents(repos, path):
  len = fs.file_length(repos.fsroot, path, repos.pool)
  stream = fs.file_contents(repos.fsroot, path, repos.pool)
  return util.svn_stream_read(stream, len)

  
class SubversionRepository(vclib.Repository):
  def __init__(self, name, rootpath, pool, rev=None):
    if not os.path.isdir(rootpath):
      raise vclib.ReposNotFound(name)
    self.repos = _repos.svn_repos_open(rootpath, pool)
    self.pool = pool
    self.name = name
    self.rootpath = rootpath
    self.fs_ptr = _repos.svn_repos_fs(self.repos)
    self.rev = rev
    if self.rev is None:
      self.rev = fs.youngest_rev(self.fs_ptr, pool)
    self.fsroot = fs.revision_root(self.fs_ptr, self.rev, self.pool)

  def getitem(self, path_parts):
    basepath = self._getpath(path_parts)
    item = self.itemtype(path_parts)
    if item is vclib.DIR:
      return vclib.Versdir(self, basepath)
    else:
      return vclib.Versfile(self, basepath)

  def itemtype(self, path_parts):
    basepath = self._getpath(path_parts)
    if fs.is_dir(self.fsroot, basepath, self.pool):
      return vclib.DIR
    if fs.is_file(self.fsroot, basepath, self.pool):
      return vclib.FILE
    raise vclib.ItemNotFound(path_parts)

  def _getpath(self, path_parts):
    return string.join(path_parts, '/')

  def _getvf_subdirs(self, basepath):
    entries = fs.dir_entries(self.fsroot, basepath, self.pool)
    subdirs = { }
    names = entries.keys()
    names.sort()
    subpool = util.svn_pool_create(self.pool)
    for name in names:
      child = fs_path_join(basepath, name)
      if fs.is_dir(self.fsroot, child, subpool):
        subdirs[name] = vclib.Versdir(self, child)
      util.svn_pool_clear(subpool)
    util.svn_pool_destroy(subpool)
    return subdirs
    
  def _getvf_files(self, basepath):
    entries = fs.dir_entries(self.fsroot, basepath, self.pool)
    files = { }
    names = entries.keys()
    names.sort()
    subpool = util.svn_pool_create(self.pool)
    for name in names:
      child = fs_path_join(basepath, name)
      if fs.is_file(self.fsroot, child, subpool):
        files[name] = vclib.Versfile(self, child)
      util.svn_pool_clear(subpool)
    util.svn_pool_destroy(subpool)
    return files
  
  def _getvf_info(self, target, basepath):
    if not fs.is_file(self.fsroot, basepath, self.pool):
      raise "Unknown file: %s " % basepath
    # todo
    pass
  
  def _getvf_tree(self, versfile):
    """
    should return a dictionary of Revisions
    Developers: method to be overloaded.
    """
    # todo

  def _getvf_properties(self, target, basepath, revisionnumber):
    """
    Add/update into target's attributes (expected to be an instance of
    Revision) a certain number of attributes:
    rev
    date
    author
    state
    log
    previous revision number
    branches ( a list of revision numbers )
    changes ( string of the form: e.g. "+1 -0 lines" )
    tags
    ... ( there can be other stuff here)
    
    Developers: in the cvs implementation, the method will never be called.
    There is no point in developping this method as  _getvf_tree already
    gets the properties.
    """
    # todo

  def _getvf_cofile(self, target, basepath):
    """
    should return a file object representing the checked out revision.
    Notice that _getvf_co can also add the properties in <target> the
    way _getvf_properties does.  

    Developers: method to be overloaded.
    """
    # todo

