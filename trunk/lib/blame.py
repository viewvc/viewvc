#!/usr/local/bin/python
# -*-python-*-
#
# Copyright (C) 2000 The ViewCVS Group. All Rights Reserved.
# Copyright (C) 2000 Curt Hagenlocher <curt@hagenlocher.org>
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://www.lyra.org/viewcvs/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://www.lyra.org/viewcvs/
#
# -----------------------------------------------------------------------
#
# blame.py: Annotate each line of a CVS file with its author,
#           revision #, date, etc.
#
# -----------------------------------------------------------------------
#
# This software is being maintained as part of the ViewCVS project.
# Information is available at:
#    http://www.lyra.org/viewcvs/
#
# This file is based on the cvsblame.pl portion of the Bonsai CVS tool,
# developed by Steve Lamm for Netscape Communications Corporation.  More
# information about Bonsai can be found at
#    http://www.mozilla.org/bonsai.html
#
# cvsblame.pl, in turn, was based on Scott Furman's cvsblame script
#
# -----------------------------------------------------------------------
#

cvsroots = ['/home/cvsroot']

import string
import sys
import os
import re
import time
import math
import cgi

is_mozilla  = re.compile('[mM]ozilla/4')
is_msie     = re.compile('MSIE')
path_sep    = os.path.normpath('/')[-1]

