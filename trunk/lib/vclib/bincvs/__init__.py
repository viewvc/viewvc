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

"Version Control lib driver for locally accessible cvs-repositories."


# ======================================================================

import vclib
import os
import os.path
import sys
import stat
import string
import re
import time

# ViewCVS libs
import compat
import popen

# if your rlog doesn't use 77 '=' characters, then this must change
LOG_END_MARKER = '=' * 77 + '\n'
ENTRY_END_MARKER = '-' * 28 + '\n'

_EOF_FILE = 'end of file entries'       # no more entries for this RCS file
_EOF_LOG = 'end of log'                 # hit the true EOF on the pipe
_EOF_ERROR = 'error message found'      # rlog issued an error

_FILE_HAD_ERROR = 'could not read file'


class LogHeader:
  "Hold state from the header portion of an 'rlog' output."
  def __init__(self, filename, head=None, branch=None, taginfo=None):
    self.filename = filename
    self.head = head
    self.branch = branch
    self.taginfo = taginfo


class LogEntry:
  "Hold state for each revision entry in an 'rlog' output."
  def __init__(self, rev, date, author, state, changed, log):
    self.rev = rev
    self.date = date
    self.author = author
    self.state = state
    self.changed = changed
    self.log = log


class LogError:
  "Represent an entry that had an (unknown) error."
  pass


# match a revision number
_re_revision = re.compile(r'^\d+\.\d+(?:\.\d+\.\d+)*$')


# match a branch number with optional 0
_re_branch = re.compile(r'^(?P<base>(?:\d+\.\d+)(?:\.\d+\.\d+)*)'
                        r'(?P<zero>\.0)?\.(?P<branch>\d+)$')


class TagInfo:
  def __init__(self, number):
    if number == '': # number has special value used to refer to the trunk
      self._rev = number
      self._branch = ''
      self._zero_branch = 0
      return

    match = _re_branch.match(number)
    if match: # number refers to a branch
      self._rev = match.group('base')
      self._branch = self._rev + '.' + match.group('branch')
      self._zero_branch = match.group('zero') is not None
      return

    match = _re_revision.match(number)
    if match: # number refers to a revision
      self._rev = number
      self._branch = ''
      self._zero_branch = 0
      return

    raise vclib.InvalidRevision(number)

  def is_trunk(self):
    "true if this is a trunk tag (i.e. MAIN when the file has no default branch)"
    return not self._rev

  def is_branch(self):
    "true if this is a branch tag"
    return not self._rev or self._branch

  def branches_at(self):
    "return revision number that this branch branches off of"
    return self._branch and self._rev or None

  def matches_rev(self, number):
    "true if specified revision number has this tag"
    return number == self._rev and (not self._branch or self._zero_branch)

  def holds_rev(self, number):
    "true if specified revision number is on this branch"
    if self._rev:
      if self._branch: # tag refers to branch
        p = string.rfind(number, '.')
        if p < 0:
          raise vclib.InvalidRevision(number) 
        return number[:p] == self._branch
      else: # tag refers to a revision
        return 0
    else: # tag refers to the trunk
      return string.count(number, '.') == 1

  def number(self):
    return self._branch or self._rev


def parse_log_header(fp):
  """Parse and RCS/CVS log header.

  fp is a file (pipe) opened for reading the log information.

  On entry, fp should point to the start of a log entry.
  On exit, fp will have consumed the separator line between the header and
  the first revision log.

  If there is no revision information (e.g. the "-h" switch was passed to
  rlog), then fp will consumed the file separator line on exit.
  """
  filename = head = branch = ""
  taginfo = { }         # tag name => number

  parsing_tags = 0
  eof = None

  while 1:
    line = fp.readline()
    if not line:
      # the true end-of-file
      eof = _EOF_LOG
      break

    if parsing_tags:
      if line[0] == '\t':
        [ tag, rev ] = map(string.strip, string.split(line, ':'))
        taginfo[tag] = rev
      else:
        # oops. this line isn't tag info. stop parsing tags.
        parsing_tags = 0

    if not parsing_tags:
      if line[:9] == 'RCS file:':
        filename = line[10:-1]
      elif line[:5] == 'head:':
        head = line[6:-1]
      elif line[:7] == 'branch:':
        branch = line[8:-1]
      elif line[:14] == 'symbolic names':
        # start parsing the tag information
        parsing_tags = 1
      elif line == ENTRY_END_MARKER:
        # end of the headers
        break
      elif line == LOG_END_MARKER:
        # end of this file's log information
        eof = _EOF_FILE
        break
      elif line[:6] == 'rlog: ':
        # rlog: filename/goes/here,v: error message
        idx = string.find(line, ': ', 6)
        if idx != -1:
          if line[idx:idx+32] == ': warning: Unknown phrases like ':
            # don't worry about this warning. it can happen with some RCS
            # files that have unknown fields in them (e.g. "permissions 644;"
            continue

          # looks like a filename
          filename = line[6:idx]
          return LogHeader(filename), _EOF_ERROR
        # dunno what this is

  return LogHeader(filename, head, branch, taginfo), eof

