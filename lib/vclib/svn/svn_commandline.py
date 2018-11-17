# -*-python-*-
#
# Copyright (C) 1999-2018 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

"""Version Control lib driver to access Subversion repositories
via commandline client 'svn'.
"""

import sys
import xml.etree.ElementTree
import subprocess
if sys.version_info[0] >= 3:
  PY3 = True
  import functools
  from urllib.parse import quote as _quote
  long = int
else:
  from urllib import quote as _quote

import vclib
from . import _canonicalize_path
from .svn_common import SubversionRepository, Revision, SVNChangedPath, \
                        _compare_paths, _path_parts, _getpath, _cleanup_path

PY3 = (sys.version_info[0] >= 3)


class SvnCommandError(vclib.Error):
  def __init__(self, errout, cmd, retcode):
    self.errout = errout
    self.cmd = cmd
    self.retcode = retcode
    vclib.Error.__init__(self,
                         ('svn %s exit with code %d: %s'
                          %  (cmd, retcode, errout)))

# here's a constants that cannot be retrived from library...
SVN_PROP_PREFIX = "svn:"
SVN_PROP_REVISION_AUTHOR = SVN_PROP_PREFIX + "author"
SVN_PROP_REVISION_LOG = SVN_PROP_PREFIX + "log"
SVN_PROP_REVISION_DATE = SVN_PROP_PREFIX + "date"
SVN_PROP_SPECIAL = SVN_PROP_PREFIX + "special"
SVN_PROP_EXECUTABLE = SVN_PROP_PREFIX + "executable"

# we don't use svn_node_kind_t in this module, however, we need symbols
# to handle node type infomation in xml tree
# (bringing from subversion/libsvn_subr/types.c on subversion 1.11.0)
# svn_node_kind_t
svn_node_none = 'none'
svn_node_file = 'file'
svn_node_dir = 'dir'
svn_node_symlink = 'symlink'
svn_node_unknown = 'unknown'
# svn_tristate_t
svn_tristate_true = 'true'
svn_tristate_false = 'false'
# svn_tristate__to_word() returns NULL for svn_tristate_unknown and
# for unknown value, however we will see it through the xml output
# if exists. so it can be ''
svn_tristate_unknown = ''


class ProcessReadPipe(object):
  """child process pipe which cares child's return code. if return code is
     other than 0, readed file content is incomplete or invalid."""

  def __init__(self, proc):
    assert isinstance(proc, subprocess.Popen)
    rc = proc.poll()
    if rc:
      try:
        errout = proc.stderr.read()
      except Exception:
        pass
      raise SvnCommandError(errout, cmd, rc)
    self.proc = proc
    self._eof = 0

  def read(self, len=None):
    if len:
      chunk = self.proc.stdout.read(len)
    else:
      chunk = self.proc.stdout.read()
    if self.proc.returncode is None:
      rc = self.proc.poll()
      if rc:
        try:
          errout = self.proc.stderr.read()
        except Exception:
          pass
        self._eof = 1
        raise SvnCommandError(errout, cmd, rc)
    if chunk == '':
      self._eof = 1
    return chunk

  def readline(self):
    chunk = self.proc.stdout.readline()
    if self.proc.returncode is None:
      rc = self.proc.poll()
      if rc:
        try:
          errout = self.proc.stderr.read()
        except Exception:
          pass
        self._eof = 1
        raise SvnCommandError(errout, cmd, rc)
    if chunk == '':
      self._eof = 1
    return chunk

  def readlines(self):
    chunk = self.proc.stdout.readlines()
    if self.proc.returncode is None:
      rc = self.proc.poll()
      if rc:
        try:
          errout = self.proc.stderr.read()
        except Exception:
          pass
        self._eof = 1
        raise SvnCommandError(errout, cmd, rc)
    self._eof = 1
    return chunk

  def close(self):
    self.proc.stdout.close()
    if self.proc.returncode is None:
       # may be last chance to tell the data is invalid or incomplete
      rc = self.proc.poll()
      if rc:
        try:
          errout = self.proc.stderr.read()
        except Exception:
          pass
        self._eof = 1
        raise SvnCommandError(errout, cmd, rc)

  def __del__(self):
    try:
       self.close()
    except SvnCommandError:
       raise
    except:
      pass