class CVSParser:
  # Precompiled regular expressions
  nonws_token = re.compile('^([^;@][^;\\s]*)\\s*')
  semic_token = re.compile('^;\\s*')
  rcsen_token = re.compile('^@([^@]*)')
  undo_escape = re.compile('@@')
  single_at   = re.compile('([^@]|^)@([^@]|$)')
  rcs_tree    = re.compile('^\\d')
  trunk_rev   = re.compile('^[0-9]+\\.[0-9]+$')
  last_branch = re.compile('(.*)\\.[0-9]+')
  is_branch   = re.compile('(.*)\\.0\\.([0-9]+)')
  d_command   = re.compile('^d(\d+)\\s(\\d+)')
  a_command   = re.compile('^a(\d+)\\s(\\d+)')

  SECONDS_PER_DAY = 86400

  def __init__(self):
    self.Reset()

  def Reset(self):
    self.line_buffer = ''
    self.rcsfile = None
    self.debug = 0
    self.last_revision = {}
    self.prev_revision = {}
    self.revision_date = {}
    self.revision_author = {}
    self.revision_branches = {}
    self.next_delta = {}
    self.prev_delta = {}
    self.feof = 0
    self.tag_revision = {}
    self.revision_symbolic_name = {}
    self.timestamp = {}
    self.revision_ctime = {}
    self.revision_age = {}
    self.revision_log = {}
    self.revision_deltatext = {}
    self.revision_map = []
    self.lines_added  = {}
    self.lines_removed = {}

  # Get the next token from the RCS file
  def get_token(self):
    # Erase all-whitespace lines
    while len(self.line_buffer) == 0:
      self.line_buffer = self.rcsfile.readline()
      if self.line_buffer == '':
        raise RuntimeError, 'EOF'
      self.line_buffer = string.lstrip(self.line_buffer)

    # A string of non-whitespace characters is a token
    match = self.nonws_token.match(self.line_buffer)
    if match:
      self.line_buffer = self.nonws_token.sub('', self.line_buffer)
      return match.group(1)

    # ...and so is a single semicolon
    if self.semic_token.match(self.line_buffer):
      self.line_buffer = self.semic_token.sub('', self.line_buffer)
      return ';'

    # ...or an RCS-encoded string that starts with an @ character
    match = self.rcsen_token.match(self.line_buffer)
    self.line_buffer = self.rcsen_token.sub('', self.line_buffer)
    token = match.group(1)

    # Detect single @ character used to close RCS-encoded string
    while string.find(self.line_buffer, '@') < 0 or not self.single_at.match(self.line_buffer):
      token = token + self.line_buffer
      self.line_buffer = self.rcsfile.readline()
      if self.line_buffer == '':
        raise RuntimeError, 'EOF'

    # Retain the remainder of the line after the terminating @ character
    i = string.rindex(self.line_buffer, '@')
    token = token + self.line_buffer[:i]
    self.line_buffer = self.line_buffer[i+1:]

    # Undo escape-coding of @ characters.
    token = self.undo_escape.sub('@', token)

    # Digest any extra blank lines
    while len(self.line_buffer) == 0 or self.line_buffer == '\n':
      self.line_buffer = self.rcsfile.readline()
      if self.line_buffer == '':
        self.feof = 1
        break

    if token[-1:] == '\n':
      token = token[:-1]

    return token

  # Try to match the next token from the input buffer
  def match_token(self, match):
    token = self.get_token()
    if token != match:
      raise RuntimeError, ('Unexpected parsing error in RCS file.\n' +
                           'Expected token: %s, but saw: %s' % (match, token))

  # Push RCS token back into the input buffer.
  def unget_token(self, token):
    self.line_buffer = token + " " + self.line_buffer

  # Map a tag to a numerical revision number.  The tag can be a symbolic
  # branch tag, a symbolic revision tag, or an ordinary numerical
  # revision number.
  def map_tag_to_revision(self, tag_or_revision):
    try:
      revision = self.tag_revision[tag_or_revision]
      match = self.is_branch.match(revision)
      if match:
        branch = match.group(1) + '.' + match.group(2)
        if self.last_revision.has_key(branch) and self.last_revision[branch]:
          return self.last_revision[branch]
        else:
          return match.group(1)
      else:
        return revision
    except:
      return ''

  # Construct an ordered list of ancestor revisions to the given
  # revision, starting with the immediate ancestor and going back
  # to the primordial revision (1.1).
  #
  # Note: The generated path does not traverse the tree the same way
  #       that the individual revision deltas do.  In particular,
  #       the path traverses the tree "backwards" on branches.
  def ancestor_revisions(self, revision):
    ancestors = []
    revision = self.prev_revision[revision]
    while revision:
      ancestors.append(revision)
      if self.prev_revision.has_key(revision):
        revision = self.prev_revision[revision]
      else:
        revision = None

    return ancestors

  # Extract the given revision from the digested RCS file.
  # (Essentially the equivalent of cvs up -rXXX)
  def extract_revision(self, revision):
    path = []
    add_lines_remaining = 0
    start_line = 0
    count = 0
    while revision:
      path.append(revision)
      if self.prev_delta.has_key(revision):
        revision = self.prev_delta[revision]
      else:
        revision = None
    path.reverse()
    path = path[1:]  # Get rid of head revision

    text = string.split(self.revision_deltatext[self.head_revision], '\n')

    # Iterate, applying deltas to previous revision
    for revision in path:
      adjust = 0
      diffs = string.split(self.revision_deltatext[revision], '\n')
      self.lines_added[revision]   = 0
      self.lines_removed[revision] = 0
      lines_added_now = 0
      lines_removed_now = 0

      for command in diffs:
        dmatch = self.d_command.match(command)
        amatch = self.a_command.match(command)
        if add_lines_remaining > 0:
          # Insertion lines from a prior "a" command
          text.insert(start_line + adjust, command)
          add_lines_remaining = add_lines_remaining - 1
          adjust = adjust + 1
        elif dmatch:
          # "d" - Delete command
          start_line = string.atoi(dmatch.group(1))
          count      = string.atoi(dmatch.group(2))
          begin = start_line + adjust - 1
          del text[begin:begin + count]
          adjust = adjust - count
          lines_removed_now = lines_removed_now + count
        elif amatch:
          # "a" - Add command
          start_line = string.atoi(amatch.group(1))
          count      = string.atoi(amatch.group(2))
          add_lines_remaining = count
          lines_added_now = lines_added_now + count
        else:
          raise RuntimeError, 'Error parsing diff commands'

      self.lines_added[revision]   = self.lines_added[revision]   + lines_added_now
      self.lines_removed[revision] = self.lines_removed[revision] + lines_removed_now
    return text

  def parse_rcs_admin(self):
    while 1:
      # Read initial token at beginning of line
      token = self.get_token()

      # We're done once we reach the description of the RCS tree
      if self.rcs_tree.match(token):
        self.unget_token(token)
        return

      # print "token:", token

      if token == "head":
        self.head_revision = self.get_token()
        self.get_token()         # Eat semicolon
      elif token == "branch":
        self.principal_branch = self.get_token()
        self.get_token()         # Eat semicolon
      elif token == "symbols":
        # Create an associate array that maps from tag name to
        # revision number and vice-versa.
        while 1:
          tag = self.get_token()
          if tag == ';':
            break
          (tag_name, tag_rev) = string.split(tag, ':')
          self.tag_revision[tag_name] = tag_rev
          self.revision_symbolic_name[tag_rev] = tag_name
      elif token == "comment":
        self.file_description = self.get_token()
        self.get_token()         # Eat semicolon

      # Ignore all these other fields - We don't care about them.         
      elif token in ("locks", "strict", "expand", "access"):
        while 1:
          tag = self.get_token()
          if tag == ';':
            break
      else:
        pass
        # warn("Unexpected RCS token: $token\n")

    raise RuntimeError, "Unexpected EOF";

  # Construct dicts that represent the topology of the RCS tree
  # and other arrays that contain info about individual revisions.
  #
  # The following dicts are created, keyed by revision number:
  #   self.revision_date     -- e.g. "96.02.23.00.21.52"
  #   self.timestamp         -- seconds since 12:00 AM, Jan 1, 1970 GMT
  #   self.revision_author   -- e.g. "tom"
  #   self.revision_branches -- descendant branch revisions, separated by spaces,
  #                             e.g. "1.21.4.1 1.21.2.6.1"
  #   self.prev_revision     -- revision number of previous *ancestor* in RCS tree.
  #                             Traversal of this array occurs in the direction
  #                             of the primordial (1.1) revision.
  #   self.prev_delta        -- revision number of previous revision which forms
  #                             the basis for the edit commands in this revision.
  #                             This causes the tree to be traversed towards the
  #                             trunk when on a branch, and towards the latest trunk
  #                             revision when on the trunk.
  #   self.next_delta        -- revision number of next "delta".  Inverts prev_delta.
  #
  # Also creates self.last_revision, keyed by a branch revision number, which
  # indicates the latest revision on a given branch,
  #   e.g. self.last_revision{"1.2.8"} == 1.2.8.5

  def parse_rcs_tree(self):
    while 1:
      revision = self.get_token()

      # End of RCS tree description ?
      if revision == 'desc':
        self.unget_token(revision)
        return

      is_trunk_revision = self.trunk_rev.match(revision) is not None

      self.tag_revision[revision] = revision
      branch = self.last_branch.match(revision).group(1)
      self.last_revision[branch] = revision

      # Parse date
      self.match_token('date')
      date = self.get_token()
      self.revision_date[revision] = date
      self.match_token(';')

      # Convert date into timestamp
      date_fields = string.split(date, '.') + ['0', '0', '0']
      date_fields = map(string.atoi, date_fields)
      if date_fields[0] < 100:
        date_fields[0] = date_fields[0] + 1900
      self.timestamp[revision] = time.mktime(date_fields)

      # Pretty print the date string
      ltime = time.localtime(self.timestamp[revision])
      formatted_date = time.strftime("%d %b %Y %H:%M", ltime)
      self.revision_ctime[revision] = formatted_date

      # Save age
      self.revision_age[revision] = (
              (time.time() - self.timestamp[revision]) / self.SECONDS_PER_DAY)

      # Parse author
      self.match_token('author')
      author = self.get_token()
      self.revision_author[revision] = author
      self.match_token(';')

      # Parse state
      self.match_token('state')
      while self.get_token() != ';':
        pass

      # Parse branches
      self.match_token('branches')
      branches = ''
      while 1:
        token = self.get_token()
        if token == ';':
          break
        self.prev_revision[token] = revision
        self.prev_delta[token] = revision
        branches = branches + token + ' '
      self.revision_branches[revision] = branches

      # Parse revision of next delta in chain
      self.match_token('next')
      next = ''
      token = self.get_token()
      if token != ';':
        next = token
        self.get_token()         # Eat semicolon
        self.next_delta[revision] = next
        self.prev_delta[next] = revision
        if is_trunk_revision:
          self.prev_revision[revision] = next
        else:
          self.prev_revision[next] = revision

      if self.debug >= 3:
        print "<pre>revision =", revision
        print "date     = ", date
        print "author   = ", author
        print "branches = ", branches
        print "next     = ", next + "</pre>\n"

  def parse_rcs_description(self):
    self.match_token('desc')
    self.rcs_file_description = self.get_token()

  # Construct associative arrays containing info about individual revisions.
  #
  # The following associative arrays are created, keyed by revision number:
  #   revision_log        -- log message
  #   revision_deltatext  -- Either the complete text of the revision,
  #                          in the case of the head revision, or the
  #                          encoded delta between this revision and another.
  #                          The delta is either with respect to the successor
  #                          revision if this revision is on the trunk or
  #                          relative to its immediate predecessor if this
  #                          revision is on a branch.
  def parse_rcs_deltatext(self):
    while not self.feof:
      revision = self.get_token()
      if self.debug >= 3:
        print "Reading delta for revision:", revision
      self.match_token('log')
      self.revision_log[revision] = self.get_token()
      self.match_token('text')
      self.revision_deltatext[revision] = self.get_token()

  def parse_rcs_file(self):
    if self.debug >= 2:
      print "Reading RCS admin..."
    self.parse_rcs_admin()
    if self.debug >= 2:
      print "Reading RCS revision tree topology..."
    self.parse_rcs_tree()

    if self.debug >= 3:
      print "<pre>Keys:\n"
      for i in self.tag_revision.keys():
        print "yoyuo %s: %s" % (i, self.tag_revision[i])
      print "</pre>"

    self.parse_rcs_description()
    if self.debug >= 2:
      print "Reading RCS revision deltas..."
    self.parse_rcs_deltatext()
    if self.debug >= 2:
      print "Done reading RCS file..."

  def parse_cvs_file(self, rcs_pathname, opt_rev = None, opt_m_timestamp = None):
    # Args in:  opt_rev - requested revision
    #           opt_m - time since modified
    # Args out: revision_map
    #           timestamp
    #           revision_deltatext

    # CheckHidden(rcs_pathname);
    try:
      self.rcsfile = open(rcs_pathname, 'r')
    except:
      raise RuntimeError, ('error: %s appeared to be under CVS control, ' +
              'but the RCS file is inaccessible.') % rcs_pathname

    self.parse_rcs_file()
    self.rcsfile.close()

    if opt_rev in [None, '', 'HEAD']:
      # Explicitly specified topmost revision in tree
      revision = self.head_revision
    else:
      # Symbolic tag or specific revision number specified.
      revision = self.map_tag_to_revision(opt_rev)
      if revision == '':
        raise RuntimeError, 'error: -r: No such revision: ' + opt_rev

    # The primordial revision is not always 1.1!  Go find it.
    primordial = revision
    while self.prev_revision.has_key(primordial) and self.prev_revision[primordial] != '':
      primordial = self.prev_revision[primordial]

    # Don't display file at all, if -m option is specified and no
    # changes have been made in the specified file.
    if opt_m_timestamp and self.timestamp[revision] < opt_m_timestamp:
      return ''

    # Figure out how many lines were in the primordial, i.e. version 1.1,
    # check-in by moving backward in time from the head revision to the
    # first revision.
    line_count = 0
    if (self.revision_deltatext.has_key(self.head_revision) and
                    self.revision_deltatext[self.head_revision]):
      tmp_array = string.split(self.revision_deltatext[self.head_revision], '\n')
      line_count = len(tmp_array)

    skip = 0

    rev = self.prev_revision[self.head_revision]
    while rev:
      diffs = string.split(self.revision_deltatext[rev], '\n')
      for command in diffs:
        dmatch = self.d_command.match(command)
        amatch = self.a_command.match(command)
        if skip > 0:
          # Skip insertion lines from a prior "a" command
          skip = skip - 1
        elif dmatch:
          # "d" - Delete command
          start_line = string.atoi(dmatch.group(1))
          count      = string.atoi(dmatch.group(2))
          line_count = line_count - count
        elif amatch:
          # "a" - Add command
          start_line = string.atoi(amatch.group(1))
          count      = string.atoi(amatch.group(2))
          skip       = count;
          line_count = line_count + count
        else:
          raise RuntimeError, 'error: illegal RCS file'
      if self.prev_revision.has_key(rev):
        rev = self.prev_revision[rev]
      else:
        rev = None

    # Now, play the delta edit commands *backwards* from the primordial
    # revision forward, but rather than applying the deltas to the text of
    # each revision, apply the changes to an array of revision numbers.
    # This creates a "revision map" -- an array where each element
    # represents a line of text in the given revision but contains only
    # the revision number in which the line was introduced rather than
    # the line text itself.
    #
    # Note: These are backward deltas for revisions on the trunk and
    # forward deltas for branch revisions.

    # Create initial revision map for primordial version.
    self.revision_map = [primordial] * line_count

    ancestors = [revision, ] + self.ancestor_revisions(revision)
    ancestors = ancestors[:-1]  # Remove "1.1"
    last_revision = primordial
    ancestors.reverse()
    for revision in ancestors:
      is_trunk_revision = self.trunk_rev.match(revision) is not None

      if is_trunk_revision:
        diffs = string.split(self.revision_deltatext[last_revision], '\n')

        # Revisions on the trunk specify deltas that transform a
        # revision into an earlier revision, so invert the translation
        # of the 'diff' commands.
        for command in diffs:
          if skip > 0:
            skip = skip - 1
          else:
            dmatch = self.d_command.match(command)
            amatch = self.a_command.match(command)
            if dmatch:
              start_line = string.atoi(dmatch.group(1))
              count      = string.atoi(dmatch.group(2))
              temp = []
              while count > 0:
                temp.append(revision)
                count = count - 1
              self.revision_map = (self.revision_map[:start_line - 1] +
                      temp + self.revision_map[start_line - 1:])
            elif amatch:
              start_line = string.atoi(amatch.group(1))
              count      = string.atoi(amatch.group(2))
              del self.revision_map[start_line:start_line + count]
              skip = count
            else:
              raise RuntimeError, 'Error parsing diff commands'

      else:
        # Revisions on a branch are arranged backwards from those on
        # the trunk.  They specify deltas that transform a revision
        # into a later revision.
        adjust = 0
        diffs = string.split(self.revision_deltatext[revision], '\n')
        for command in diffs:
          if skip > 0:
            skip = skip - 1
          else:
            dmatch = self.d_command.match(command)
            amatch = self.a_command.match(command)
            if dmatch:
              start_line = string.atoi(dmatch.group(1))
              count      = string.atoi(dmatch.group(2))
              del self.revision_map[start_line + adjust - 1:start_line + adjust - 1 + count]
              adjust = adjust - count
            elif amatch:
              start_line = string.atoi(amatch.group(1))
              count      = string.atoi(amatch.group(2))
              skip = count
              temp = []
              while count > 0:
                temp.append(revision)
                count = count - 1
              self.revision_map = (self.revision_map[:start_line + adjust] +
                      temp + self.revision_map[start_line + adjust:])
              adjust = adjust + skip
            else:
              raise RuntimeError, 'Error parsing diff commands'

      last_revision = revision

    return revision

