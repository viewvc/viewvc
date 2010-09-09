# -*-python-*-
#
# Copyright (C) 1999-2008 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

"Version Control lib driver for locally accessible cvs-repositories."

import vclib
import vcauth
import os
import os.path
import sys
import stat
import string
import re
import time

# ViewVC libs
import compat
import popen

class BaseCVSRepository(vclib.Repository):
  def __init__(self, name, rootpath, authorizer, utilities):
    if not os.path.isdir(rootpath):
      raise vclib.ReposNotFound(name) 
   
    self.name = name
    self.rootpath = rootpath
    self.auth = authorizer
    self.utilities = utilities

    # See if this repository is even viewable, authz-wise.
    if not vclib.check_root_access(self):
      raise vclib.ReposNotFound(name)

  def rootname(self):
    return self.name

  def rootpath(self):
    return self.rootpath

  def roottype(self):
    return vclib.CVS

  def authorizer(self):
    return self.auth
  
  def itemtype(self, path_parts, rev):
    basepath = self._getpath(path_parts)
    kind = None
    if os.path.isdir(basepath):
      kind = vclib.DIR
    elif os.path.isfile(basepath + ',v'):
      kind = vclib.FILE
    else:
      atticpath = self._getpath(self._atticpath(path_parts))
      if os.path.isfile(atticpath + ',v'):
        kind = vclib.FILE
    if not kind:
      raise vclib.ItemNotFound(path_parts)
    if not vclib.check_path_access(self, path_parts, kind, rev):
      raise vclib.ItemNotFound(path_parts)
    return kind

  def itemprops(self, path_parts, rev):
    self.itemtype(path_parts, rev)  # does auth-check
    return {}  # CVS doesn't support properties
  
  def listdir(self, path_parts, rev, options):
    if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
      raise vclib.Error("Path '%s' is not a directory."
                        % (string.join(path_parts, "/")))
    
    # Only RCS files (*,v) and subdirs are returned.
    data = [ ]
    full_name = self._getpath(path_parts)
    for file in os.listdir(full_name):
      name = None
      kind, errors = _check_path(os.path.join(full_name, file))
      if kind == vclib.FILE:
        if file[-2:] == ',v':
          name = file[:-2]
      elif kind == vclib.DIR:
        if file != 'Attic' and file != 'CVS': # CVS directory is for fileattr
          name = file
      else:
        name = file
      if not name:
        continue
      if vclib.check_path_access(self, path_parts + [name], kind, rev):
        data.append(CVSDirEntry(name, kind, errors, 0))

    full_name = os.path.join(full_name, 'Attic')
    if os.path.isdir(full_name):
      for file in os.listdir(full_name):
        name = None
        kind, errors = _check_path(os.path.join(full_name, file))
        if kind == vclib.FILE:
          if file[-2:] == ',v':
            name = file[:-2]
        elif kind != vclib.DIR:
          name = file
        if not name:
          continue
        if vclib.check_path_access(self, path_parts + [name], kind, rev):
          data.append(CVSDirEntry(name, kind, errors, 1))

    return data
    
  def _getpath(self, path_parts):
    return apply(os.path.join, (self.rootpath,) + tuple(path_parts))

  def _atticpath(self, path_parts):
    return path_parts[:-1] + ['Attic'] + path_parts[-1:]

  def rcsfile(self, path_parts, root=0, v=1):
    "Return path to RCS file"

    ret_parts = path_parts
    ret_file = self._getpath(ret_parts)
    if not os.path.isfile(ret_file + ',v'):
      ret_parts = self._atticpath(path_parts)
      ret_file = self._getpath(ret_parts)
      if not os.path.isfile(ret_file + ',v'):
        raise vclib.ItemNotFound(path_parts)
    if root:
      ret = ret_file
    else:
      ret = string.join(ret_parts, "/")
    if v:
      ret = ret + ",v"
    return ret

  def isexecutable(self, path_parts, rev):
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts, "/")))
    rcsfile = self.rcsfile(path_parts, 1)
    return os.access(rcsfile, os.X_OK)


