#!/usr/local/bin/python
# -*-python-*-
#
# Copyright (C) 2000-2001 The ViewCVS Group. All Rights Reserved.
# Copyright (C) 2000 Curt Hagenlocher <curt@hagenlocher.org>
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
#
# blame.py: Annotate each line of a CVS file with its author,
#           revision #, date, etc.
#
# -----------------------------------------------------------------------
#
# This software is being maintained as part of the ViewCVS project.
# Information is available at:
#    http://viewcvs.sourceforge.net/
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

import string
import sys
import os
import re
import time
import math
import cgi
import rcsparse

class CVSParser(rcsparse.Sink):
  # Precompiled regular expressions
  trunk_rev   = re.compile('^[0-9]+\\.[0-9]+$')
  last_branch = re.compile('(.*)\\.[0-9]+')
  is_branch   = re.compile('(.*)\\.0\\.([0-9]+)')
  d_command   = re.compile('^d(\d+)\\s(\\d+)')
  a_command   = re.compile('^a(\d+)\\s(\\d+)')

  SECONDS_PER_DAY = 86400

  def __init__(self):
    self.Reset()

  def Reset(self):
    self.last_revision = {}
    self.prev_revision = {}
    self.revision_date = {}
    self.revision_author = {}
    self.revision_branches = {}
    self.next_delta = {}
    self.prev_delta = {}
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

  # Map a tag to a numerical revision number.  The tag can be a symbolic
  # branch tag, a symbolic revision tag, or an ordinary numerical
  # revision number.
  def map_tag_to_revision(self, tag_or_revision):
    try:
      revision = self.tag_revision[tag_or_revision]
      match = self.is_branch.match(revision)
      if match:
        branch = match.group(1) + '.' + match.group(2)
        if self.last_revision.get(branch):
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
    revision = self.prev_revision.get(revision)
    while revision:
      ancestors.append(revision)
      revision = self.prev_revision.get(revision)

    return ancestors

  # Split deltatext specified by rev to each line.
  def deltatext_split(self, rev):
    lines = string.split(self.revision_deltatext[rev], '\n')
    if lines[-1] == '':
      del lines[-1]
    return lines

  # Extract the given revision from the digested RCS file.
  # (Essentially the equivalent of cvs up -rXXX)
  def extract_revision(self, revision):
    path = []
    add_lines_remaining = 0
    start_line = 0
    count = 0
    while revision:
      path.append(revision)
      revision = self.prev_delta.get(revision)
    path.reverse()
    path = path[1:]  # Get rid of head revision

    text = self.deltatext_split(self.head_revision)

    # Iterate, applying deltas to previous revision
    for revision in path:
      adjust = 0
      diffs = self.deltatext_split(revision)
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

  def set_head_revision(self, revision):
    self.head_revision = revision

  def set_principal_branch(self, branch_name):
    self.principal_branch = branch_name

  def define_tag(self, name, revision):
    # Create an associate array that maps from tag name to
    # revision number and vice-versa.
    self.tag_revision[name] = revision

    ### actually, this is a bit bogus... a rev can have multiple names
    self.revision_symbolic_name[revision] = name

  def set_comment(self, comment):
    self.file_description = comment

  def set_description(self, description):
    self.rcs_file_description = description

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
  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    self.tag_revision[revision] = revision
    branch = self.last_branch.match(revision).group(1)
    self.last_revision[branch] = revision

    #self.revision_date[revision] = date
    self.timestamp[revision] = timestamp

    # Pretty print the date string
    ltime = time.localtime(self.timestamp[revision])
    formatted_date = time.strftime("%d %b %Y %H:%M", ltime)
    self.revision_ctime[revision] = formatted_date

    # Save age
    self.revision_age[revision] = ((time.time() - self.timestamp[revision])
                                   / self.SECONDS_PER_DAY)

    # save author
    self.revision_author[revision] = author

    # ignore the state

    # process the branch information
    branch_text = ''
    for branch in branches:
      self.prev_revision[branch] = revision
      self.next_delta[revision] = branch
      self.prev_delta[branch] = revision
      branch_text = branch_text + branch + ''
    self.revision_branches[revision] = branch_text

    # process the "next revision" information
    if next:
      self.next_delta[revision] = next
      self.prev_delta[next] = revision
      is_trunk_revision = self.trunk_rev.match(revision) is not None
      if is_trunk_revision:
        self.prev_revision[revision] = next
      else:
        self.prev_revision[next] = revision

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
  def set_revision_info(self, revision, log, text):
    self.revision_log[revision] = log
    self.revision_deltatext[revision] = text

  def parse_cvs_file(self, rcs_pathname, opt_rev = None, opt_m_timestamp = None):
    # Args in:  opt_rev - requested revision
    #           opt_m - time since modified
    # Args out: revision_map
    #           timestamp
    #           revision_deltatext

    # CheckHidden(rcs_pathname);
    try:
      rcsfile = open(rcs_pathname, 'r')
    except:
      raise RuntimeError, ('error: %s appeared to be under CVS control, ' +
              'but the RCS file is inaccessible.') % rcs_pathname

    rcsparse.Parser().parse(rcsfile, self)
    rcsfile.close()

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
    while self.prev_revision.get(primordial):
      primordial = self.prev_revision[primordial]

    # Don't display file at all, if -m option is specified and no
    # changes have been made in the specified file.
    if opt_m_timestamp and self.timestamp[revision] < opt_m_timestamp:
      return ''

    # Figure out how many lines were in the primordial, i.e. version 1.1,
    # check-in by moving backward in time from the head revision to the
    # first revision.
    line_count = 0
    if self.revision_deltatext.get(self.head_revision):
      tmp_array = self.deltatext_split(self.head_revision)
      line_count = len(tmp_array)

    skip = 0

    rev = self.prev_revision.get(self.head_revision)
    while rev:
      diffs = self.deltatext_split(rev)
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

      rev = self.prev_revision.get(rev)

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
	diffs = self.deltatext_split(last_revision)

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
	diffs = self.deltatext_split(revision)
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


