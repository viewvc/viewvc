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

"Version Control lib driver for remotely accessible Subversion repositories."


# ======================================================================

import vclib
import sys
import os
import string
import re
import tempfile
import popen2

# Subversion swig libs
from svn import core, delta, client, wc


def _rev2optrev(rev):
  rt = core.svn_opt_revision_t()
  if rev:
    if str(rev) == 'HEAD':
      rt.kind = core.svn_opt_revision_head
    else:
      rt.kind = core.svn_opt_revision_number
      rt.value.number = rev
  else:
    rt.kind = core.svn_opt_revision_unspecified
  return rt


def date_from_rev(svnrepos, rev):
  ### this is, obviously, wrong
  return 0


class LogEntry:
  "Hold state for each revision's log entry."
  def __init__(self, rev, date, author, msg, filename, copy_path, copy_rev):
    self.rev = rev
    self.date = date
    self.author = author
    self.state = '' # should we populate this?
    self.changed = 0
    self.log = msg
    self.filename = filename
    self.copy_path = copy_path
    self.copy_rev = copy_rev


class LastHistoryCollector:
  def __init__(self):
    self.has_history = 0
    pass

  def add_history(self, revision, author, date, message):
    self.revision = revision
    self.author = author
    self.date = date
    self.message = message
    self.has_history = 1

  def get_history(self):
    if not self.has_history:
      return None, None, None, None
    return self.revision, self.author, self.date, self.message


def _get_revision_info(svnrepos, rev, pool):
  lhc = LastHistoryCollector()
  def _log_cb(paths, revision, author, date, message, pool, lhc=lhc):
    if not lhc.has_history:
      lhc.add_history(revision, author, date, message)
  client.svn_client_log([svnrepos.rootpath],
                        _rev2optrev(rev), _rev2optrev(rev),
                        0, 0, _log_cb, svnrepos.ctx, pool)
  return lhc.get_history()
  

def fetch_log(svnrepos, full_name):
  alltags = {           # all the tags seen in the files of this dir
    'MAIN' : '1',
    'HEAD' : '1',
    }
  logs = {}

  dir_url = svnrepos.rootpath
  if full_name and full_name != '':
    dir_url = dir_url + '/' + full_name

  def _log_cb(paths, revision, author, date, message, pool,
              logs=logs, path=full_name):
    date = core.svn_time_from_cstring(date, pool)
    entry = LogEntry(revision, date, author, message, path, None, None)
    entry.size = 0
    logs[revision] = entry
    
  cross_copies = getattr(svnrepos, 'cross_copies', 1)
  client.svn_client_log([dir_url], _rev2optrev(1), _rev2optrev(svnrepos.rev),
                        0, not cross_copies, _log_cb,
                        svnrepos.ctx, svnrepos.pool)
  return alltags, logs


def get_logs(svnrepos, full_name, files):
  parts = filter(None, string.split(full_name, '/'))
  dirents = svnrepos.get_dirents(parts, svnrepos.rev)
  subpool = core.svn_pool_create(svnrepos.pool)
  rev_info_cache = { }
  for file in files:
    core.svn_pool_clear(subpool)
    entry = dirents[file.name]
    if rev_info_cache.has_key(entry.created_rev):
      rev, author, date, log = rev_info_cache[entry.created_rev]
    else:
      ### i think this needs some get_last_history action to be accurate
      rev, author, date, log = _get_revision_info(svnrepos,
                                                  entry.created_rev, subpool)
      rev_info_cache[entry.created_rev] = rev, author, date, log
    file.rev = rev
    file.author = author
    file.date = core.svn_time_from_cstring(date, subpool) / 1000000
    file.log = log
    file.size = entry.size
  core.svn_pool_destroy(subpool)    


