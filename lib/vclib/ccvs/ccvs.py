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

import os
import string
import re
import cStringIO
import tempfile

import vclib
import rcsparse
import blame

### The functionality shared with bincvs should probably be moved to a
### separate module
from bincvs import BaseCVSRepository, Revision, Tag, _file_log, _log_path, _logsort_date_cmp, _logsort_rev_cmp

class CCVSRepository(BaseCVSRepository):
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
    entries_to_fetch = []
    for entry in entries:
      if vclib.check_path_access(self, path_parts + [entry.name], None, rev):
        entries_to_fetch.append(entry)

    subdirs = options.get('cvs_subdirs', 0)

    dirpath = self._getpath(path_parts)
    alltags = {           # all the tags seen in the files of this dir
      'MAIN' : '',
      'HEAD' : '1.1'
    }

    for entry in entries_to_fetch:
      entry.rev = entry.date = entry.author = None
      entry.dead = entry.absent = entry.log = entry.lockinfo = None
      path = _log_path(entry, dirpath, subdirs)
      if path:
        entry.path = path
        try:
          rcsparse.parse(open(path, 'rb'), InfoSink(entry, rev, alltags))
        except IOError, e:
          entry.errors.append("rcsparse error: %s" % e)
        except RuntimeError, e:
          entry.errors.append("rcsparse error: %s" % e)
        except rcsparse.RCSStopParser:
          pass

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

    Option values returned by this implementation:

      cvs_tags
        dictionary of Tag objects for all tags encountered
    """
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts, "/")))

    path = self.rcsfile(path_parts, 1)
    sink = TreeSink()
    rcsparse.parse(open(path, 'rb'), sink)
    filtered_revs = _file_log(sink.revs.values(), sink.tags, sink.lockinfo,
                              sink.default_branch, rev)
    for rev in filtered_revs:
      if rev.prev and len(rev.number) == 2:
        rev.changed = rev.prev.next_changed
    options['cvs_tags'] = sink.tags

    if sortby == vclib.SORTBY_DATE:
      filtered_revs.sort(_logsort_date_cmp)
    elif sortby == vclib.SORTBY_REV:
      filtered_revs.sort(_logsort_rev_cmp)
      
    if len(filtered_revs) < first:
      return []
    if limit:
      return filtered_revs[first:first+limit]
    return filtered_revs

  def rawdiff(self, path_parts1, rev1, path_parts2, rev2, type, options={}):
    if self.itemtype(path_parts1, rev1) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts1, "/")))
    if self.itemtype(path_parts2, rev2) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts2, "/")))
    
    temp1 = tempfile.mktemp()
    open(temp1, 'wb').write(self.openfile(path_parts1, rev1)[0].getvalue())
    temp2 = tempfile.mktemp()
    open(temp2, 'wb').write(self.openfile(path_parts2, rev2)[0].getvalue())

    r1 = self.itemlog(path_parts1, rev1, vclib.SORTBY_DEFAULT, 0, 0, {})[-1]
    r2 = self.itemlog(path_parts2, rev2, vclib.SORTBY_DEFAULT, 0, 0, {})[-1]

    info1 = (self.rcsfile(path_parts1, root=1, v=0), r1.date, r1.string)
    info2 = (self.rcsfile(path_parts2, root=1, v=0), r2.date, r2.string)

    diff_args = vclib._diff_args(type, options)

    return vclib._diff_fp(temp1, temp2, info1, info2,
                          self.utilities.diff or 'diff', diff_args)

  def annotate(self, path_parts, rev=None):
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts, "/")))
    source = blame.BlameSource(self.rcsfile(path_parts, 1), rev)
    return source, source.revision

  def revinfo(self, rev):
    raise vclib.UnsupportedFeature

  def openfile(self, path_parts, rev=None):
    if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
      raise vclib.Error("Path '%s' is not a file."
                        % (string.join(path_parts, "/")))
    path = self.rcsfile(path_parts, 1)
    sink = COSink(rev)
    rcsparse.parse(open(path, 'rb'), sink)
    revision = sink.last and sink.last.string
    return cStringIO.StringIO(string.join(sink.sstext.text, "\n")), revision

class MatchingSink(rcsparse.Sink):
  """Superclass for sinks that search for revisions based on tag or number"""

  def __init__(self, find):
    """Initialize with tag name or revision number string to match against"""
    if not find or find == 'MAIN' or find == 'HEAD':
      self.find = None
    else:
      self.find = find

    self.find_tag = None

  def set_principal_branch(self, branch_number):
    if self.find is None:
      self.find_tag = Tag(None, branch_number)

  def define_tag(self, name, revision):
    if name == self.find:
      self.find_tag = Tag(None, revision)

  def admin_completed(self):
    if self.find_tag is None:
      if self.find is None:
        self.find_tag = Tag(None, '')
      else:
        try:
          self.find_tag = Tag(None, self.find)
        except ValueError:
          pass

class InfoSink(MatchingSink):
  def __init__(self, entry, tag, alltags):
    MatchingSink.__init__(self, tag)
    self.entry = entry
    self.alltags = alltags
    self.matching_rev = None
    self.perfect_match = 0
    self.lockinfo = { }

  def define_tag(self, name, revision):
    MatchingSink.define_tag(self, name, revision)
    self.alltags[name] = revision

  def admin_completed(self):
    MatchingSink.admin_completed(self)
    if self.find_tag is None:
      # tag we're looking for doesn't exist
      if self.entry.kind == vclib.FILE:
        self.entry.absent = 1
      raise rcsparse.RCSStopParser

  def set_locker(self, rev, locker):
    self.lockinfo[rev] = locker
    
  def define_revision(self, revision, date, author, state, branches, next):
    if self.perfect_match:
      return

    tag = self.find_tag
    rev = Revision(revision, date, author, state == "dead")
    rev.lockinfo = self.lockinfo.get(revision)
    
    # perfect match if revision number matches tag number or if revision is on
    # trunk and tag points to trunk. imperfect match if tag refers to a branch
    # and this revision is the highest revision so far found on that branch
    perfect = ((rev.number == tag.number) or
               (not tag.number and len(rev.number) == 2))
    if perfect or (tag.is_branch and tag.number == rev.number[:-1] and
                   (not self.matching_rev or
                    rev.number > self.matching_rev.number)):
      self.matching_rev = rev
      self.perfect_match = perfect

  def set_revision_info(self, revision, log, text):
    if self.matching_rev:
      if revision == self.matching_rev.string:
        self.entry.rev = self.matching_rev.string
        self.entry.date = self.matching_rev.date
        self.entry.author = self.matching_rev.author
        self.entry.dead = self.matching_rev.dead
        self.entry.lockinfo = self.matching_rev.lockinfo
        self.entry.absent = 0
        self.entry.log = log
        raise rcsparse.RCSStopParser
    else:
      raise rcsparse.RCSStopParser

class TreeSink(rcsparse.Sink):
  d_command = re.compile('^d(\d+)\\s(\\d+)')
  a_command = re.compile('^a(\d+)\\s(\\d+)')

  def __init__(self):
    self.revs = { }
    self.tags = { }
    self.head = None
    self.default_branch = None
    self.lockinfo = { }
    
  def set_head_revision(self, revision):
    self.head = revision

  def set_principal_branch(self, branch_number):
    self.default_branch = branch_number

  def set_locker(self, rev, locker):
    self.lockinfo[rev] = locker
    
  def define_tag(self, name, revision):
    # check !tags.has_key(tag_name)
    self.tags[name] = revision

  def define_revision(self, revision, date, author, state, branches, next):
    # check !revs.has_key(revision)
    self.revs[revision] = Revision(revision, date, author, state == "dead")

  def set_revision_info(self, revision, log, text):
    # check revs.has_key(revision)
    rev = self.revs[revision]
    rev.log = log

    changed = None
    added = 0
    deled = 0
    if self.head != revision:
      changed = 1
      lines = string.split(text, '\n')
      idx = 0
      while idx < len(lines):
        command = lines[idx]
        dmatch = self.d_command.match(command)
        idx = idx + 1
        if dmatch:
          deled = deled + string.atoi(dmatch.group(2))
        else:
          amatch = self.a_command.match(command)
          if amatch:
            count = string.atoi(amatch.group(2))
            added = added + count
            idx = idx + count
          elif command:
            raise "error while parsing deltatext: %s" % command

    if len(rev.number) == 2:
      rev.next_changed = changed and "+%i -%i" % (deled, added)
    else:
      rev.changed = changed and "+%i -%i" % (added, deled)

class StreamText:
  d_command = re.compile('^d(\d+)\\s(\\d+)')
  a_command = re.compile('^a(\d+)\\s(\\d+)')

  def __init__(self, text):
    self.text = string.split(text, "\n")

  def command(self, cmd):
    adjust = 0
    add_lines_remaining = 0
    diffs = string.split(cmd, "\n")
    if diffs[-1] == "":
      del diffs[-1]
    if len(diffs) == 0:
      return
    if diffs[0] == "":
      del diffs[0]
    for command in diffs:
      if add_lines_remaining > 0:
        # Insertion lines from a prior "a" command
        self.text.insert(start_line + adjust, command)
        add_lines_remaining = add_lines_remaining - 1
        adjust = adjust + 1
        continue
      dmatch = self.d_command.match(command)
      amatch = self.a_command.match(command)
      if dmatch:
        # "d" - Delete command
        start_line = string.atoi(dmatch.group(1))
        count      = string.atoi(dmatch.group(2))
        begin = start_line + adjust - 1
        del self.text[begin:begin + count]
        adjust = adjust - count
      elif amatch:
        # "a" - Add command
        start_line = string.atoi(amatch.group(1))
        count      = string.atoi(amatch.group(2))
        add_lines_remaining = count
      else:
        raise RuntimeError, 'Error parsing diff commands'

def secondnextdot(s, start):
  # find the position the second dot after the start index.
  return string.find(s, '.', string.find(s, '.', start) + 1)


class COSink(MatchingSink):
  def __init__(self, rev):
    MatchingSink.__init__(self, rev)

  def set_head_revision(self, revision):
    self.head = Revision(revision)
    self.last = None
    self.sstext = None

  def admin_completed(self):
    MatchingSink.admin_completed(self)
    if self.find_tag is None:
      raise vclib.InvalidRevision(self.find)

  def set_revision_info(self, revision, log, text):
    tag = self.find_tag
    rev = Revision(revision)

    if rev.number == tag.number:
      self.log = log

    depth = len(rev.number)

    if rev.number == self.head.number:
      assert self.sstext is None
      self.sstext = StreamText(text)
    elif (depth == 2 and tag.number and rev.number >= tag.number[:depth]):
      assert len(self.last.number) == 2
      assert rev.number < self.last.number
      self.sstext.command(text)
    elif (depth > 2 and rev.number[:depth-1] == tag.number[:depth-1] and
          (rev.number <= tag.number or len(tag.number) == depth-1)):
      assert len(rev.number) - len(self.last.number) in (0, 2)
      assert rev.number > self.last.number
      self.sstext.command(text)
    else:
      rev = None

    if rev:
      #print "tag =", tag.number, "rev =", rev.number, "<br>"
      self.last = rev