opt_a = 1
opt_v = 1
opt_d = 0
opt_A = 0
opt_m = 0
opt_w = 0
opt_l = 1

def show_annotated_cvs_file(pathname):
  global revision_map, output, text

  output = []
  revision = parse_cvs_file(pathname)

  text = extract_revision(revision)
  if len(text) != len(revision_map):
    raise RuntimeError, 'Internal consistency error'

  # Set total width of line annotation.
  # Warning: field widths here must match format strings below.
  annotation_width = 0;
  if opt_a:
    # author
    annotation_width = annotation_width +  8
  if opt_v:
    # revision
    annotation_width = annotation_width +  7
  if opt_A:
    # age
    annotation_width = annotation_width +  6
  if opt_d:
    # date
    annotation_width = annotation_width + 12
  blank_annotation = ' ' * annotation_width

  # Print each line of the revision, preceded by its annotation.
  line = 0
  for revision in revision_map:
    linetxt = text[line]
    line = line + 1
    annotation = ''

    if opt_a:
      # Annotate with revision author
      annotation = annotation + "%-8s" % revision_author[revision]

    if opt_v:
      # Annotate with revision number
      annotation = annotation + " %-6s" % revision

    if opt_d:
      # Date annotation
      annotation = annotation + revision_ctime[revision]

    if opt_A:
      # Age annotation ?
      annotation = annotation + " (%3s)" % int(revision_age[revision])

    # -m (if-modified-since) annotion ?
    if opt_m and timestamp[revision] < opt_m_timestamp:
      annotation = blank_annotation

    if opt_w and string.strip(linetxt) == '':
      # Suppress annotation of whitespace lines, if requested;
      annotation = blank_annotation

    if opt_l:
      output.append('%4d' % line)
    output.append(annotation + ' - ' + linetxt)


