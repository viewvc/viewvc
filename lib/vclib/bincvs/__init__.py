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


def parse_log_header(fp):
  """Parse and RCS/CVS log header.

  fp is a file (pipe) opened for reading the log information.

  On entry, fp should point to the start of a log entry.
  On exit, fp will have consumed the separator line between the header and
  the first revision log.

  If there is no revision information (e.g. the "-h" switch was passed to
  rlog), then fp will consumed the file separator line on exit.
  """
  filename = head = branch = None
  taginfo = { }         # tag name => revision

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
        # remove the trailing ,v
        filename = line[10:-3]
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
        idx = string.find(line, ':', 6)
        if idx != -1:
          if line[idx:idx+32] == ': warning: Unknown phrases like ':
            # don't worry about this warning. it can happen with some RCS
            # files that have unknown fields in them (e.g. "permissions 644;"
            continue

          # looks like a filename
          filename = line[6:idx]
          if filename[-2:] == ',v':
            filename = filename[:-2]
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

def process_rlog_output(rlog, full_name, view_tag, fileinfo, alltags):
  "Fill in fileinfo and alltags with info from the rlog output."

  # consume each file found in the resulting log
  while 1:

    revwanted = None
    branch = None
    branchpoint = None

    header, eof = parse_log_header(rlog)
    filename = header.filename
    head = header.head
    branch = header.branch
    symrev = header.taginfo

    # the rlog output is done
    if eof == _EOF_LOG:
      break

    if filename:
      # convert from absolute to relative
      if filename[:len(full_name)] == full_name:
        filename = filename[len(full_name)+1:]

      # for a subdir (not Attic files!), use the subdir for a key
      idx = string.find(filename, '/')
      if idx != -1 and filename[:6] != 'Attic/':
        info_key = filename[:idx]
      else:
        info_key = filename

    # an error was found regarding this file
    if eof == _EOF_ERROR:
      fileinfo[info_key] = _FILE_HAD_ERROR
      continue

    # if we hit the end of the log information (already!), then there is
    # nothing we can do with this file
    if eof:
      continue

    if not filename or not head:
      # parsing error. skip the rest of this file.
      skip_file(rlog)
      continue

    if not branch:
      idx = string.rfind(head, '.')
      branch = head[:idx]
    idx = string.rfind(branch, '.')
    if idx == -1:
      branch = '0.' + branch
    else:
      branch = branch[:idx] + '.0' + branch[idx:]

    symrev['MAIN'] = symrev['HEAD'] = branch

    if symrev.has_key(view_tag):
      revwanted = symrev[view_tag]
      if revwanted[:2] == '0.': ### possible?
        branch = revwanted[2:]
      else:
        idx = string.find(revwanted, '.0.')
        if idx == -1:
          branch = revwanted
        else:
          branch = revwanted[:idx] + revwanted[idx+2:]
      if revwanted != branch:
        revwanted = None

      idx = string.rfind(branch, '.')
      if idx == -1:
        branchpoint = ''
      else:
        branchpoint = branch[:idx]

    elif view_tag:
      # the tag wasn't found, so skip this file
      skip_file(rlog)
      continue

    # we don't care about the values -- just the keys. this the fastest
    # way to merge the set of keys
    alltags.update(symrev)

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

      idx = string.rfind(rev, '.')
      revbranch = rev[:idx]

      if not view_tag or (not revwanted and branch == revbranch):
        revwanted = rev

      if rev == revwanted or rev == branchpoint:
        new_entry = LogEntry(rev, entry.date, entry.author, entry.state,
                             None, entry.log)
        new_entry.filename = filename
        fileinfo[info_key] = new_entry
#        fileinfo[info_key] = (rev, entry.date, entry.log, entry.author,
#                              filename, entry.state)

        if rev == revwanted:
          # done with this file now
          if not eof:
            skip_file(rlog)
          break

      # if we hit the true EOF, or just this file's end-of-info, then we are
      # done collecting log entries.
      if eof:
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

