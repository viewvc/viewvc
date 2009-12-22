#! /usr/bin/python

# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2006-2007 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.  The terms
# are also available at http://subversion.tigris.org/license-1.html.
# If newer versions of this license are posted there, you may use a
# newer version instead, at your option.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs, available at http://cvs2svn.tigris.org/.
# ====================================================================

"""Parse an RCS file, showing the rcsparse callbacks that are called.

This program is useful to see whether an RCS file has a problem (in
the sense of not being parseable by rcsparse) and also to illuminate
the correspondence between RCS file contents and rcsparse callbacks.

The output of this program can also be considered to be a kind of
'canonical' format for RCS files, at least in so far as rcsparse
returns all relevant information in the file and provided that the
order of callbacks is always the same."""


import sys
import os


class Logger:
  def __init__(self, f, name):
    self.f = f
    self.name = name

  def __call__(self, *args):
    self.f.write(
        '%s(%s)\n' % (self.name, ', '.join(['%r' % arg for arg in args]),)
        )


class LoggingSink:
  def __init__(self, f):
    self.f = f

  def __getattr__(self, name):
    return Logger(self.f, name)


if __name__ == '__main__':
  # Since there is nontrivial logic in __init__.py, we have to import
  # parse() via that file.  First make sure that the directory
  # containing this script is in the path:
  sys.path.insert(0, os.path.dirname(sys.argv[0]))

  from __init__ import parse

  if sys.argv[1:]:
    for path in sys.argv[1:]:
      if os.path.isfile(path) and path.endswith(',v'):
        parse(
            open(path, 'rb'), LoggingSink(sys.stdout)
            )
      else:
        sys.stderr.write('%r is being ignored.\n' % path)
  else:
    parse(sys.stdin, LoggingSink(sys.stdout))