re_includes = re.compile('\\#(\\s*)include(\\s*)"(.*?)"')
re_filename = re.compile('(.*[\\\\/])?(.+)')

def link_includes(text, root, rcs_path, browse_revtag = 'HEAD'):
  match = re_includes.match(text)
  if match:
    incfile = match.group(3)
    use_html = 0
    for trial_root in (rcs_path, rcs_path + path_sep + "Attic", rcs_path + path_sep + ".."):
      file = os.path.normpath('%s%s%s%s%s,v' % (root, path_sep, trial_root, path_sep, incfile))
      if os.access(file, os.F_OK):
        # blame.py
        file = os.path.normpath('%s%s%s,v' % (trial_root, path_sep, incfile))
        return '#%sinclude%s"<a href=\'%s?root=%s&file=%s&rev=%s&use_html=%d\'>%s</a>"' % (
                match.group(1), match.group(2), "blame.py", root, file, browse_revtag, use_html, incfile)
  return text

def make_html(root, rcs_path, opt_rev = None):
  print 'Content-Type: text/html'
  print
  print '''\
<!doctype html public "-//W3C//DTD HTML 4.0 Transitional//EN"
 "http://www.w3.org/TR/REC-html40/loose.dtd">
'''

  filename = root + path_sep + rcs_path
  parser = CVSParser()
  revision = parser.parse_cvs_file(filename, opt_rev)
  count = len(parser.revision_map)
  text = parser.extract_revision(revision)
  if len(text) != count:
    raise RuntimeError, 'Internal consistency error'

  match = re_filename.match(rcs_path)
  if not match:
    raise RuntimeError, 'Unable to parse filename'
  file_head = match.group(1)
  file_tail = match.group(2)

  print '<html><head><title>CVS Blame</title>'
  print '<body bgcolor="#FFFFFF" text="#000000" link="#0000EE" vlink="#551A8B" alink="#F0A000">'

  open_table_tag = '<table border=0 cellpadding=0 cellspacing=0 width="100%">'
  startOfRow = '<tr><td colspan=3%s><pre>'
  endOfRow = '</td></tr>'

  print open_table_tag + (startOfRow % '')

  if count == 0:
    count = 1

  line_num_width = int(math.log(count) / math.log(10)) + 1
  revision_width = 3
  author_width = 5
  line = 0
  usedlog = {}
  usedlog[revision] = 1
  old_revision = 0
  row_color = ''
  lines_in_table = 0
  inMark = 0
  rev_count = 0

  for revision in parser.revision_map:
    thisline = text[line]
    line = line + 1
    usedlog[revision] = 1
    line_in_table = lines_in_table + 1

    # Escape HTML meta-characters
    thisline = cgi.escape(thisline)

    # Add a link to traverse to included files
    if 1:   # opt_includes
      thisline = link_includes(thisline, root, file_head)

    output = ''

    # Highlight lines
    #mark_cmd;
    #if (defined($mark_cmd = $mark_line{$line}) and mark_cmd != 'end':
    #	output = output + endOfRow + '<tr><td bgcolor=LIGHTGREEN width="100%"><pre>'
    #	inMark = 1

    if old_revision != revision and line != 1:
      if row_color == '':
        row_color = ' bgcolor="#e7e7e7"'
      else:
        row_color = ''

      if not inMark:
        if lines_in_table > 100:
          output = output + endOfRow + '</table>' + open_table_tag + (startOfRow % row_color)
          lines_in_table = 0
        else:
          output = output + endOfRow + (startOfRow % row_color)

    elif lines_in_table > 200 and not inMark:
      output = output + endOfRow + '</table>' + open_table_tag + (startOfRow % row_color)
      lines_in_table = 0

    output = output + "<a name=%d></a>" % (line, )
    if 1:  # opt_line_nums
      output = output + ('%%%dd' % (line_num_width, )) % (line, )

    if old_revision != revision or rev_count > 20:
      revision_width = max(revision_width, len(revision))

      # output = output + "<a href=\"cvsblame.cgi?file=$filename&rev=$revision&root=$root\""
      if parser.prev_revision.has_key(revision):
        output = output + " <a href=\"viewcvs.py?diff_mode=context&whitespace_mode=show&root=%s&subdir=%s&command=DIFF_FRAMESET&file=%s&r2=%s&r1=%s\"" % (
                root, file_head, file_tail, revision, parser.prev_revision[revision])
      else:
        output = output + " <a href=\"viewcvs.py?root=%s&subdir=%s&command=DIRECTORY&file=%s\"" % (
                root, file_head, file_tail)
        parser.prev_revision[revision] = ''

      if 0: # use_layers
        output = output + " onmouseover='return log(event,\"%s\",\"%s\");'" % (
                parser.prev_revision[revision], revision)
      output = output + ">"
      author = parser.revision_author[revision]
      # $author =~ s/%.*$//;
      author_width = max(author_width, len(author))
      output = output + ('%%-%ds ' % (author_width, )) % (author, )
      output = output + revision + '</a> '
      output = output + (' ' * (revision_width - len(revision)))

      old_revision = revision
      rev_count = 0
    else:
      output = output + '   ' + (' ' * (author_width + revision_width))
    rev_count = rev_count + 1

    output = output + thisline

    # Close the highlighted section
    #if (defined $mark_cmd and mark_cmd != 'begin'):
    #	chop($output)
    #	output = output + endOfRow + (startOfRow % row_color)
    #	inMark = 0

    print output
  print endOfRow + '</table><hr width="100%"></body></html>'


if __name__ == '__main__':
  CVSROOT = cvsroots[0]
  if len(sys.argv) == 2:
    # Command-line testing
    make_html(CVSROOT, sys.argv[1])
  else:
    form = cgi.FieldStorage()
    if form.has_key('root'):
      root = form['root'].value
    else:
      root = CVSROOT
    try:
      cvsroots.index(root)
      root_ok = 1
    except:
      root_ok = 0

    rev = None
    if form.has_key('rev'):
      rev = form['rev'].value
    if root_ok and form.has_key('file'):
      rcs_path = form['file'].value
      while rcs_path[0] in ('\\', '/'):
        rcs_path = rcs_path[1:]
      if string.lower(rcs_path[-2:]) != ',v':
        rcs_path = rcs_path + ',v'
      make_html(root, rcs_path, rev)
    else:
      print 'Content-Type: text/html'
      print
      print '''\
<!doctype html public "-//W3C//DTD HTML 4.0 Transitional//EN"
 "http://www.w3.org/TR/REC-html40/loose.dtd">
<html>Sorry...</html>
'''