class BinCVSRepository(BaseCVSRepository):
  def _get_tip_revision(self, rcs_file, rev=None):
    """Get the (basically) youngest revision (filtered by REV)."""
    args = rcs_file,
    fp = self.rcs_popen('rlog', args, 'rt', 0)
    filename, default_branch, tags, lockinfo, msg, eof = _parse_log_header(fp)
    revs = []
    while not eof:
      revision, eof = _parse_log_entry(fp)
      if revision:
        revs.append(revision)
    revs = _file_log(revs, tags, lockinfo, default_branch, rev)
    if revs:
      return revs[-1]
    return None

  def openfile(self, path_parts, rev):
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts, "/")))
    if not rev or rev == 'HEAD' or rev == 'MAIN':
      rev_flag = '-p'
    else:
      rev_flag = '-p' + rev
    full_name = self.rcsfile(path_parts, root=1, v=0)

    used_rlog = 0
    tip_rev = None  # used only if we have to fallback to using rlog

    fp = self.rcs_popen('co', (rev_flag, full_name), 'rb') 
    try:
      filename, revision = _parse_co_header(fp)
    except COMissingRevision:
      # We got a "revision X.Y.Z absent" error from co.  This could be
      # because we were asked to find a tip of a branch, which co
      # doesn't seem to handle.  So we do rlog-gy stuff to figure out
      # which revision the tip of the branch currently maps to.
      ### TODO: Only do this when 'rev' is a branch symbol name?
      if not used_rlog:
        tip_rev = self._get_tip_revision(full_name + ',v', rev)
        used_rlog = 1
      if not tip_rev:
        raise vclib.Error("Unable to find valid revision")
      fp = self.rcs_popen('co', ('-p' + tip_rev.string, full_name), 'rb') 
      filename, revision = _parse_co_header(fp)
      
    if filename is None:
      # CVSNT's co exits without any output if a dead revision is requested.
      # Bug at http://www.cvsnt.org/cgi-bin/bugzilla/show_bug.cgi?id=190
      # As a workaround, we invoke rlog to find the first non-dead revision
      # that precedes it and check out that revision instead.  Of course, 
      # if we've already invoked rlog above, we just reuse its output.
      if not used_rlog:
        tip_rev = self._get_tip_revision(full_name + ',v', rev)
        used_rlog = 1
      if not (tip_rev and tip_rev.undead):
        raise vclib.Error(
          'Could not find non-dead revision preceding "%s"' % rev)
      fp = self.rcs_popen('co', ('-p' + tip_rev.undead.string,
                                 full_name), 'rb') 
      filename, revision = _parse_co_header(fp)

    if filename is None:
      raise vclib.Error('Missing output from co (filename = "%s")' % full_name)

    if not _paths_eq(filename, full_name):
      raise vclib.Error(
        'The filename from co ("%s") did not match (expected "%s")'
        % (filename, full_name))

    return fp, revision

  def dirlogs(self, path_parts, rev, entries, options):
    """see vclib.Repository.dirlogs docstring

    rev can be a tag name or None. if set only information from revisions
    matching the tag will be retrieved

    Option values recognized by this implementation:

      cvs_subdirs
        boolean. true to fetch logs of the most recently modified file in each
        subdirectory

    Option values returned by this implementation:

      cvs_tags, cvs_branches
        lists of tag and branch names encountered in the directory
    """
    if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
      raise vclib.Error("Path '%s' is not a directory."
                        % (string.join(path_parts, "/")))

    subdirs = options.get('cvs_subdirs', 0)
    entries_to_fetch = []
    for entry in entries:
      if vclib.check_path_access(self, path_parts + [entry.name], None, rev):
        entries_to_fetch.append(entry)
    alltags = _get_logs(self, path_parts, entries_to_fetch, rev, subdirs)
    branches = options['cvs_branches'] = []
    tags = options['cvs_tags'] = []
    for name, rev in alltags.items():
      if Tag(None, rev).is_branch:
        branches.append(name)
      else:
        tags.append(name)

  def itemlog(self, path_parts, rev, sortby, first, limit, options):
    """see vclib.Repository.itemlog docstring

    rev parameter can be a revision number, a branch number, a tag name,
    or None. If None, will return information about all revisions, otherwise,
    will only return information about the specified revision or branch.

    Option values recognized by this implementation:

      cvs_pass_rev
        boolean, default false. set to true to pass rev parameter as -r
        argument to rlog, this is more efficient but causes less
        information to be returned

    Option values returned by this implementation:

      cvs_tags
        dictionary of Tag objects for all tags encountered
    """

    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts, "/")))
    
    # Invoke rlog
    rcsfile = self.rcsfile(path_parts, 1)
    if rev and options.get('cvs_pass_rev', 0):
      args = '-r' + rev, rcsfile
    else:
      args = rcsfile,

    fp = self.rcs_popen('rlog', args, 'rt', 0)
    filename, default_branch, tags, lockinfo, msg, eof = _parse_log_header(fp)

    # Retrieve revision objects
    revs = []
    while not eof:
      revision, eof = _parse_log_entry(fp)
      if revision:
        revs.append(revision)

    filtered_revs = _file_log(revs, tags, lockinfo, default_branch, rev)

    options['cvs_tags'] = tags
    if sortby == vclib.SORTBY_DATE:
      filtered_revs.sort(_logsort_date_cmp)
    elif sortby == vclib.SORTBY_REV:
      filtered_revs.sort(_logsort_rev_cmp)

    if len(filtered_revs) < first:
      return []
    if limit:
      return filtered_revs[first:first+limit]
    return filtered_revs

  def rcs_popen(self, rcs_cmd, rcs_args, mode, capture_err=1):
    if self.utilities.cvsnt:
      cmd = self.utilities.cvsnt
      args = ['rcsfile', rcs_cmd]
      args.extend(list(rcs_args))
    else:
      cmd = os.path.join(self.utilities.rcs_dir, rcs_cmd)
      args = rcs_args
    return popen.popen(cmd, args, mode, capture_err)

  def annotate(self, path_parts, rev=None):
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts, "/")))
                        
    from vclib.ccvs import blame
    source = blame.BlameSource(self.rcsfile(path_parts, 1), rev)
    return source, source.revision

  def revinfo(self, rev):
    raise vclib.UnsupportedFeature
  
  def rawdiff(self, path_parts1, rev1, path_parts2, rev2, type, options={}):
    """see vclib.Repository.rawdiff docstring

    Option values recognized by this implementation:

      ignore_keyword_subst - boolean, ignore keyword substitution
    """
    if self.itemtype(path_parts1, rev1) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts1, "/")))
    if self.itemtype(path_parts2, rev2) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts2, "/")))
    
    args = vclib._diff_args(type, options)
    if options.get('ignore_keyword_subst', 0):
      args.append('-kk')

    rcsfile = self.rcsfile(path_parts1, 1)
    if path_parts1 != path_parts2:
      raise NotImplementedError, "cannot diff across paths in cvs"
    args.extend(['-r' + rev1, '-r' + rev2, rcsfile])
    
    fp = self.rcs_popen('rcsdiff', args, 'rt')

    # Eat up the non-GNU-diff-y headers.
    while 1:
      line = fp.readline()
      if not line or line[0:5] == 'diff ':
        break
    return fp
  

