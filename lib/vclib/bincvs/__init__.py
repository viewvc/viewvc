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
    if os.path.isfile(basepath + ',v'):
      return vclib.FILE
    raise vclib.ItemNotFound(path_parts)

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

  def openfile(self, path_parts, rev=None):
    if not rev or rev == 'HEAD' or rev == 'MAIN':
      rev_flag = '-p'
    else:
      rev_flag = '-p' + rev

    full_name = self._getpath(path_parts)

    fp = self.rcs_popen('co', (rev_flag, full_name), 'rb')

    filename, revision = parse_co_header(fp)
    if filename is None:
      # CVSNT's co exits without any output if a dead revision is requested.
      # Bug at http://www.cvsnt.org/cgi-bin/bugzilla/show_bug.cgi?id=190
      # As a workaround, we invoke rlog to find the first non-dead revision
      # that precedes it and check out that revision instead
      revs = file_log(self, path_parts, rev)[0]

      # if we find a good revision, invoke co again, otherwise error out
      if len(revs) and revs[-1].undead:
        rev_flag = '-p' + revs[-1].undead.string
        fp = rcs_popen(self.rcs_paths, 'co', (rev_flag, full_name), 'rb')
        filename, revision = parse_co_header(fp)
      else:
        raise vclib.Error("CVSNT co workaround could not find non-dead "
                          "revision preceding \"%s\"" % rev)

    if filename is None:
      raise vclib.Error('Missing output from co.<br>fname="%s".' % full_name)

    if filename != full_name:
      raise vclib.Error(
        'The filename from co did not match. Found "%s". Wanted "%s"<br>'
        'url="%s"' % (filename, full_name, where))

    return fp, revision

  def rcs_popen(self, rcs_cmd, rcs_args, mode, capture_err=1):
    if self.rcs_paths.cvsnt_exe_path:
      cmd = self.rcs_paths.cvsnt_exe_path
      args = ['rcsfile', rcs_cmd]
      args.extend(rcs_args)
    else:
      cmd = os.path.join(self.rcs_paths.rcs_path, rcs_cmd)
      args = rcs_args
    return popen.popen(cmd, args, mode, capture_err)

  def _getpath(self, path_parts):
    return apply(os.path.join, (self.rootpath,) + tuple(path_parts))

class CVSDirEntry(vclib.DirEntry):
  def __init__(self, name, kind, verboten, in_attic):
    vclib.DirEntry.__init__(self, name, kind, verboten)
    self.in_attic = in_attic

class Revision:
  def __init__(self, revstr, date, author, state, changed, log):
    self.number = _revision_tuple(revstr)
    self.string = revstr
    self.date = date
    self.author = author
    self.state = state
    self.changed = changed
    self.log = log
    self.dead = state == "dead"

  def __cmp__(self, other):
    return cmp(self.number, other.number)

class Tag:
  def __init__(self, name, revstr):
    self.name = name
    self.number = _tag_tuple(revstr)
    self.is_branch = len(self.number) % 2 == 1 or not self.number


# ======================================================================
# Functions for dealing with Revision and Tag objects

def match_revs_tags(revlist, taglist):
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

  This function assumes it will be passed a complete, feasible sequence of
  revisions. If an invalid sequence is passed it will return garbage or throw
  exceptions.
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
      if depth == 0 or rev.number[:-1] == prev.number[:-1]:
        rev.prev = prev
        prev.next = rev

    # set "parent"
    if depth > 0:
      assert history[depth-1].number == rev.number[:-2]
      rev.parent = history[depth-1]
    else:
      rev.parent = None

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
      rev.branch_number = rev.parent and rev.number[:-1] or ()
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
    if depth < len(history):
      history[depth] = rev
    else:
      assert depth == len(history)
      history.append(rev)

def add_tag(tag_name, revision):
  """Create a new tag object and associate it with a revision"""
  tag = Tag(tag_name, revision.string)
  revision.tags.append(tag)
  tag.co_rev = revision
  tag.aliases = revision.tags
  return tag
  
def remove_tag(tag):
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
      raise ValueError
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

### suck up other warnings in _re_co_warning?
_re_co_filename = re.compile(r'^(.*),v\s+-->\s+standard output\s*\n$')
_re_co_warning = re.compile(r'^.*co: .*,v: warning: Unknown phrases like .*\n$')
_re_co_revision = re.compile(r'^revision\s+([\d\.]+)\s*\n$')

def parse_co_header(fp):
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
  filename = revision = None

  line = fp.readline()
  if not line:
    return None, None

  match = _re_co_filename.match(line)
  if not match:
    raise vclib.Error(
      'First line of co output is not the filename.<br>'
      'Line was: %s<br>'
      'fname="%s"' % (line, full_name))
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

  return filename, revision


