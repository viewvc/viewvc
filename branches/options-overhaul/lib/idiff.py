# -*-python-*-
#
# Copyright (C) 1999-2006 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
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

def unified(fromlines, tolines, context):
  """Generate unified diff"""

  diff = difflib.Differ().compare(fromlines, tolines)
  lastrow = None

  for row in _trim_context(diff, context):
    if row[0].startswith("? "):
      yield _differ_split(lastrow, row[0])
      lastrow = None
    else:
      if lastrow:
        yield _differ_split(lastrow, None)
      lastrow = row

  if lastrow:
    yield _differ_split(lastrow, None)

def _trim_context(lines, context_size):
  """Trim context lines that don't surround changes from Differ results

  yields (line, leftnum, rightnum, gap) tuples"""

  # circular buffer to hold context lines
  context_buffer = [None] * (context_size or 0)
  context_start = context_len = 0

  # number of context lines left to print after encountering a change
  context_owed = 0

  # current line numbers
  leftnum = rightnum = 0

  # whether context lines have been dropped
  gap = False

  for line in lines:
    row = save = None

    if line.startswith("- "):
      leftnum = leftnum + 1
      row = line, leftnum, None
      context_owed = context_size

    elif line.startswith("+ "):
      rightnum = rightnum + 1
      row = line, None, rightnum
      context_owed = context_size

    else:
      if line.startswith("  "):
        leftnum = leftnum = leftnum + 1
        rightnum = rightnum = rightnum + 1
        if context_owed > 0:
          context_owed = context_owed - 1
        elif context_size is not None:
          save = True

      row = line, leftnum, rightnum

    if save:
      # don't yield row right away, store it in buffer
      context_buffer[(context_start + context_len) % context_size] = row
      if context_len == context_size:
        context_start = (context_start + 1) % context_size
        gap = True
      else:
        context_len = context_len + 1
    else:
      # yield row, but first drain stuff in buffer
      context_len == context_size
      while context_len:
        yield context_buffer[context_start] + (gap,)
        gap = False
        context_start = (context_start + 1) % context_size
        context_len = context_len - 1
      yield row + (gap,)
      gap = False

_re_differ = re.compile(r"[+-^]+")

def _differ_split(row, guide):
  """Break row into segments using guide line"""
  line, left_number, right_number, gap = row

  if left_number and right_number:
    type = "" 
  elif left_number:
    type = "remove"
  elif right_number:
    type = "add"

  segments = []  
  pos = 2

  if guide:
    assert guide.startswith("? ")

    for m in _re_differ.finditer(guide, pos):
      if m.start() > pos:
        segments.append(_item(text=cgi.escape(line[pos:m.start()]), type=None))
      segments.append(_item(text=cgi.escape(line[m.start():m.end()]),
                            type="change"))
      pos = m.end()

  segments.append(_item(text=cgi.escape(line[pos:]), type=None))

  return _item(gap=ezt.boolean(gap), type=type, segments=segments,
               left_number=left_number, right_number=right_number)

class _item:
  def __init__(self, **kw):
    vars(self).update(kw)

try:
  ### Using difflib._mdiff function here was the easiest way of obtaining
  ### intraline diffs for use in ViewVC, but it doesn't exist prior to
  ### Python 2.4 and is not part of the public difflib API, so for now
  ### fall back if it doesn't exist.
  difflib._mdiff
except AttributeError:
  sidebyside = None