class CVSDirEntry(vclib.DirEntry):
  def __init__(self, name, kind, errors, in_attic, absent=0):
    vclib.DirEntry.__init__(self, name, kind, errors)
    self.in_attic = in_attic
    self.absent = absent # meaning, no revisions found on requested tag

class Revision(vclib.Revision):
  def __init__(self, revstr, date=None, author=None, dead=None,
               changed=None, log=None):
    vclib.Revision.__init__(self, _revision_tuple(revstr), revstr,
                            date, author, changed, log, None, None)
    self.dead = dead

class Tag:
  def __init__(self, name, revstr):
    self.name = name
    self.number = _tag_tuple(revstr)
    self.is_branch = len(self.number) % 2 == 1 or not self.number


# ======================================================================
# Functions for dealing with Revision and Tag objects

def _logsort_date_cmp(rev1, rev2):
  # sort on date; secondary on revision number
  return -cmp(rev1.date, rev2.date) or -cmp(rev1.number, rev2.number)

def _logsort_rev_cmp(rev1, rev2):
  # sort highest revision first
  return -cmp(rev1.number, rev2.number)

def _match_revs_tags(revlist, taglist):
  """Match up a list of Revision objects with a list of Tag objects

  Sets the following properties on each Revision in revlist:
    "tags"
      list of non-branch tags which refer to this revision
      example: if revision is 1.2.3.4, tags is a list of all 1.2.3.4 tags

    "branches"
      list of branch tags which refer to this revision's branch
      example: if revision is 1.2.3.4, branches is a list of all 1.2.3 tags

    "branch_points"
      list of branch tags which branch off of this revision
      example: if revision is 1.2, it's a list of tags like 1.2.3 and 1.2.4

    "prev"
      reference to the previous revision, possibly None
      example: if revision is 1.2.3.4, prev is 1.2.3.3

    "next"
      reference to next revision, possibly None
      example: if revision is 1.2.3.4, next is 1.2.3.5

    "parent"
      reference to revision this one branches off of, possibly None
      example: if revision is 1.2.3.4, parent is 1.2

    "undead"
      If the revision is dead, then this is a reference to the first 
      previous revision which isn't dead, otherwise it's a reference
      to itself. If all the previous revisions are dead it's None. 

    "branch_number"
      tuple representing branch number or empty tuple if on trunk
      example: if revision is 1.2.3.4, branch_number is (1, 2, 3)

  Each tag in taglist gets these properties set:
    "co_rev"
      reference to revision that would be retrieved if tag were checked out

    "branch_rev"
      reference to revision branched off of, only set for branch tags
      example: if tag is 1.2.3, branch_rev points to 1.2 revision

    "aliases"
      list of tags that have the same number
  """

  # map of branch numbers to lists of corresponding branch Tags
  branch_dict = {}

  # map of revision numbers to lists of non-branch Tags
  tag_dict = {}

  # map of revision numbers to lists of branch Tags
  branch_point_dict = {}

  # toss tags into "branch_dict", "tag_dict", and "branch_point_dict"
  # set "aliases" property and default "co_rev" and "branch_rev" values
  for tag in taglist:
    tag.co_rev = None
    if tag.is_branch:
      tag.branch_rev = None
      _dict_list_add(branch_point_dict, tag.number[:-1], tag)
      tag.aliases = _dict_list_add(branch_dict, tag.number, tag)
    else:
      tag.aliases = _dict_list_add(tag_dict, tag.number, tag)

  # sort the revisions so the loop below can work properly
  revlist.sort()

  # array of the most recently encountered revision objects indexed by depth
  history = []

  # loop through revisions, setting properties and storing state in "history"
  for rev in revlist:
    depth = len(rev.number) / 2 - 1

    # set "prev" and "next" properties
    rev.prev = rev.next = None
    if depth < len(history):
      prev = history[depth]
      if prev and (depth == 0 or rev.number[:-1] == prev.number[:-1]):
        rev.prev = prev
        prev.next = rev

    # set "parent"
    rev.parent = None
    if depth and depth <= len(history):
      parent = history[depth-1]
      if parent and parent.number == rev.number[:-2]:
        rev.parent = history[depth-1]

    # set "undead"
    if rev.dead:
      prev = rev.prev or rev.parent
      rev.undead = prev and prev.undead
    else:
      rev.undead = rev

    # set "tags" and "branch_points"
    rev.tags = tag_dict.get(rev.number, [])
    rev.branch_points = branch_point_dict.get(rev.number, [])

    # set "branches" and "branch_number"
    if rev.prev:
      rev.branches = rev.prev.branches
      rev.branch_number = rev.prev.branch_number
    else:
      rev.branch_number = depth and rev.number[:-1] or ()
      try:
        rev.branches = branch_dict[rev.branch_number]
      except KeyError:
        rev.branches = []

    # set "co_rev" and "branch_rev"
    for tag in rev.tags:
      tag.co_rev = rev

    for tag in rev.branch_points:
      tag.co_rev = rev
      tag.branch_rev = rev

    # This loop only needs to be run for revisions at the heads of branches,
    # but for the simplicity's sake, it actually runs for every revision on
    # a branch. The later revisions overwrite values set by the earlier ones.
    for branch in rev.branches:
      branch.co_rev = rev

    # end of outer loop, store most recent revision in "history" array
    while len(history) <= depth:
      history.append(None)
    history[depth] = rev

