#!/usr/bin/env python
# -*-python-*-
#
# Copyright (C) 1999-2010 The ViewCVS Group. All Rights Reserved.
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

import sys
import string
import os
import re
import time
import math
import vclib
import sapi

re_includes = re.compile('\\#(\\s*)include(\\s*)"(.*?)"')

def link_includes(text, repos, path_parts, include_url):
  match = re_includes.match(text)
  if match:
    incfile = match.group(3)
    include_path_parts = path_parts[:-1]
    for part in filter(None, string.split(incfile, '/')):
      if part == "..":
        if not include_path_parts:
          # nothing left to pop; don't bother marking up this include.
          return text
        include_path_parts.pop()
      elif part and part != ".":
        include_path_parts.append(part)

    include_path = None
    try:
      if repos.itemtype(include_path_parts, None) == vclib.FILE:
        include_path = string.join(include_path_parts, '/')
    except vclib.ItemNotFound:
      pass

    if include_path:
      return '#%sinclude%s<a href="%s">"%s"</a>' % \
             (match.group(1), match.group(2),
              string.replace(include_url, '/WHERE/', include_path), incfile)
    
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
    thisline = link_includes(sapi.escape(item.text), self.repos,
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
  import vclib.ccvs.blame
  bs = vclib.ccvs.blame.BlameSource(os.path.join(root, rcs_path))

  line = 0
  old_revision = 0
  row_color = 'ffffff'
  rev_count = 0

  align = ' style="text-align: %s;"'

  sys.stdout.write('<table cellpadding="2" cellspacing="2" style="font-family: monospace; whitespace: pre;">\n')
  for line_data in bs:
    revision = line_data.rev
    thisline = line_data.text
    line = line_data.line_number
    author = line_data.author
    prev_rev = line_data.prev_rev

    if old_revision != revision and line != 1:
      if row_color == 'ffffff':
        row_color = 'e7e7e7'
      else:
        row_color = 'ffffff'

    sys.stdout.write('<tr id="l%d" style="background-color: #%s; vertical-align: center;">' % (line, row_color))
    sys.stdout.write('<td%s>%d</td>' % (align % 'right', line))

    if old_revision != revision or rev_count > 20:
      sys.stdout.write('<td%s>%s</td>' % (align % 'right', author or '&nbsp;'))
      sys.stdout.write('<td%s>%s</td>' % (align % 'left', revision))
      old_revision = revision
      rev_count = 0
    else:
      sys.stdout.write('<td>&nbsp;</td><td>&nbsp;</td>')
    rev_count = rev_count + 1

    sys.stdout.write('<td%s>%s</td></tr>\n' % (align % 'left', string.rstrip(thisline) or '&nbsp;'))
  sys.stdout.write('</table>\n')


def main():
  import sys
  if len(sys.argv) != 3:
    print 'USAGE: %s cvsroot rcs-file' % sys.argv[0]
    sys.exit(1)
  make_html(sys.argv[1], sys.argv[2])

if __name__ == '__main__':
  main()