# if your rlog doesn't use 77 '=' characters, then this must change
LOG_END_MARKER = '=' * 77 + '\n'
ENTRY_END_MARKER = '-' * 28 + '\n'

_EOF_FILE = 'end of file entries'       # no more entries for this RCS file
_EOF_LOG = 'end of log'                 # hit the true EOF on the pipe
_EOF_ERROR = 'error message found'      # rlog issued an error

_FILE_HAD_ERROR = 'could not read file'

_re_lineno = re.compile(r'\:\d+$')

def parse_log_header(fp):
  """Parse and RCS/CVS log header.

  fp is a file (pipe) opened for reading the log information.

  On entry, fp should point to the start of a log entry.
  On exit, fp will have consumed the separator line between the header and
  the first revision log.

  If there is no revision information (e.g. the "-h" switch was passed to
  rlog), then fp will consumed the file separator line on exit.

  Returns: filename, default branch, tag dictionary, and eof flag
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
        # rlog: filename/goes/here,v:123: error message
        idx = string.find(line, ': ', 6)
        if idx != -1:
          if line[idx:idx+32] == ': warning: Unknown phrases like ':
            # don't worry about this warning. it can happen with some RCS
            # files that have unknown fields in them (e.g. "permissions 644;"
            continue

          # look for a line number after the filename
          match = _re_lineno.search(line, 6, idx)
          if match:
            idx = match.start()

          # looks like a filename
          filename = line[6:idx]
          return filename, branch, taginfo, _EOF_ERROR
      elif line[-28:] == ": No such file or directory\n":
        # For some reason the windows version of rlog omits the "rlog: "
        # prefix for first error message when the standard error stream
        # is redirected to a file or pipe. (the prefix is present
        # in subsequent errors and when rlog is run from the console
        # This is just a special case to prevent an especially common
        # error message from being lost when this happens
        filename = line[:-28]
        return filename, branch, taginfo, _EOF_ERROR
        # dunno what this is

  return filename, branch, taginfo, eof

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
  date = compat.timegm(tm)

  return Revision(rev, date,
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


# ======================================================================
# Functions for interpreting and manipulating log information

def file_log(repos, path_parts, filter):
  """Run rlog on a file, return list of Revisions and a dictionary of Tags"""
  # Invoke rlog
  args = repos._getpath(path_parts) + ',v',
  fp = repos.rcs_popen('rlog', args, 'rt', 0)
  filename, cur_branch, taginfo, eof = parse_log_header(fp)

  # Add artificial ViewCVS tag MAIN. If the file has a default branch, then
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

  # Retrieve revision objects
  revs = []
  while not eof:
    rev, eof = parse_log_entry(fp)
    if rev:
      revs.append(rev)

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
  match_revs_tags(revs, tags)

  # Add artificial ViewCVS tag HEAD, which acts like a non-branch tag pointing
  # at the latest revision on the MAIN branch. The HEAD revision doesn't have
  # anything to do with the "head" revision number specified in the RCS file
  # and in rlog output. HEAD refers to the revision that the CVS and RCS co
  # commands will check out by default, whereas the "head" field just refers
  # to the highest revision on the trunk.  
  taginfo['HEAD'] = add_tag('HEAD', taginfo['MAIN'].co_rev)

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
    if view_tag.is_branch:
      for rev in revs:
        if rev.branch_number == view_tag.number or rev is view_tag.branch_rev:
          filtered_revs.append(rev)
    elif view_tag.co_rev:
      filtered_revs.append(view_tag.co_rev)

    # get rid of the view_tag if it was only created for filtering
    if view_tag.name is None:
      remove_tag(view_tag)
  else:
    filtered_revs = revs
  
  return filtered_revs, taginfo

def _sort_tags(alltags):
  alltagnames = alltags.keys()
  alltagnames.sort(lambda t1, t2: cmp(string.lower(t1), string.lower(t2)))
  alltagnames.reverse()
  branch_tags = []
  plain_tags = []
  for tag in alltagnames:
    rev = alltags[tag]
    if Tag(None, rev).is_branch:
      branch_tags.append(tag)
    else:
      plain_tags.append(tag)      
  return branch_tags, plain_tags

def get_logs(repos, path_parts, entries, view_tag, get_dirs=0):
  alltags = {           # all the tags seen in the files of this dir
    'MAIN' : '',
    'HEAD' : '1.1'
    }

  dirpath = repos._getpath(path_parts)

  entries_idx = 0
  entries_len = len(entries)
  max_args = 100

  while 1:
    chunk = []

    while len(chunk) < max_args and entries_idx < entries_len:
      entry = entries[entries_idx]

      path = name = None
      if not entry.verboten:
        if entry.kind == vclib.FILE:
          path = entry.in_attic and 'Attic' or ''
          name = entry.name
        elif entry.kind == vclib.DIR and get_dirs and entry.name != 'Attic':
          assert not entry.in_attic
          entry.newest_file = _newest_file(os.path.join(dirpath, entry.name))
          if entry.newest_file:
            path = entry.name
            name = entry.newest_file

      if name:
        entry.path = os.path.join(dirpath, path, name + ',v')
        entry.idx = entries_idx
        chunk.append(entry)

      # set a value even if we don't retrieve logs
      entry.rev = entry.state = None

      entries_idx = entries_idx + 1

    if not chunk:
      repos.branch_tags, repos.plain_tags = _sort_tags(alltags)
      return

    args = []
    if not view_tag:
      # NOTE: can't pass tag on command line since a tag may contain "-"
      #       we'll search the output for the appropriate revision
      # fetch the latest revision on the default branch
      args.append('-r')
    args.extend(map(lambda x: x.path, chunk))
    rlog = repos.rcs_popen('rlog', args, 'rt')

    # consume each file found in the resulting log
    for file in chunk:
      filename, default_branch, taginfo, eof = parse_log_header(rlog)

      if eof == _EOF_LOG:
        # the rlog output ended early. this happens on errors that rlog thinks
        # are so serious that it stops parsing the current file and refuses
        # to parse any of the files that come after it. one of the errors that
        # triggers this obnoxious behavior looks like:
        #
        # rlog: c:\cvsroot\dir\file,v:8: unknown expand mode u
        # rlog aborted

        if file is not chunk[0]:
          # if this isn't the first file, go back and run rlog again
          # starting with this file
          entries_idx = file.idx
          break

        # if this is the first file and there's no output, then
        # something really is wrong
        raise vclib.Error('Rlog output ended early. Expected RCS file "%s"'
                          % file.path)

      # check path_ends_in instead of file.path == filename because of
      # cvsnt's rlog, which only outputs the base filename 
      # http://www.cvsnt.org/cgi-bin/bugzilla/show_bug.cgi?id=188
      if not (filename and path_ends_in(file.path, filename)):
        raise vclib.Error('Error parsing rlog output. Expected RCS file "%s"'
                          ', found "%s"' % (file.path, filename))

      # an error was found regarding this file
      if eof == _EOF_ERROR:
        file.rev = _FILE_HAD_ERROR
        continue

      # if we hit the end of the log information (already!), then there is
      # nothing we can do with this file
      if eof:
        continue

      if view_tag == 'MAIN' or view_tag == 'HEAD':
        tag = Tag(None, default_branch)
      elif taginfo.has_key(view_tag):
        tag = Tag(None, taginfo[view_tag])
      elif view_tag:
        # the tag wasn't found, so skip this file
        skip_file(rlog)
        continue
      else:
        tag = None

      # we don't care about the specific values -- just the keys and whether
      # the values point to branches or revisions. this the fastest way to 
      # merge the set of keys and keep values that allow us to make the 
      # distinction between branch tags and normal tags
      alltags.update(taginfo)

      # read all of the log entries until we find the revision we want
      wanted_entry = None
      while 1:

        # fetch one of the log entries
        entry, eof = parse_log_entry(rlog)

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
        if perfect or entry.number[-2:] == tag.number[:-1]:
          wanted_entry = entry
          if perfect:
            break

        # if we hit the true EOF, or just this file's end-of-info, then we are
        # done collecting log entries.
        if eof:
          break

      if wanted_entry:
        file.rev = wanted_entry.string
        file.date = wanted_entry.date
        file.author = wanted_entry.author
        file.state = wanted_entry.state
        file.log = wanted_entry.log

      # done with this file now, skip the rest of this file's revisions
      if not eof:
        skip_file(rlog)

    rlog.close()

def fetch_log(rcs_paths, full_name, which_rev=None):
  if which_rev:
    args = ('-r' + which_rev, full_name)
  else:
    args = (full_name,)
  rlog = repos.rcs_popen('rlog', args, 'rt', 0)

  filename, branch, taginfo, eof = parse_log_header(rlog)

  if eof:
    # no log entries or a parsing failure
    return branch, taginfo, [ ]

  revs = [ ]
  while 1:
    entry, eof = parse_log_entry(rlog)
    if entry:
      # valid revision info
      revs.append(entry)
    if eof:
      break

  return branch, taginfo, revs


# ======================================================================
# Functions for dealing with the filesystem

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
      elif (mode & mask) != mask:
        if not os.access(pathname, isdir and (os.R_OK | os.X_OK) or os.R_OK):
          valid = 0

      if isdir:
        kind = vclib.DIR
      else:
        kind = vclib.FILE

      return kind, not valid

    return None, 1

def _newest_file(dirpath):
  """Find the last modified RCS file in a directory"""
  newest_file = None
  newest_time = 0

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

def path_ends_in(path, ending):
  if path == ending:
    return 1
  le = len(ending)
  if le >= len(path):
    return 0
  return path[-le:] == ending and path[-le-1] == os.sep