def _add_tag(tag_name, revision):
  """Create a new tag object and associate it with a revision"""
  if revision:
    tag = Tag(tag_name, revision.string)
    tag.aliases = revision.tags
    revision.tags.append(tag)
  else:
    tag = Tag(tag_name, None)
    tag.aliases = []
  tag.co_rev = revision
  tag.is_branch = 0
  return tag

def _remove_tag(tag):
  """Remove a tag's associations"""
  tag.aliases.remove(tag)
  if tag.is_branch and tag.branch_rev:
    tag.branch_rev.branch_points.remove(tag)

def _revision_tuple(revision_string):
  """convert a revision number into a tuple of integers"""
  t = tuple(map(int, string.split(revision_string, '.')))
  if len(t) % 2 == 0:
    return t
  raise ValueError

def _tag_tuple(revision_string):
  """convert a revision number or branch number into a tuple of integers"""
  if revision_string:
    t = map(int, string.split(revision_string, '.'))
    l = len(t)
    if l == 1:
      return ()
    if l > 2 and t[-2] == 0 and l % 2 == 0:
      del t[-2]
    return tuple(t)
  return ()

def _dict_list_add(dict, idx, elem):
  try:
    list = dict[idx]
  except KeyError:
    list = dict[idx] = [elem]
  else:
    list.append(elem)
  return list


# ======================================================================
# Functions for parsing output from RCS utilities


class COMalformedOutput(vclib.Error):
  pass
class COMissingRevision(vclib.Error):
  pass

### suck up other warnings in _re_co_warning?
_re_co_filename = re.compile(r'^(.*),v\s+-->\s+(?:(?:standard output)|(?:stdout))\s*\n?$')
_re_co_warning = re.compile(r'^.*co: .*,v: warning: Unknown phrases like .*\n$')
_re_co_missing_rev = re.compile(r'^.*co: .*,v: revision.*absent\n$')
_re_co_side_branches = re.compile(r'^.*co: .*,v: no side branches present for [\d\.]+\n$')
_re_co_revision = re.compile(r'^revision\s+([\d\.]+)\s*\n$')