re_includes = re.compile('\\#(\\s*)include(\\s*)"(.*?)"')
re_filename = re.compile('(.*[\\\\/])?(.+)')

def link_includes(text, root, rcs_path, sticky = None):
  match = re_includes.match(text)
  if match:
    incfile = match.group(3)
    for rel_path in ('', 'Attic', '..'):
      trial_root = os.path.join(rcs_path, rel_path)
      file = os.path.join(root, trial_root)
      file = os.path.normpath(os.path.join(file, incfile + ',v'))
      if os.access(file, os.F_OK):
	url = os.path.join(rel_path, incfile)
	if sticky:
	  url = url + '?' + sticky
        return '#%sinclude%s"<a href="%s">%s</a>"' % \
               (match.group(1), match.group(2), url, incfile)
  return text

def make_html(root, rcs_path, opt_rev = None, sticky = None):
  filename = os.path.join(root, rcs_path)
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

  open_table_tag = '<table border=0 cellpadding=0 cellspacing=0 width="100%">'
  startOfRow = '<tr><td colspan=3%s><pre>'
  endOfRow = '</td></tr>'

  print open_table_tag + (startOfRow % '')

  if count == 0:
    count = 1

  line_num_width = int(math.log10(count)) + 1
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
      thisline = link_includes(thisline, root, file_head, sticky)

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

      if parser.prev_revision.get(revision):
        fname = file_tail[:-2]	# strip the ",v"
	url = '%s.diff?r1=%s&amp;r2=%s' % \
	      (fname, parser.prev_revision[revision], revision)
	if sticky:
	  url = url + '&' + sticky
	output = output + ' <a href="%s"' % (url, )
        if 0: # use_layers
          output = output + " onmouseover='return log(event,\"%s\",\"%s\");'" % (
                  parser.prev_revision[revision], revision)
        output = output + ">"
      else:
        output = output + " "
        parser.prev_revision[revision] = ''

      author = parser.revision_author[revision]
      # $author =~ s/%.*$//;
      author_width = max(author_width, len(author))
      output = output + ('%%-%ds ' % (author_width, )) % (author, )
      output = output + revision
      if parser.prev_revision.get(revision):
        output = output + '</a>'
      output = output + (' ' * (revision_width - len(revision) + 1))

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
  print endOfRow + '</table>'


def main():
  if len(sys.argv) != 3:
    print 'USAGE: %s cvsroot rcs-file' % sys.argv[0]
    sys.exit(1)
  make_html(sys.argv[1], sys.argv[2])

if __name__ == '__main__':
  main()
