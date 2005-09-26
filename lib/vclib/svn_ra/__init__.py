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
import time
from vclib.svn import Revision, ChangedPath, _datestr_to_date
from svn import core, delta, client, wc, ra


### Require Subversion 1.3.0 or better. (for svn_ra_get_locations support)
if (core.SVN_VER_MAJOR, core.SVN_VER_MINOR, core.SVN_VER_PATCH) < (1, 3, 0):
  raise Exception, "Version requirement not met (needs 1.3.0 or better)"

  
def _rev2optrev(rev):
  rt = core.svn_opt_revision_t()
  if rev is not None:
    if str(rev) == 'HEAD':
      rt.kind = core.svn_opt_revision_head
    else:
      rt.kind = core.svn_opt_revision_number
      rt.value.number = rev
  else:
    rt.kind = core.svn_opt_revision_unspecified
  return rt


def date_from_rev(svnrepos, rev):
  datestr = ra.svn_ra_rev_prop(svnrepos.ra_session, rev,
                               'svn:date', svnrepos.pool)
  return _datestr_to_date(datestr, svnrepos.pool)


def get_location(svnrepos, path, rev):
  try:
    results = ra.get_locations(svnrepos.ra_session, path, svnrepos.rev,
                               [int(rev)], svnrepos.pool)
    return results[int(rev)]
  except:
    raise vclib.ItemNotFound(filter(None, string.split(path, '/')))


def created_rev(svnrepos, full_name):
  kind = ra.svn_ra_check_path(svnrepos.ra_session, full_name, svnrepos.rev,
                              svnrepos.pool)
  if kind == core.svn_node_dir:
    props = ra.svn_ra_get_dir(svnrepos.ra_session, full_name,
                              svnrepos.rev, svnrepos.pool)
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
      for changed_path in changed_paths:
        change = paths[changed_path]
        if change.action == 'D':
          action = 'deleted'
        elif change.action == 'A' or change.action == 'R':
          if change.copyfrom_path and change.copyfrom_rev:
            action = 'copied'
          else:
            action = 'added'
        else:
          action = 'modified'
        ### Wrong, diddily wrong wrong wrong.  Can you say,
        ### "Manufacturing data left and right because it hurts to
        ### figure out the right stuff?"
        self.changes.append(ChangedPath(changed_path[1:], None, 0, 0,
                                        changed_path[1:], 0, action))

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

  
def get_revision_info(svnrepos):
  rev, author, date, log, changes = \
       _get_rev_details(svnrepos, svnrepos.rev, svnrepos.pool)
  return _datestr_to_date(date, svnrepos.pool), author, log, changes


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
      rev, author, date, log, changes = \
           _get_rev_details(svnrepos, entry.created_rev, subpool)
      rev_info_cache[entry.created_rev] = rev, author, date, log
    file.rev = rev
    file.author = author
    file.date = _datestr_to_date(date, subpool)
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
    ### TODO: fix this.  if we use ra-getfile, we can grab props and a
    ### stream for our tempfiles at the same time.  maybe do all this
    ### stuff in __init__() and make either_binary() and get_files()
    ### just hand back cached stuffs.
    return 0

  def get_files(self):
    if self.tempfile1:
      # no need to do more. we ran this already.
      return self.tempfile1, self.tempfile2

    self.tempfile1 = tempfile.mktemp()
    stream = core.svn_stream_from_aprfile(self.tempfile1, self.pool)
    client.svn_client_cat(core.Stream(stream), self.url1,
                          _rev2optrev(self.rev1), self.ctx, self.pool)
    core.svn_stream_close(stream)
    self.tempfile2 = tempfile.mktemp()
    stream = core.svn_stream_from_aprfile(self.tempfile2, self.pool)
    client.svn_client_cat(core.Stream(stream), self.url2,
                          _rev2optrev(self.rev2), self.ctx, self.pool)
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


def get_youngest_revision(svnrepos):
  return svnrepos.youngest


def do_diff(svnrepos, path1, rev1, path2, rev2, diffoptions):
  url1 = svnrepos.rootpath + (path1 and '/' + path1)
  url2 = svnrepos.rootpath + (path2 and '/' + path2)

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

    ra_callbacks = ra.svn_ra_callbacks_t()
    ra_callbacks.auth_baton = ctx.auth_baton
    self.ra_session = ra.svn_ra_open(self.rootpath, ra_callbacks, None,
                                     ctx.config, pool)
    self.youngest = ra.svn_ra_get_latest_revnum(self.ra_session, pool)
    if rev is not None:
      self.rev = rev
      if self.rev > self.youngest:
        raise vclib.InvalidRevision(self.rev)
    else:
      self.rev = self.youngest
    self._dirent_cache = { }

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
    client.svn_client_cat(core.Stream(stream), url,
                          _rev2optrev(rev), self.ctx, self.pool)
    core.svn_stream_close(stream)
    return SelfCleanFP(tmp_file), rev

  def listdir(self, path_parts, options):
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

  def dirlogs(self, path_parts, entries, options):
    get_logs(self, self._getpath(path_parts), entries)

  def itemlog(self, path_parts, rev, options):
    full_name = self._getpath(path_parts)

    if rev is not None:
      try:
        rev = int(rev)
      except ValueError:
        vclib.InvalidRevision(rev)

    # It's okay if we're told to not show all logs on a file -- all
    # the revisions should match correctly anyway.
    lc = LogCollector(full_name, options.get('svn_show_all_dir_logs', 0))
    dir_url = self.rootpath
    if full_name:
      dir_url = dir_url + '/' + full_name

    cross_copies = options.get('svn_cross_copies', 0)
    client.svn_client_log([dir_url], _rev2optrev(self.rev), _rev2optrev(1),
                          1, not cross_copies, lc.add_log,
                          self.ctx, self.pool)
    revs = lc.logs
    revs.sort()
    prev = None
    for rev in revs:
      rev.prev = prev
      prev = rev

    return revs

  def annotate(self, path_parts, rev=None):
    path = self._getpath(path_parts)
    url = self.rootpath + (path and '/' + path)
    if rev is None:
      rev = self.rev
    else:
      rev = int(rev)

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
    
    
class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