def _parse_co_header(fp):
  """Parse RCS co header.

  fp is a file (pipe) opened for reading the co standard error stream.

  Returns: (filename, revision) or (None, None) if output is empty
  """

  # header from co:
  #
  #/home/cvsroot/mod_dav/dav_shared_stub.c,v  -->  standard output
  #revision 1.1
  #
  # Sometimes, the following line might occur at line 2:
  #co: INSTALL,v: warning: Unknown phrases like `permissions ...;' are present.

  # parse the output header
  filename = None

  # look for a filename in the first line (if there is a first line).
  line = fp.readline()
  if not line:
    return None, None
  match = _re_co_filename.match(line)
  if not match:
    raise COMalformedOutput, "Unable to find filename in co output stream"
  filename = match.group(1)

  # look through subsequent lines for a revision.  we might encounter
  # some ignorable or problematic lines along the way.
  while 1:
    line = fp.readline()
    if not line:
      break
    # look for a revision.
    match = _re_co_revision.match(line)
    if match:
      return filename, match.group(1)
    elif _re_co_missing_rev.match(line) or _re_co_side_branches.match(line):
      raise COMissingRevision, "Got missing revision error from co output stream"
    elif _re_co_warning.match(line):
      pass
    else:
      break
    
  raise COMalformedOutput, "Unable to find revision in co output stream"

# if your rlog doesn't use 77 '=' characters, then this must change
LOG_END_MARKER = '=' * 77 + '\n'
ENTRY_END_MARKER = '-' * 28 + '\n'

_EOF_FILE = 'end of file entries'       # no more entries for this RCS file
_EOF_LOG = 'end of log'                 # hit the true EOF on the pipe
_EOF_ERROR = 'error message found'      # rlog issued an error

# rlog error messages look like
#
#   rlog: filename/goes/here,v: error message
#   rlog: filename/goes/here,v:123: error message
#
# so we should be able to match them with a regex like
#
#   ^rlog\: (.*)(?:\:\d+)?\: (.*)$
#
# But for some reason the windows version of rlog omits the "rlog: " prefix
# for the first error message when the standard error stream has been 
# redirected to a file or pipe. (the prefix is present in subsequent errors
# and when rlog is run from the console). So the expression below is more
# complicated
_re_log_error = re.compile(r'^(?:rlog\: )*(.*,v)(?:\:\d+)?\: (.*)$')

# CVSNT error messages look like:
# cvs rcsfile: `C:/path/to/file,v' does not appear to be a valid rcs file
# cvs [rcsfile aborted]: C:/path/to/file,v: No such file or directory
# cvs [rcsfile aborted]: cannot open C:/path/to/file,v: Permission denied
_re_cvsnt_error = re.compile(r'^(?:cvs rcsfile\: |cvs \[rcsfile aborted\]: )'
                             r'(?:\`(.*,v)\' |cannot open (.*,v)\: |(.*,v)\: |)'
                             r'(.*)$')

def _parse_log_header(fp):
  """Parse and RCS/CVS log header.

  fp is a file (pipe) opened for reading the log information.

  On entry, fp should point to the start of a log entry.
  On exit, fp will have consumed the separator line between the header and
  the first revision log.

  If there is no revision information (e.g. the "-h" switch was passed to
  rlog), then fp will consumed the file separator line on exit.

  Returns: filename, default branch, tag dictionary, lock dictionary,
  rlog error message, and eof flag
  """
  
  filename = head = branch = msg = ""
  taginfo = { }   # tag name => number
  lockinfo = { }  # revision => locker
  state = 0       # 0 = base, 1 = parsing symbols, 2 = parsing locks
  eof = None

  while 1:
    line = fp.readline()
    if not line:
      # the true end-of-file
      eof = _EOF_LOG
      break

    if state == 1:
      if line[0] == '\t':
        [ tag, rev ] = map(string.strip, string.split(line, ':'))
        taginfo[tag] = rev
      else:
        # oops. this line isn't tag info. stop parsing tags.
        state = 0

    if state == 2:
      if line[0] == '\t':
        [ locker, rev ] = map(string.strip, string.split(line, ':'))
        lockinfo[rev] = locker
      else:
        # oops. this line isn't lock info. stop parsing tags.
        state = 0
      
    if state == 0:
      if line[:9] == 'RCS file:':
        filename = line[10:-1]
      elif line[:5] == 'head:':
        head = line[6:-1]
      elif line[:7] == 'branch:':
        branch = line[8:-1]
      elif line[:6] == 'locks:':
        # start parsing the lock information
        state = 2
      elif line[:14] == 'symbolic names':
        # start parsing the tag information
        state = 1
      elif line == ENTRY_END_MARKER:
        # end of the headers
        break
      elif line == LOG_END_MARKER:
        # end of this file's log information
        eof = _EOF_FILE
        break
      else:
        error = _re_cvsnt_error.match(line)
        if error:
          p1, p2, p3, msg = error.groups()
          filename = p1 or p2 or p3
          if not filename:
            raise vclib.Error("Could not get filename from CVSNT error:\n%s"
                               % line)
          eof = _EOF_ERROR
          break

        error = _re_log_error.match(line)
        if error:
          filename, msg = error.groups()
          if msg[:30] == 'warning: Unknown phrases like ':
            # don't worry about this warning. it can happen with some RCS
            # files that have unknown fields in them (e.g. "permissions 644;"
            continue
          eof = _EOF_ERROR
          break

  return filename, branch, taginfo, lockinfo, msg, eof

