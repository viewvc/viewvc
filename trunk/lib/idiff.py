# -*-python-*-
#
# Copyright (C) 1999-2002 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# idiff: display differences between files highlighting intraline changes
#
# -----------------------------------------------------------------------

from __future__ import generators

import difflib
import sys
import re
import ezt
import cgi

def sidebyside(fromlines, tolines, context):
  """Generate side by side diff"""

  ### for some reason mdiff chokes on \n's in input lines
  line_strip = lambda line: line.rstrip("\n")
  fromlines = map(line_strip, fromlines)
  tolines = map(line_strip, tolines)

  gap = False
  for fromdata, todata, flag in difflib._mdiff(fromlines, tolines, context):
    if fromdata is None and todata is None and flag is None:
      gap = True
    else:
      from_item = _mdiff_split(flag, fromdata)
      to_item = _mdiff_split(flag, todata)
      yield _item(gap=ezt.boolean(gap), columns=(from_item, to_item))
      gap = False

_re_mdiff = re.compile("\0([+-^])(.*?)\1")

def _mdiff_split(flag, (line_number, text)):
  """Break up row from mdiff output into segments"""
  segments = []
  pos = 0
  while True:
    m = _re_mdiff.search(text, pos)
    if not m:
      segments.append(_item(text=cgi.escape(text[pos:]), type=None))
      break

    if m.start() > pos:
      segments.append(_item(text=cgi.escape(text[pos:m.start()]), type=None))

    if m.group(1) == "+":
      segments.append(_item(text=cgi.escape(m.group(2)), type="add"))
    elif m.group(1) == "-":
      segments.append(_item(text=cgi.escape(m.group(2)), type="remove"))
    elif m.group(1) == "^":
      segments.append(_item(text=cgi.escape(m.group(2)), type="change"))

    pos = m.end()

  return _item(segments=segments, line_number=line_number)  

class _item:
  def __init__(self, **kwargs):
    vars(self).update(**kwargs)

try:
  ### Using difflib._mdiff function here was the easiest way of obtaining
  ### intraline diffs for use in ViewVC, but it doesn't exist prior to
  ### Python 2.4 and is not part of the public difflib API, so for now
  ### fall back if it doesn't exist.
  difflib._mdiff
except AttributeError:
  sidebyside = None