class CmdLineSubversionRepository(SubversionRepository):
  def __init__(self, name, rootpath, authorizer, utilities, config_dir):
    SubversionRepository.__init__(self, name, rootpath, authorizer, utilities,
                                  config_dir)
    self.svn_version = self.get_svn_version()

  def open(self):
    # get head revison of root
    et = self.svn_cmd_xml('propget', ['--revprop', '-r', 'HEAD',
                          SVN_PROP_REVISION_DATE, self.rootpath])
    self.youngest = long(et.find('revprops').attrib['rev'])
    self._dirent_cache = { }
    self._revinfo_cache = { }

    # See if a universal read access determination can be made.
    if self.auth and self.auth.check_universal_access(self.name) == 1:
      self.auth = None

  def itemtype(self, path_parts, rev):
    pathtype = None
    if not len(path_parts):
      pathtype = vclib.DIR
    else:
      rev = self._getrev(rev)
      url = self._geturl(_getpath(path_parts)) + ('@%s' % rev)
      try:
        if self.svn_version >= (1, 9, 0):
          kind = self.svn_cmd('info', ['--depth=empty', '-r%s' % rev,
                                       '--show-item=kind', '--no-newline',
                                       url])
        else:
          et = self.svn_cmd_xml('info', ['--depth=empty', '-r%d' %rev, url])
          kind = et.find('entry').attrib['kind']
        if kind == 'file':
          pathtype = vclib.FILE
        elif kind == 'dir':
          pathtype = vclib.DIR
      except:
        pass
    if pathtype is None:
      raise vclib.ItemNotFound(path_parts)
    if not vclib.check_path_access(self, path_parts, pathtype, rev):
      raise vclib.ItemNotFound(path_parts)
    return pathtype

  def openfile(self, path_parts, rev, options):
    path = _getpath(path_parts)
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file." % path)
    rev = self._getrev(rev)
    url = self._geturl(path) + ('@%s' % rev)
    if self.svn_version >= (1, 9, 0):
      # we can use --ignore-keywords, which is useful to make a diff
      # by using our internal function
      proc = self._do_svn_cmd('cat', ['-r%s' % rev, '--ignore-keywords', url])
    else:
      proc = self._do_svn_cmd('cat', ['-r%s' % rev, url])
    ### rev here should be the last history revision of the URL
    fp = ProcessReadPipe(proc)
    lh_rev, c_rev = self._get_last_history_rev(path_parts, rev)
    return fp, lh_rev

  def listdir(self, path_parts, rev, options):
    path = _getpath(path_parts)
    if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
      raise vclib.Error("Path '%s' is not a directory." % path)
    rev = self._getrev(rev)
    entries = []
    dirents = self._get_dirents(path, rev)
    for name, entry in dirents.items():
      if entry.attrib['kind'] == svn_node_dir:
        kind = vclib.DIR
      elif entry.attrib['kind'] == svn_node_file:
        kind = vclib.FILE
      else:
        kind = None
      entries.append(vclib.DirEntry(name, kind))
    return entries

  def dirlogs(self, path_parts, rev, entries, options):
    path = _getpath(path_parts)
    if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
      raise vclib.Error("Path '%s' is not a directory." % path)
    rev = self._getrev(rev)
    dirents = self._get_dirents(path, rev)
    for entry in entries:
      entry_path_parts = path_parts + [entry.name]
      dirent = dirents.get(entry.name, None)
      # dirents is authz-sanitized, so ensure the entry is found therein.
      if dirent is None:
        continue
      # Get authz-sanitized revision metadata.
      created_rev_elm = dirent.find('created_rev')
      assert created_rev_elm is not None
      entry.rev = created_rev_elm.text
      entry.date, entry.author, entry.log, revprops, changes = \
                  self._revinfo(long(entry.rev))
      size_elm = dirent.find('size')
      if size_elm is not None:
        entry.size = long(dirent.find('size').text)
      else:
        entry.size = None
      entry.lockinfo = None
      lockinfo = dirent.find('lock')
      if lockinfo is not None:
        entry.lockinfo = lockinfo.find('owner').text

  def itemlog(self, path_parts, rev, sortby, first, limit, options):
    raise vclib.UnsupportedFeature()

  def itemprops(self, path_parts, rev):
    path = _getpath(path_parts)
    path_type = self.itemtype(path_parts, rev) # does auth-check
    rev = self._getrev(rev)
    url = self._geturl(path) + ('@%s' % rev)

    et = self.svn_cmd_xml('proplist', ['--depth=empty', '-r%d' % rev,
                                       '-v', url])
    props = {}
    for prop in et.findall('./target/property'):
      props[prop.attrib['name']] = prop.text
    return props

  def rawdiff(self, path_parts1, rev1, path_parts2, rev2, type, options={}):
    raise vclib.UnsupportedFeature()

  def annotate(self, path_parts, rev, include_text=False):
    raise vclib.UnsupportedFeature()

  def revinfo(self, rev):
    raise vclib.UnsupportedFeature()

  def isexecutable(self, path_parts, rev):
    props = self.itemprops(path_parts, rev) # does authz-check
    return props.has_key(SVN_PROP_EXECUTABLE)

  def filesize(self, path_parts, rev):
    path = _getpath(path_parts)
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file." % path)
    rev = self._getrev(rev)
    dirents = self._get_dirents(_getpath(path_parts[:-1]), rev)
    dirent = dirents.get(path_parts[-1], None)
    return long(dirent.find('size').text)

  def get_location(self, path, rev, old_rev):
    raise UnsupportedFeature()

  def created_rev(self, path, rev):
    lh_rev, c_rev = self._get_last_history_rev(_path_parts(path), rev)
    return lh_rev

  def get_symlink_target(self, path_parts, rev):
    raise UnsupportedFeature()

  ### helper functions ###

  def _geturl(self, path=None):
    if not path:
      return self.rootpath
    path = self.rootpath + '/' + _quote(path)
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
    dirents = self._dirent_cache.get(key)
    if not dirents:
      tmp_dirents = self.list_directory(dir_url, rev, rev)
      dirents = {}
      # tmp_dirents._root is <lists> tmp_dirents._root._children is [<list>]
      for entry in tmp_dirents.findall('./list/entry'):
        kind = entry.attrib['kind']
        name = entry.find('name').text
        dirent_parts = path_parts + [name]
        if (kind == svn_node_dir or kind == svn_node_file) \
           and vclib.check_path_access(self, dirent_parts,
                                       kind == svn_node_dir \
                                         and vclib.DIR or vclib.FILE, rev):
          lh_rev, c_rev = self._get_last_history_rev(dirent_parts, rev)
          elm = xml.etree.ElementTree.Element('created_rev')
          elm.text = str(lh_rev)
          entry.append(elm)
          dirents[name] = entry
      self._dirent_cache[key] = dirents

    # ...then return the goodies from the cache.
    return dirents

  def _get_last_history_rev(self, path_parts, rev):
    """Return the a 2-tuple which contains:
         - the last interesting revision equal to or older than REV in
           the history of PATH_PARTS.
         - the created_rev of of PATH_PARTS as of REV."""

    path = _getpath(path_parts)
    url = self._geturl(_getpath(path_parts))
    rev = self._getrev(rev)
    url = url + ('@%s' % rev)
    if self.svn_version >= (1, 9, 0):
      last_changed_rev = self.svn_cmd('info', ['--depth=empty', '-r%s' % rev,
                                      '--show-item=last-changed-revision',
                                      '--no-newline', url])
    else:
      et = self.svn_cmd_xml('info', ['--depth=empty', '-r%s' % rev, url])
      last_changed_rev = et.find('entry').attrib['last-changed-revision']

    # Now, this object might not have been directly edited since the
    # last-changed-rev, but it might have been the child of a copy.
    # To determine this, we'll run a potentially no-op log between
    # LAST_CHANGED_REV and REV.
    revopt = "-r%s:%s" % (rev, last_changed_rev)
    et = self.svn_cmd_xml('log', [revopt, '-l', '1', '-v', '--stop-on-copy',
                                  url])
    assert len(et._root._children) == 1
    # et._root is element <log>, and its only child is element <logentry>
    # with 'revision attribute'
    return (long(et._root._children[0].attrib['revision']),
            long(last_changed_rev))

  def _revinfo_fetch(self, rev, include_changed_paths=0):
    need_changes = include_changed_paths or self.auth
    revopt = "-r%s" % rev
    if need_changes:
      et = self.svn_cmd_xml('log', [revopt, '-l', '1', '-v', '--stop-on-copy',
                                    '--with-all-revprops', self.rootpath])
    else:
      et = self.svn_cmd_xml('log', [revopt, '-l', '1', '--stop-on-copy',
                                    '--with-all-revprops', self.rootpath])
    log_entry = et.find('./logentry')
    revison = long(log_entry.attrib['revision'])
    msg = log_entry.find('msg').text
    author = log_entry.find('author').text
    date = log_entry.find('date').text
    revprops = { SVN_PROP_REVISION_LOG : msg,
                 SVN_PROP_REVISION_AUTHOR : author,
                 SVN_PROP_REVISION_DATE : date }
    for prop in log_entry.findall('revprops/property'):
      revprops[prop.attrib['name']] = prop.text

    # Easy out: if we won't use the changed-path info, just return a
    # changes-less tuple.
    if not need_changes:
      return [date, author, msg, revprops, None]

    action_map = { 'D' : vclib.DELETED,
                   'A' : vclib.ADDED,
                   'R' : vclib.REPLACED,
                   'M' : vclib.MODIFIED,
                   }

    paths = log_entry.findall('paths/path')
    if PY3:
      paths.sort(key=functools.cmp_to_key(
                          lambda a, b: _compare_paths(a.text, b.text)))
    else:
      paths.sort(lambda a, b: _compare_paths(a.text, b.text))

    # If we get this far, our caller needs changed-paths, or we need
    # them for authz-related sanitization.
    changes = []
    found_readable = found_unreadable = 0
    for change in paths:
      path = change.text
      # svn_log_changed_path_t (which we might get instead of the
      # svn_log_changed_path2_t we'd prefer) doesn't have the
      # 'node_kind' member.
      pathtype = None
      if 'kind' in change.attrib:
        if change.attrib['kind'] == svn_node_dir:
          pathtype = vclib.DIR
        elif change.attrib['kind'] == svn_node_file:
          pathtype = vclib.FILE

      # svn_log_changed_path2_t only has the 'text_modified' and
      # 'props_modified' bits in Subversion 1.7 and beyond.  And
      # svn_log_changed_path_t is without.
      text_modified = props_modified = 0
      if 'text-mods' in change.attrib:
        if change.attrib['text-mods'] == svn_tristate_true:
          text_modified = 1
      if 'prop-mods' in change.attrib:
        if change.attrib['prop-mods'] == svn_tristate_true:
          props_modified = 1

      # Wrong, diddily wrong wrong wrong.  Can you say,
      # "Manufacturing data left and right because it hurts to
      # figure out the right stuff?"
      action = action_map.get(change.attrib['action'], vclib.MODIFIED)
      if 'copyfrom-path' in change.attrib and 'copyfrom-rev' in change.attrib:
        is_copy = 1
        base_path = change.attrib['copyfrom-path']
        base_rev = change.attrib['copyfrom-rev']
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

    return [date, author, msg, revprops, changes]

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

  def _do_svn_cmd(self, cmd, args, cfg=None):
    """execute svn commandline utility and returns its proces object"""

    # TODO: make an config option to specifiy subversion command line client
    #       path and use it here.
    svnpath='svn'
    svn_cmd = [svnpath, cmd, '--non-interactive']
    if self.config_dir:
      svn_cmd.append('--config-dir=%s' % self.config_dir)
    proc = subprocess.Popen(svn_cmd + list(args), bufsize=-1,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           close_fds=(sys.platform != "win32"))
    return proc

  def svn_cmd(self, cmd, args, cfg=None):
    proc = self._do_svn_cmd(cmd, args, cfg)
    text = proc.stdout.read()
    proc.stdout.close()
    rc = proc.poll()
    if rc:
      try:
        errout = proc.stderr.read()
      except Exception:
        pass
      raise SvnCommandError(errout, cmd, rc)
    return text

  def svn_cmd_xml(self, cmd, args, cfg=None):
    proc = self._do_svn_cmd(cmd, list(args) + ['--xml'], cfg)
    try:
      et = xml.etree.ElementTree.parse(proc.stdout)
    except:
      try:
        errout = proc.stderr.read()
      except Exception:
        pass
      rc = proc.poll()
      if rc:
        raise SvnCommandError(errout, cmd, rc)
      else:
        raise
    return et

  def get_svn_version(self):
    version = self.svn_cmd('--version', ['--quiet'])
    if version and version[-1:] == b'\n':
      version = version[:-1]
    version = tuple([int(x) for x in version.split(b'.')])
    return version

  def list_directory(self, url, peg_rev, rev):
    # xml output always contains lock information
    url = url + ("@%s" % peg_rev)
    return self.svn_cmd_xml('ls', ['-r%s' % rev, url])