_re_log_info = re.compile(r'^date:\s+([^;]+);'
                          r'\s+author:\s+([^;]+);'
                          r'\s+state:\s+([^;]+);'
                          r'(\s+lines:\s+([0-9\s+-]+);?)?'
                          r'(\s+commitid:\s+([a-zA-Z0-9]+))?\n$')
### _re_rev should be updated to extract the "locked" flag
_re_rev = re.compile(r'^revision\s+([0-9.]+).*')
def _parse_log_entry(fp):
  """Parse a single log entry.

  On entry, fp should point to the first line of the entry (the "revision"
  line).
  On exit, fp will have consumed the log separator line (dashes) or the
  end-of-file marker (equals).

  Returns: Revision object and eof flag (see _EOF_*)
  """
  rev = None
  line = fp.readline()
  if not line:
    return None, _EOF_LOG
  if line == LOG_END_MARKER:
    # Needed because some versions of RCS precede LOG_END_MARKER
    # with ENTRY_END_MARKER
    return None, _EOF_FILE
  if line[:8] == 'revision':
    match = _re_rev.match(line)
    if not match:
      return None, _EOF_LOG
    rev = match.group(1)

    line = fp.readline()
    if not line:
      return None, _EOF_LOG
    match = _re_log_info.match(line)

  eof = None
  log = ''
  while 1:
    line = fp.readline()
    if not line:
      # true end-of-file
      eof = _EOF_LOG
      break
    if line[:9] == 'branches:':
      continue
    if line == ENTRY_END_MARKER:
      break
    if line == LOG_END_MARKER:
      # end of this file's log information
      eof = _EOF_FILE
      break

    log = log + line

  if not rev or not match:
    # there was a parsing error
    return None, eof

  # parse out a time tuple for the local time
  tm = compat.cvs_strptime(match.group(1))

  # rlog seems to assume that two-digit years are 1900-based (so, "04"
  # comes out as "1904", not "2004").
  EPOCH = 1970
  if tm[0] < EPOCH:
    tm = list(tm)
    if (tm[0] - 1900) < 70:
      tm[0] = tm[0] + 100
    if tm[0] < EPOCH:
      raise ValueError, 'invalid year'
  date = compat.timegm(tm)

  return Revision(rev, date,
                  # author, state, lines changed
                  match.group(2), match.group(3) == "dead", match.group(5),
                  log), eof

def _skip_file(fp):
  "Skip the rest of a file's log information."
  while 1:
    line = fp.readline()
    if not line:
      break
    if line == LOG_END_MARKER:
      break

def _paths_eq(path1, path2):
  "See if two path strings are the same"
  # This function is neccessary because CVSNT (since version 2.0.29)
  # converts paths passed as arguments to use upper case drive
  # letter and forward slashes
  return os.path.normcase(path1) == os.path.normcase(path2)


# ======================================================================
# Functions for interpreting and manipulating log information

def _file_log(revs, taginfo, lockinfo, cur_branch, filter):
  """Augment list of Revisions and a dictionary of Tags"""

  # Add artificial ViewVC tag MAIN. If the file has a default branch, then
  # MAIN acts like a branch tag pointing to that branch. Otherwise MAIN acts
  # like a branch tag that points to the trunk. (Note: A default branch is
  # just a branch number specified in an RCS file that tells CVS and RCS
  # what branch to use for checkout and update operations by default, when
  # there's no revision argument or sticky branch to override it. Default
  # branches get set by "cvs import" to point to newly created vendor
  # branches. Sometimes they are also set manually with "cvs admin -b")
  taginfo['MAIN'] = cur_branch

  # Create tag objects
  for name, num in taginfo.items():
    taginfo[name] = Tag(name, num)
  tags = taginfo.values()

  # Set view_tag to a Tag object in order to filter results. We can filter by
  # revision number or branch number
  if filter:
    try:
      view_tag = Tag(None, filter)
    except ValueError:
      view_tag = None
    else:
      tags.append(view_tag)  

  # Match up tags and revisions
  _match_revs_tags(revs, tags)

  # Match up lockinfo and revision
  for rev in revs:
    rev.lockinfo = lockinfo.get(rev.string)
      
  # Add artificial ViewVC tag HEAD, which acts like a non-branch tag pointing
  # at the latest revision on the MAIN branch. The HEAD revision doesn't have
  # anything to do with the "head" revision number specified in the RCS file
  # and in rlog output. HEAD refers to the revision that the CVS and RCS co
  # commands will check out by default, whereas the "head" field just refers
  # to the highest revision on the trunk.  
  taginfo['HEAD'] = _add_tag('HEAD', taginfo['MAIN'].co_rev)

  # Determine what revisions to return
  if filter:
    # If view_tag isn't set, it means filter is not a valid revision or
    # branch number. Check taginfo to see if filter is set to a valid tag
    # name. If so, filter by that tag, otherwise raise an error.
    if not view_tag:
      try:
        view_tag = taginfo[filter]
      except KeyError:
        raise vclib.Error('Invalid tag or revision number "%s"' % filter)
    filtered_revs = [ ]

    # only include revisions on the tag branch or it's parent branches
    if view_tag.is_branch:
      branch = view_tag.number
    elif len(view_tag.number) > 2:
      branch = view_tag.number[:-1]
    else:
      branch = ()

    # for a normal tag, include all tag revision and all preceding revisions.
    # for a branch tag, include revisions on branch, branch point revision,
    # and all preceding revisions
    for rev in revs:
      if (rev.number == view_tag.number
          or rev.branch_number == view_tag.number
          or (rev.number < view_tag.number
              and rev.branch_number == branch[:len(rev.branch_number)])):
        filtered_revs.append(rev)

    # get rid of the view_tag if it was only created for filtering
    if view_tag.name is None:
      _remove_tag(view_tag)
  else:
    filtered_revs = revs
  
  return filtered_revs