class FileDiff:
  def __init__(self, rev1, url1, rev2, url2, ctx, pool, diffoptions=[]):
    assert url1 or url2

    self.tempfile1 = None
    self.tempfile2 = None

    self.rev1 = rev1
    self.url1 = url1
    self.rev2 = rev2
    self.url2 = url2
    self.diffoptions = diffoptions
    self.ctx = ctx

    # the caller can't manage this pool very well given our indirect use
    # of it. so we'll create a subpool and clear it at "proper" times.
    self.pool = core.svn_pool_create(pool)

  def either_binary(self):
    "Return true if either of the files are binary."
    ### broken
    return 0

  def get_files(self):
    if self.tempfile1:
      # no need to do more. we ran this already.
      return self.tempfile1, self.tempfile2

    self.tempfile1 = tempfile.mktemp()
    stream = core.svn_stream_from_aprfile(self.tempfile1, self.pool)
    client.svn_client_cat(stream, self.url1, _rev2optrev(self.rev1),
                          self.ctx, self.pool)
    core.svn_stream_close(stream)
    self.tempfile2 = tempfile.mktemp()
    stream = core.svn_stream_from_aprfile(self.tempfile2, self.pool)
    client.svn_client_cat(stream, self.url2, _rev2optrev(self.rev2),
                          self.ctx, self.pool)
    core.svn_stream_close(stream)

    # get rid of anything we put into our subpool
    core.svn_pool_clear(self.pool)

    return self.tempfile1, self.tempfile2

  def get_pipe(self):
    self.get_files()

    # use an array for the command to avoid the shell and potential
    # security exposures
    cmd = ["diff"] \
          + self.diffoptions \
          + [self.tempfile1, self.tempfile2]
          
    # the windows implementation of popen2 requires a string
    if sys.platform == "win32":
      cmd = _escape_msvcrt_shell_command(cmd)

    # open the pipe, forget the end for writing to the child (we won't),
    # and then return the file object for reading from the child.
    fromchild, tochild = popen2.popen2(cmd)
    tochild.close()
    return fromchild

  def __del__(self):
    # it seems that sometimes the files are deleted, so just ignore any
    # failures trying to remove them
    if self.tempfile1 is not None:
      try:
        os.remove(self.tempfile1)
      except OSError:
        pass
    if self.tempfile2 is not None:
      try:
        os.remove(self.tempfile2)
      except OSError:
        pass


def _escape_msvcrt_shell_command(argv):
  return '"' + string.join(map(_escape_msvcrt_shell_arg, argv), " ") + '"'

def _escape_msvcrt_shell_arg(arg):
  arg = re.sub(_re_slashquote, r'\1\1\2', arg)
  arg = '"' + string.replace(arg, '"', '"^""') + '"'
  return arg

_re_slashquote = re.compile(r'(\\+)(\"|$)')


def do_diff(svnrepos, path1, rev1, path2, rev2, diffoptions):
  url1 = svnrepos.rootpath + (path1 and '/' + path1)
  url2 = svnrepos.rootpath + (path2 and '/' + path2)
  return FileDiff(rev1, url1, rev2, url2,
                  svnrepos.ctx, svnrepos.pool, diffoptions)


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
  def __init__(self, name, rootpath, rev=None):
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

    # Fetch the youngest, which we'll pray is the largest of all the
    # committed revisions of the root directory's children.
    dirents = client.svn_client_ls(self.rootpath, _rev2optrev('HEAD'), 0,
                                   self.ctx, self.pool)
    self.youngest = -1
    for name in dirents.keys():
      entry = dirents[name]
      self.youngest = max(entry.created_rev, self.youngest)
    if rev:
      self.rev = rev
      if self.rev > self.youngest:
        raise vclib.InvalidRevision(self.rev)
    else:
      self.rev = self.youngest
    self._dirent_cache = { }
    self._dirent_cache[str(self.rev)] = dirents

  def __del__(self):
    core.svn_pool_destroy(self.pool)
    core.apr_terminate()
    
  def itemtype(self, path_parts):
    if not len(path_parts):
      return vclib.DIR
    dirents = self.get_dirents(path_parts[:-1], self.rev)
    try:
      entry = dirents[path_parts[-1]]
      if entry.kind == core.svn_node_dir:
        return vclib.DIR
      if entry.kind == core.svn_node_file:
        return vclib.FILE
    except KeyError:
      raise vclib.ItemNotFound(path_parts)

  def openfile(self, path_parts, rev=None):
    if rev is None:
      rev = self.rev
    else:
      rev = int(rev)
    url = self.rootpath
    if len(path_parts):
      url = self.rootpath + '/' + self._getpath(path_parts)
    tmp_file = tempfile.mktemp()
    stream = core.svn_stream_from_aprfile(tmp_file, self.pool)
    ### rev here should be the last history revision of the URL
    client.svn_client_cat(stream, url, _rev2optrev(rev), self.ctx, self.pool)
    core.svn_stream_close(stream)
    return SelfCleanFP(tmp_file), rev

  def listdir(self, path_parts):
    entries = [ ]
    dirents = self.get_dirents(path_parts, self.rev)
    for name in dirents.keys():
      entry = dirents[name]
      if entry.kind == core.svn_node_dir:
        kind = vclib.DIR
      elif entry.kind == core.svn_node_file:
        kind = vclib.FILE
      entries.append(vclib.DirEntry(name, kind))
    return entries

  def _getpath(self, path_parts):
    return string.join(path_parts, '/')

  def get_dirents(self, path_parts, rev):
    if len(path_parts):
      path = self._getpath(path_parts)
      key = str(rev) + '/' + path
      dir_url = self.rootpath + '/' + path
    else:
      path = None
      key = str(rev)
      dir_url = self.rootpath
    dirents = self._dirent_cache.get(key)
    if dirents:
      return dirents
    dirents = client.svn_client_ls(dir_url, _rev2optrev(rev), 0,
                                   self.ctx, self.pool)
    self._dirent_cache[key] = dirents
    return dirents
    
    