_re_log_info = re.compile(r'^date:\s+([^;]+);'
                          r'\s+author:\s+([^;]+);'
                          r'\s+state:\s+([^;]+);'
                          r'(\s+lines:\s+([0-9\s+-]+))?\n$')
### _re_rev should be updated to extract the "locked" flag
_re_rev = re.compile(r'^revision\s+([0-9.]+).*')
def parse_log_entry(fp):
  """Parse a single log entry.

  On entry, fp should point to the first line of the entry (the "revision"
  line).
  On exit, fp will have consumed the log separator line (dashes) or the
  end-of-file marker (equals).

  Returns: revision, date (time_t secs), author, state, lines changed,
  the log text, and eof flag (see _EOF_*)
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
  date = compat.timegm(tm)

  return LogEntry(rev, date,
                  # author, state, lines changed
                  match.group(2), match.group(3), match.group(5),
                  log), eof

def skip_file(fp):
  "Skip the rest of a file's log information."
  while 1:
    line = fp.readline()
    if not line:
      break
    if line == LOG_END_MARKER:
      break

def rcs_popen(rcs_paths, rcs_cmd, rcs_args, mode, capture_err=1):
  if rcs_paths.cvsnt_exe_path:
    cmd = rcs_paths.cvsnt_exe_path
    args = ['rcsfile', rcs_cmd]
    args.extend(rcs_args)
  else:
    cmd = os.path.join(rcs_paths.rcs_path, rcs_cmd)
    args = rcs_args
  return popen.popen(cmd, args, mode, capture_err)

def path_ends_in(path, ending):
  if path == ending:
    return 1
  le = len(ending)
  if le >= len(path):
    return 0
  return path[-le:] == ending and path[-le-1] == os.sep

def get_logs(repos, path_parts, entries, view_tag, get_dirs=0):
  have_logs = 0
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
      entries_idx = entries_idx + 1

      path = None
      if not entry.verboten:
        if entry.kind == vclib.FILE:
          path = (entry.in_attic and ['Attic'] or []) + [entry.name]
        elif entry.kind == vclib.DIR and get_dirs and entry.name != 'Attic':
          assert not entry.in_attic
          entry.newest_file = repos._newest_file(path_parts + [entry.name])
          if entry.newest_file:
            path = [entry.name, entry.newest_file]

      if path:
        entry.path = repos._getpath(path_parts + path) + ',v'
        chunk.append(entry)

      # set a value even if we don't retrieve logs
      entry.rev = None

    if not chunk:
      return have_logs, alltags

    args = []
    if not view_tag:
      # NOTE: can't pass tag on command line since a tag may contain "-"
      #       we'll search the output for the appropriate revision
      # fetch the latest revision on the default branch
      args.append('-r')
    args.extend(map(lambda x: x.path, chunk))
    rlog = rcs_popen(repos.rcs_paths, 'rlog', args, 'rt')

    # consume each file found in the resulting log
    for file in chunk:
      header, eof = parse_log_header(rlog)

      # the rlog output is done
      if eof == _EOF_LOG:
        raise vclib.Error('Rlog output ended early. Expected RCS file "%s"'
                          % file.path)

      # check path_ends_in instead of file == header.filename because of
      # cvsnt's rlog, which only outputs the base filename 
      # http://www.cvsnt.org/cgi-bin/bugzilla/show_bug.cgi?id=188
      if not (header.filename and path_ends_in(file.path, header.filename)):
        raise vclib.Error('Error parsing rlog output. Expected RCS file "%s"'
                          ', found "%s"' % (file.path, header.filename))

      # an error was found regarding this file
      if eof == _EOF_ERROR:
        file.rev = _FILE_HAD_ERROR
        continue

      # if we hit the end of the log information (already!), then there is
      # nothing we can do with this file
      if eof:
        continue

      if view_tag == 'MAIN':
        view_tag_info = TagInfo(header.branch)
      elif view_tag == 'HEAD':
        view_tag_info = TagInfo(header.head)
      elif header.taginfo.has_key(view_tag):
        view_tag_info = TagInfo(header.taginfo[view_tag])
      elif view_tag:
        # the tag wasn't found, so skip this file
        skip_file(rlog)
        continue
      else:
        view_tag_info = None       

      # we don't care about the specific values -- just the keys and whether
      # the values point to branches or revisions. this the fastest way to 
      # merge the set of keys and keep values that allow us to make the 
      # distinction between branch tags and normal tags
      alltags.update(header.taginfo)

      # read all of the log entries until we find the revision we want
      while 1:

        # fetch one of the log entries
        entry, eof = parse_log_entry(rlog)

        if not entry:
          # parsing error
          if not eof:
            skip_file(rlog)
          break

        rev = entry.rev
        if (not view_tag_info or view_tag_info.matches_rev(rev) or
            view_tag_info.holds_rev(rev)):

          have_logs = 1
          file.rev = rev
          file.date = entry.date
          file.author = entry.author
          file.state = entry.state
          file.log = entry.log

          # done with this file now, skip the rest of this file's revisions
          if not eof:
            skip_file(rlog)
          break

        # if we hit the true EOF, or just this file's end-of-info, then we are
        # done collecting log entries.
        if eof:
          break

    status = rlog.close()
    if status:
      raise 'error during rlog: '+hex(status)

def fetch_log(rcs_paths, full_name, which_rev=None):
  if which_rev:
    args = ('-r' + which_rev, full_name)
  else:
    args = (full_name,)
  rlog = rcs_popen(rcs_paths, 'rlog', args, 'rt', 0)

  header, eof = parse_log_header(rlog)
  head = header.head
  branch = header.branch
  taginfo = header.taginfo

  if eof:
    # no log entries or a parsing failure
    return head, branch, taginfo, [ ]

  revs = [ ]
  while 1:
    entry, eof = parse_log_entry(rlog)
    if entry:
      # valid revision info
      revs.append(entry)
    if eof:
      break

  return head, branch, taginfo, revs


if sys.platform == "win32":
  def _check_path(path):
    kind = None
    if os.path.isfile(path):
      kind = vclib.FILE
    elif os.path.isdir(path):
      kind = vclib.DIR
    return kind, not os.access(path, os.R_OK)

else:
  _uid = os.getuid()
  _gid = os.getgid()

  def _check_path(pathname):
    try:
      info = os.stat(pathname)
    except os.error:
      return None, 1

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

      valid = 1
      if info[stat.ST_UID] == _uid:
        if ((mode >> 6) & mask) != mask:
          valid = 0
      elif info[stat.ST_GID] == _gid:
        if ((mode >> 3) & mask) != mask:
          valid = 0
      # If the process running the web server is a member of
      # the group stat.ST_GID access may be granted.
      # so the fall back to os.access is needed to figure this out.
      elif ((mode & mask) != mask) and (os.access(pathname,os.R_OK) == -1):
        valid = 0

      if isdir:
        kind = vclib.DIR
      else:
        kind = vclib.FILE

      return kind, not valid

    return None, 1


### suck up other warnings in _re_co_warning?
_re_co_filename = re.compile(r'^(.*),v\s+-->\s+standard output\s*\n$')
_re_co_warning = re.compile(r'^.*co: .*,v: warning: Unknown phrases like .*\n$')
_re_co_revision = re.compile(r'^revision\s+([\d\.]+)\s*\n$')


class BinCVSRepository(vclib.Repository):
  def __init__(self, name, rootpath, rcs_paths):
    if not os.path.isdir(rootpath):
      raise vclib.ReposNotFound(name)

    self.name = name
    self.rootpath = rootpath
    self.rcs_paths = rcs_paths

  def itemtype(self, path_parts):
    basepath = self._getpath(path_parts)
    if os.path.isdir(basepath):
      return vclib.DIR
    if os.path.isfile(self._getrcsname(basepath)):
      return vclib.FILE
    raise vclib.ItemNotFound(path_parts)

  def openfile(self, path_parts, rev=None):
    if not rev or rev == 'HEAD':
      rev_flag = '-p'
    else:
      rev_flag = '-p' + rev

    full_name = self._getpath(path_parts)

    fp = rcs_popen(self.rcs_paths, 'co', (rev_flag, full_name), 'rb')

    # header from co:
    #
    #/home/cvsroot/mod_dav/dav_shared_stub.c,v  -->  standard output
    #revision 1.1
    #
    # Sometimes, the following line might occur at line 2:
    #co: INSTALL,v: warning: Unknown phrases like `permissions ...;' are present.

    # parse the output header
    filename = revision = None

    line = fp.readline()
    if not line:
      raise vclib.Error('Missing output from co.<br>'
                        'fname="%s". url="%s"' % (filename, where))

    match = _re_co_filename.match(line)
    if not match:
      raise debug.ViewcvsException(
        'First line of co output is not the filename.<br>'
        'Line was: %s<br>'
        'fname="%s". url="%s"' % (line, filename, where))
    filename = match.group(1)

    line = fp.readline()
    if not line:
      raise vclib.Error(
        'Missing second line of output from co.<br>'
        'fname="%s". url="%s"' % (filename, where))
    match = _re_co_revision.match(line)
    if not match:
      match = _re_co_warning.match(line)
      if not match:
        raise vclib.Error(
          'Second line of co output is not the revision.<br>'
          'Line was: %s<br>'
          'fname="%s". url="%s"' % (line, filename, where))

      # second line was a warning. ignore it and move along.
      line = fp.readline()
      if not line:
        raise vclib.Error(
          'Missing third line of output from co (after a warning).<br>'
          'fname="%s". url="%s"' % (filename, where))
      match = _re_co_revision.match(line)
      if not match:
        raise vclib.Error(
          'Third line of co output is not the revision.<br>'
          'Line was: %s<br>'
          'fname="%s". url="%s"' % (line, filename, where))

    # one of the above cases matches the revision. grab it.
    revision = match.group(1)

    if filename != full_name:
      raise vclib.Error(
        'The filename from co did not match. Found "%s". Wanted "%s"<br>'
        'url="%s"' % (filename, full_name, where))

    return fp, revision

  def listdir(self, path_parts, list_attic=1):
    # Only RCS files (*,v) and subdirs are returned.

    data = [ ]

    full_name = self._getpath(path_parts)
    for file in os.listdir(full_name):
      kind, verboten = _check_path(os.path.join(full_name, file))
      if kind == vclib.FILE:
        if file[-2:] == ',v':
          data.append(CVSDirEntry(file[:-2], kind, verboten, 0))
      else:
        data.append(CVSDirEntry(file, kind, verboten, 0))

    if list_attic:
      full_name = os.path.join(full_name, 'Attic')
      if os.path.isdir(full_name):
        for file in os.listdir(full_name):
          kind, verboten = _check_path(os.path.join(full_name, file))
          if kind == vclib.FILE and file[-2:] == ',v':
            data.append(CVSDirEntry(file[:-2], kind, verboten, 1))

    return data

  def _getpath(self, path_parts):
    return apply(os.path.join, (self.rootpath,) + tuple(path_parts))

  def _getrcsname(self, filename):
    if filename[-2:] == ',v':
      return filename
    else:
      return filename + ',v'

  def _newest_file(self, path_parts):
    newest_file = None
    newest_time = 0

    dirpath = self._getpath(path_parts)

    for subfile in os.listdir(dirpath):
      ### filter CVS locks? stale NFS handles?
      if subfile[-2:] != ',v':
        continue
      info = os.stat(os.path.join(dirpath, subfile))
      if not stat.S_ISREG(info[stat.ST_MODE]):
        continue
      if info[stat.ST_MTIME] > newest_time:
        newest_file = subfile[:-2]
        newest_time = info[stat.ST_MTIME]

    return newest_file


class CVSDirEntry(vclib.DirEntry):
  def __init__(self, name, kind, verboten, in_attic):
    vclib.DirEntry.__init__(self, name, kind, verboten)
    self.in_attic = in_attic