def _get_logs(repos, dir_path_parts, entries, view_tag, get_dirs):
  alltags = {           # all the tags seen in the files of this dir
    'MAIN' : '',
    'HEAD' : '1.1'
    }

  entries_idx = 0
  entries_len = len(entries)
  max_args = 100

  while 1:
    chunk = []

    while len(chunk) < max_args and entries_idx < entries_len:
      entry = entries[entries_idx]
      path = _log_path(entry, repos._getpath(dir_path_parts), get_dirs)
      if path:
        entry.path = path
        entry.idx = entries_idx
        chunk.append(entry)

      # set properties even if we don't retrieve logs
      entry.rev = entry.date = entry.author = None
      entry.dead = entry.log = entry.lockinfo = None

      entries_idx = entries_idx + 1

    if not chunk:
      return alltags

    args = []
    if not view_tag:
      # NOTE: can't pass tag on command line since a tag may contain "-"
      #       we'll search the output for the appropriate revision
      # fetch the latest revision on the default branch
      args.append('-r')
    args.extend(map(lambda x: x.path, chunk))
    rlog = repos.rcs_popen('rlog', args, 'rt')

    # consume each file found in the resulting log
    chunk_idx = 0
    while chunk_idx < len(chunk):
      file = chunk[chunk_idx]
      filename, default_branch, taginfo, lockinfo, msg, eof \
        = _parse_log_header(rlog)

      if eof == _EOF_LOG:
        # the rlog output ended early. this can happen on errors that rlog 
        # thinks are so serious that it stops parsing the current file and
        # refuses to parse any of the files that come after it. one of the
        # errors that triggers this obnoxious behavior looks like:
        #
        # rlog: c:\cvsroot\dir\file,v:8: unknown expand mode u
        # rlog aborted

        # if current file has errors, restart on the next one
        if file.errors:
          chunk_idx = chunk_idx + 1
          if chunk_idx < len(chunk):
            entries_idx = chunk[chunk_idx].idx
          break

        # otherwise just error out
        raise vclib.Error('Rlog output ended early. Expected RCS file "%s"'
                          % file.path)

      # if rlog filename doesn't match current file and we already have an
      # error message about this file, move on to the next file
      while not (file and _paths_eq(file.path, filename)):
        if file and file.errors:
          chunk_idx = chunk_idx + 1
          file = chunk_idx < len(chunk) and chunk[chunk_idx] or None
          continue

        raise vclib.Error('Error parsing rlog output. Expected RCS file %s'
                          ', found %s' % (file and file.path, filename))

      # if we get an rlog error message, restart loop without advancing
      # chunk_idx cause there might be more output about the same file
      if eof == _EOF_ERROR:
        file.errors.append("rlog error: %s" % msg)
        continue

      if view_tag == 'MAIN' or view_tag == 'HEAD':
        tag = Tag(None, default_branch)
      elif taginfo.has_key(view_tag):
        tag = Tag(None, taginfo[view_tag])
      elif view_tag:
        # the tag wasn't found, so skip this file
        _skip_file(rlog)
        eof = 1
      else:
        tag = None

      # we don't care about the specific values -- just the keys and whether
      # the values point to branches or revisions. this the fastest way to 
      # merge the set of keys and keep values that allow us to make the 
      # distinction between branch tags and normal tags
      alltags.update(taginfo)

      # read all of the log entries until we find the revision we want
      wanted_entry = None
      while not eof:

        # fetch one of the log entries
        entry, eof = _parse_log_entry(rlog)

        if not entry:
          # parsing error
          break

        # A perfect match is a revision on the branch being viewed or
        # a revision having the tag being viewed or any revision
        # when nothing is being viewed. When there's a perfect match
        # we set the wanted_entry value and break out of the loop.
        # An imperfect match is a revision at the branch point of a
        # branch being viewed. When there's an imperfect match we
        # also set the wanted_entry value but keep looping in case
        # something better comes along.
        perfect = not tag or entry.number == tag.number or       \
                  (len(entry.number) == 2 and not tag.number) or \
                  entry.number[:-1] == tag.number
        if perfect or entry.number == tag.number[:-1]:
          wanted_entry = entry
          if perfect:
            break

      if wanted_entry:
        file.rev = wanted_entry.string
        file.date = wanted_entry.date
        file.author = wanted_entry.author
        file.dead = file.kind == vclib.FILE and wanted_entry.dead
        file.absent = 0
        file.log = wanted_entry.log
        file.lockinfo = lockinfo.get(file.rev)
        # suppress rlog errors if we find a usable revision in the end
        del file.errors[:]
      elif file.kind == vclib.FILE:
        file.dead = 0
        #file.errors.append("No revisions exist on %s" % (view_tag or "MAIN"))
        file.absent = 1
        
      # done with this file now, skip the rest of this file's revisions
      if not eof:
        _skip_file(rlog)

      # end of while loop, advance index
      chunk_idx = chunk_idx + 1

    rlog.close()