def get_logs(rcs_paths, full_name, files, view_tag):

  if len(files) == 0:
    return { }, { }

  files = files[:]
  fileinfo = { }
  alltags = {           # all the tags seen in the files of this dir
    'MAIN' : '1',
    'HEAD' : '1',
    }

  chunk_size = 100
  while files:
    chunk = files[:chunk_size]
    del files[:chunk_size]

    # prepend the full pathname for each file
    for i in range(len(chunk)):
      chunk[i] = full_name + '/' + chunk[i]

    if not view_tag:
      # NOTE: can't pass tag on command line since a tag may contain "-"
      #       we'll search the output for the appropriate revision
      # fetch the latest revision on the default branch
      chunk = ('-r',) + tuple(chunk)

    rlog = rcs_popen(rcs_paths, 'rlog', chunk, 'rt', 0)

    process_rlog_output(rlog, full_name, view_tag, fileinfo, alltags)

    ### it would be nice to verify that we got SOMETHING from rlog about
    ### each file. if we didn't, then it could be that the chunk is still
    ### too large, so we want to cut the chunk_size in half and try again.
    ###
    ### BUT: if we didn't get feedback for some *other* reason, then halving
    ### the chunk size could merely send us into a needless retry loop.
    ###
    ### more work for later...

    status = rlog.close()
    if status:
      raise 'error during rlog: '+hex(status)

  return fileinfo, alltags

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

  def getitem(self, path_parts):
    basepath = self._getpath(path_parts)
    if os.path.isdir(basepath):
      return vclib.Versdir(self, basepath)
    rcspath = self._getrcsname(basepath)
    if os.path.isfile(rcspath):
      return vclib.Versfile(self, rcspath)
    raise vclib.ItemNotFound(path_parts)

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

  def listdir(self, path_parts):
    # Only RCS files (*,v) and subdirs are returned.

    full_name = self._getpath(path_parts)
    files = os.listdir(full_name)
    data = [ ]

    if sys.platform == "win32":
      uid = 1
      gid = 1
    else:
      uid = os.getuid()
      gid = os.getgid()

    for file in files:
      pathname = os.path.join(full_name, file)
      try:
        info = os.stat(pathname)
      except os.error:
        data.append(vclib.DirEntry(file, None, 1))
        continue
      mode = info[stat.ST_MODE]
      isdir = stat.S_ISDIR(mode)
      isreg = stat.S_ISREG(mode)
      if (isreg and file[-2:] == ',v') or isdir:
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
        if info[stat.ST_UID] == uid:
          if ((mode >> 6) & mask) != mask:
            valid = 0
        elif info[stat.ST_GID] == gid:
          if ((mode >> 3) & mask) != mask:
            valid = 0
        # If the process running the web server is a member of
        # the group stat.ST_GID access may be granted.
        # so the fall back to os.access is needed to figure this out.
        elif ((mode & mask) != mask) and (os.access(pathname,os.R_OK) == -1):
          valid = 0

        if isdir:
          name = file
          kind = vclib.DIR
        else:
          name = file[:-2]
          kind = vclib.FILE

        data.append(vclib.DirEntry(name, kind, not valid))

    return data

  def _getpath(self, path_parts):
    return apply(os.path.join, (self.rootpath,) + tuple(path_parts))

  def _getrcsname(self, filename):
    if filename[-2:] == ',v':
      return filename
    else:
      return filename + ',v'  

  def _getvf_subdirs(self, basepath):
    h = os.listdir(basepath)
    g = { }
    for i in h:
      thispath = os.path.join(basepath, i)
      if os.path.isdir(thispath):
        g[i] = vclib.Versdir(self, thispath)
    return g
    
  def _getvf_files(self, basepath):
    h = os.listdir(basepath)
    g = { }
    for i in h:
      rcspath = self._getrcsname(os.path.join(basepath, i))
      if os.path.isfile(rcspath):
      	g[i] = vclib.Versfile(self, rcspath)
    return g  
  
  def _getvf_info(self, target, basepath):
    """
    This method will add to <target> (expect to be an instance of Versfile)
    a certain number of attributes:
    head (string)
    age (int timestamp)
    author (string)
    log
    branch
    ... ( there can be other stuff here)
    
    Developers: method to be overloaded.
    """
    if not os.path.isfile(basepath):
      raise "Unknown file: %s " % basepath
    rlog = popen.popen('rlog', basepath, 'rt')
    header, eof = parse_log_header(rlog)
    target.head = header.head
    target.branch = header.branch
    target.taginfo = header.taginfo
    
  def _getvf_tree(self, versfile):
    """
    should return a dictionary of Revisions
    Developers: method to be overloaded.
    """

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

  def _getvf_cofile(self, target, basepath):
    """
    should return a file object representing the checked out revision.
    Notice that _getvf_co can also add the properties in <target> the
    way _getvf_properties does.  

    Developers: method to be overloaded.
    """
    fp = popen.popen('co', ('-p' + rev, basepath, 'rb'))
    fp.readline()
    fp.readline()
    return fp
