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

"""commonly used functions and classes for Version Control lib driver
for accessible Subversion repositories, without swig Python binding of
Subversion.
"""

import sys
import vclib

# Python 3: workaround for cmp()
if sys.version_info[0] >= 3:
  def cmp(a, b):
    return (a > b) - (a < b)


def _path_parts(path):
  return [pp for pp in path.split('/') if pp]


def _getpath(path_parts):
  return '/'.join(path_parts)

def _cleanup_path(path):
  """Return a cleaned-up Subversion filesystem path"""
  return '/'.join([pp for pp in path.split('/') if pp])


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


class Revision(vclib.Revision):
  "Hold state for each revision's log entry."
  def __init__(self, rev, date, author, msg, size, lockinfo,
               filename, copy_path, copy_rev):
    vclib.Revision.__init__(self, rev, str(rev), date, author, None,
                            msg, size, lockinfo)
    self.filename = filename
    self.copy_path = copy_path
    self.copy_rev = copy_rev


class SVNChangedPath(vclib.ChangedPath):
  """Wrapper around vclib.ChangedPath which handles path splitting."""

  def __init__(self, path, rev, pathtype, base_path, base_rev,
               action, copied, text_changed, props_changed):
    path_parts = _path_parts(path or '')
    base_path_parts = _path_parts(base_path or '')
    vclib.ChangedPath.__init__(self, path_parts, rev, pathtype,
                               base_path_parts, base_rev, action,
                               copied, text_changed, props_changed)


class SubversionRepository(vclib.Repository):
  def __init__(self, name, rootpath, authorizer, utilities, config_dir):
    # Initialize some stuff.
    self.rootpath = rootpath
    self.name = name
    self.auth = authorizer
    self.diff_cmd = utilities.diff or 'diff'
    self.config_dir = config_dir or None

    # See if this repository is even viewable, authz-wise.
    if not vclib.check_root_access(self):
      raise vclib.ReposNotFound(name)

  def rootname(self):
    return self.name

  def rootpath(self):
    return self.rootpath

  def roottype(self):
    return vclib.SVN

  def authorizer(self):
    return self.auth

  ### Subversion specific methods, but called from viewvc.py ###
  def get_youngest_revision(self):
    """returns youngest revision of the repository as int"""
    return self.youngest

  def get_location(self, path, rev, old_rev):
    """returns location path of item specified by 'path' and 'rev' in 'old_rev'"""
    raise UnsupportedFeature()

  def created_rev(self, path, rev):
    """returns first appeared revison of the item specified by 'path' and 'rev' as int"""
    raise UnsupportedFeature()

  def last_rev(self, path, peg_revision, limit_revision=None):
    """Given PATH, known to exist in PEG_REVISION, find the youngest
    revision older than, or equal to, LIMIT_REVISION in which path
    exists.  Return that revision, and the path at which PATH exists in
    that revision."""

    # this is fallback implementation that first used svn_ra module
    # that uses self.get_location() and binary search

    # Here's the plan, man.  In the trivial case (where PEG_REVISION is
    # the same as LIMIT_REVISION), this is a no-brainer.  If
    # LIMIT_REVISION is older than PEG_REVISION, we can use Subversion's
    # history tracing code to find the right location.  If, however,
    # LIMIT_REVISION is younger than PEG_REVISION, we suffer from
    # Subversion's lack of forward history searching.  Our workaround,
    # ugly as it may be, involves a binary search through the revisions
    # between PEG_REVISION and LIMIT_REVISION to find our last live
    # revision.
    peg_revision = self._getrev(peg_revision)
    limit_revision = self._getrev(limit_revision)
    if peg_revision == limit_revision:
      return peg_revision, path
    elif peg_revision > limit_revision:
      path = self.get_location(path, peg_revision, limit_revision)
      return limit_revision, path
    else:
      direction = 1
      while peg_revision != limit_revision:
        mid = (peg_revision + 1 + limit_revision) // 2
        try:
          path = self.get_location(path, peg_revision, mid)
        except vclib.ItemNotFound:
          limit_revision = mid - 1
        else:
          peg_revision = mid
      return peg_revision, path

  def get_symlink_target(self, path_parts, rev):
    """Return the target of the symbolic link versioned at PATH_PARTS
    in REV, or None if that object is not a symlink."""
    raise UnsupportedFeature()

  ## commonly used helper method

  def _getrev(self, rev):
    if rev is None or rev == 'HEAD':
      return self.youngest
    try:
      if isinstance(rev, str):
        while rev[0] == 'r':
          rev = rev[1:]
      rev = int(rev)
    except:
      raise vclib.InvalidRevision(rev)
    if (rev < 0) or (rev > self.youngest):
      raise vclib.InvalidRevision(rev)
    return rev