def _log_path(entry, dirpath, getdirs):
  path = name = None
  if not entry.errors:
    if entry.kind == vclib.FILE:
      path = entry.in_attic and 'Attic' or ''
      name = entry.name
    elif entry.kind == vclib.DIR and getdirs:
      entry.newest_file = _newest_file(os.path.join(dirpath, entry.name))
      if entry.newest_file:
        path = entry.name
        name = entry.newest_file

  if name:
    return os.path.join(dirpath, path, name + ',v')
  return None


# ======================================================================
# Functions for dealing with the filesystem

if sys.platform == "win32":
  def _check_path(path):
    kind = None
    errors = []

    if os.path.isfile(path):
      kind = vclib.FILE
    elif os.path.isdir(path):
      kind = vclib.DIR
    else:
      errors.append("error: path is not a file or directory")

    if not os.access(path, os.R_OK):
      errors.append("error: path is not accessible")

    return kind, errors

else:
  _uid = os.getuid()
  _gid = os.getgid()

  def _check_path(pathname):
    try:
      info = os.stat(pathname)
    except os.error, e:
      return None, ["stat error: %s" % e]

    kind = None
    errors = []

    mode = info[stat.ST_MODE]
    isdir = stat.S_ISDIR(mode)
    isreg = stat.S_ISREG(mode)
    if isreg or isdir:
      #
      # Quick version of access() where we use existing stat() data.
      #
      # This might not be perfect -- the OS may return slightly different
      # results for some bizarre reason. However, we make a good show of
      # "can I read this file/dir?" by checking the various perm bits.
      #
      # NOTE: if the UID matches, then we must match the user bits -- we
      # cannot defer to group or other bits. Similarly, if the GID matches,
      # then we must have read access in the group bits.
      #
      # If the UID or GID don't match, we need to check the
      # results of an os.access() call, in case the web server process
      # is in the group that owns the directory.
      #
      if isdir:
        mask = stat.S_IROTH | stat.S_IXOTH
      else:
        mask = stat.S_IROTH

      if info[stat.ST_UID] == _uid:
        if ((mode >> 6) & mask) != mask:
          errors.append("error: path is not accessible to user %i" % _uid)
      elif info[stat.ST_GID] == _gid:
        if ((mode >> 3) & mask) != mask:
          errors.append("error: path is not accessible to group %i" % _gid)
      # If the process running the web server is a member of
      # the group stat.ST_GID access may be granted.
      # so the fall back to os.access is needed to figure this out.
      elif (mode & mask) != mask:
        if not os.access(pathname, isdir and (os.R_OK | os.X_OK) or os.R_OK):
          errors.append("error: path is not accessible")

      if isdir:
        kind = vclib.DIR
      else:
        kind = vclib.FILE

    else:
      errors.append("error: path is not a file or directory")

    return kind, errors

def _newest_file(dirpath):
  """Find the last modified RCS file in a directory"""
  newest_file = None
  newest_time = 0

  ### FIXME:  This sucker is leaking unauthorized paths! ###
  
  for subfile in os.listdir(dirpath):
    ### filter CVS locks? stale NFS handles?
    if subfile[-2:] != ',v':
      continue
    path = os.path.join(dirpath, subfile)
    info = os.stat(path)
    if not stat.S_ISREG(info[stat.ST_MODE]):
      continue
    if info[stat.ST_MTIME] > newest_time:
      kind, verboten = _check_path(path)
      if kind == vclib.FILE and not verboten:
        newest_file = subfile[:-2]
        newest_time = info[stat.ST_MTIME]

  return newest_file
