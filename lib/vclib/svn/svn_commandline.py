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
  from urllib.parse import quote as _quote
else:
  from urllib import quote as _quote

import vclib
from . import _canonicalize_path
from .common import SubversionRepository, Revision, SVNChangedPath, \
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


class CmdLineSubversionRepository(SubversionRepository):
  def __init__(self, name, rootpath, authorizer, utilities, config_dir):
    SubversionRepository.__init__(self, name, rootpath, authorizer, utilities,
                                  config_dir)
    self.svn_version = self.get_svn_version()

  def open(self):

    # get head revison of root
    et = self.svn_cmd_xml('propget', ['--revprop', '-r', 'HEAD',
                          SVN_PROP_REVISION_DATE, self.rootpath])
    self.youngest = int(et.find('revprops').attrib['rev'])
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
      url = self._geturl(_getpath(path_parts))
      rev = self._getrev(rev)
      try:
        if self.svn_version >= (1, 9, 0) and False:
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
    raise vclib.UnsupportedFeature()

  def listdir(self, path_parts, rev, options):
    raise vclib.UnsupportedFeature()

  def dirlogs(self, path_parts, rev, entries, options):
    raise vclib.UnsupportedFeature()

  def itemlog(self, path_parts, rev, sortby, first, limit, options):
    raise vclib.UnsupportedFeature()

  def itemprops(self, path_parts, rev):
    raise vclib.UnsupportedFeature()

  def rawdiff(self, path_parts1, rev1, path_parts2, rev2, type, options={}):
    raise vclib.UnsupportedFeature()

  def annotate(self, path_parts, rev, include_text=False):
    raise vclib.UnsupportedFeature()

  def revinfo(self, rev):
    raise vclib.UnsupportedFeature()

  def isexecutable(self, path_parts, rev):
    raise vclib.UnsupportedFeature()

  def filesize(self, path_parts, rev):
    raise vclib.UnsupportedFeature()

  def get_youngest_revision(self):
    return self.youngest

  def get_location(self, path, rev, old_rev):
    raise UnsupportedFeature()

  def created_rev(self, path, rev):
    raise UnsupportedFeature()

  def get_symlink_target(self, path_parts, rev):
    raise UnsupportedFeature()

  ### helper functions ###

  def _geturl(self, path=None):
    if not path:
      return self.rootpath
    path = self.rootpath + '/' + _quote(path)
    return _canonicalize_path(path)

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

  def svn_cmd_fp(self, cmd, args, cfg=None):
    proc = self._do_svn_cmd(cmd, args, cfg)
    return proc.stdout

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

