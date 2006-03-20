#!/usr/bin/env python
# -*-python-*-
#
# Copyright (C) 1999-2006 The ViewCVS Group. All Rights Reserved.
# Copyright (C) 2000 Curt Hagenlocher <curt@hagenlocher.org>
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# blame.py: Annotate each line of a CVS file with its author,
#           revision #, date, etc.
#
# -----------------------------------------------------------------------
#
# This file is based on the cvsblame.pl portion of the Bonsai CVS tool,
# developed by Steve Lamm for Netscape Communications Corporation.  More
# information about Bonsai can be found at
#    http://www.mozilla.org/bonsai.html
#
# cvsblame.pl, in turn, was based on Scott Furman's cvsblame script
#
# -----------------------------------------------------------------------

import string
import os
import re
import time
import math
import cgi
import vclib
import vclib.ccvs.blame


re_includes = re.compile('\\#(\\s*)include(\\s*)"(.*?)"')

def link_includes(text, repos, path_parts, include_url):
  match = re_includes.match(text)
  if match:
    incfile = match.group(3)

    # check current directory and parent directory for file
    for depth in (-1, -2):
      include_path = path_parts[:depth] + [incfile]
      try:
        # will throw if path doesn't exist
        if repos.itemtype(include_path, None) == vclib.FILE:
          break
      except vclib.ItemNotFound:
        pass
    else:
      include_path = None

    if include_path:
        url = string.replace(include_url, '/WHERE/', 
                             string.join(include_path, '/'))
        return '#%sinclude%s<a href="%s">"%s"</a>' % \
               (match.group(1), match.group(2), url, incfile)
       
  return text


class HTMLBlameSource:
  """Wrapper around a the object by the vclib.annotate() which does
  HTML escaping, diff URL generation, and #include linking."""
  def __init__(self, repos, path_parts, diff_url, include_url, opt_rev=None):
    self.repos = repos
    self.path_parts = path_parts
    self.diff_url = diff_url
    self.include_url = include_url
    self.annotation, self.revision = self.repos.annotate(path_parts, opt_rev)

  def __getitem__(self, idx):
    item = self.annotation.__getitem__(idx)
    diff_url = None
    if item.prev_rev:
      diff_url = '%sr1=%s&amp;r2=%s' % (self.diff_url, item.prev_rev, item.rev)
    thisline = link_includes(cgi.escape(item.text), self.repos,
                             self.path_parts, self.include_url)
    return _item(text=thisline, line_number=item.line_number,
                 rev=item.rev, prev_rev=item.prev_rev,
                 diff_url=diff_url, date=item.date, author=item.author)


def blame(repos, path_parts, diff_url, include_url, opt_rev=None):
  source = HTMLBlameSource(repos, path_parts, diff_url, include_url, opt_rev)
  return source, source.revision


class _item:
  def __init__(self, **kw):
    vars(self).update(kw)


def make_html(root, rcs_path):
  bs = vclib.ccvs.blame.BlameSource(os.path.join(root, rcs_path))

  count = bs.num_lines
  if count == 0:
    count = 1

  line_num_width = int(math.log10(count)) + 1
  revision_width = 3
  author_width = 5
  line = 0
  old_revision = 0
  row_color = ''
  inMark = 0
  rev_count = 0

  open_table_tag = '<table cellpadding="0" cellspacing="0">'
  startOfRow = '<tr><td colspan="3"%s><pre>'
  endOfRow = '</td></tr>'

  print open_table_tag + (startOfRow % '')

  for line_data in bs:
    revision = line_data.rev
    thisline = line_data.text
    line = line_data.line_number
    author = line_data.author
    prev_rev = line_data.prev_rev
    
    output = ''

    if old_revision != revision and line != 1:
      if row_color == '':
        row_color = ' style="background-color:#e7e7e7"'
      else:
        row_color = ''

      if not inMark:
        output = output + endOfRow + (startOfRow % row_color)

    output = output + '<a name="%d">%*d</a>' % (line, line_num_width, line)

    if old_revision != revision or rev_count > 20:
      revision_width = max(revision_width, len(revision))
      output = output + ' '
      author_width = max(author_width, len(author))
      output = output + ('%-*s ' % (author_width, author))
      output = output + revision
      if prev_rev:
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
  import sys
  if len(sys.argv) != 3:
    print 'USAGE: %s cvsroot rcs-file' % sys.argv[0]
    sys.exit(1)
  make_html(sys.argv[1], sys.argv[2])

if __name__ == '__main__':
  main()
