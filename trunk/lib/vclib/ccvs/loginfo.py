#
# Copyright (C) 2002 The ViewCVS Group. All Rights Reserved.
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
# vclib.ccvs.loginfo: utilities for 'loginfo' processing
#
# -----------------------------------------------------------------------
#

import os
import re


def what_changed(cvsroot, change_line, update_line):
  """Determine what changed in the commit of this directory.

  cvsroot: Typically os.environ['CVSROOT']
  change_line: The value %{sVv} provided by CVS to the loginfo handler.
    It normally looks something like:
        testing/subdir foobar,1.11,1.12  baz,1.5,1.6
  update_line: The first line CVS provides to the loginfo handler on stdin.
    It normally looks something like:
        Update of /home/cvsroot/testing/subdir

  The caller should ensure that any trailing white space (eg. newlines)
  has been stripped before passing the values here.

  If the loginfo line looks like:

      ALL (echo %{sVv}; cat) | your-script

  Then change_line will be the first line of your script's stdin. The
  update_line will be the second line. Note that CVS will quote the
  %{sVv} string, so it should not be quoted in CVSROOT/loginfo.

  The parsing of this information is complicated by the fact that the
  first line is space-separated. Naive processing will not handle
  directories or files with spaces in it. Therefore, we take particular
  care in splitting this information up to determine the changes.

  The return value is a 2-tuple. The first element is the directory
  where the commit occurred, relative to CVSROOT (no leading separator,
  nor a trailing separator). The second element is a list of 3-tuples:
  FILENAME, OLD-VERSION, NEW-VERSION. A version number may be NONE if
  the file was added/deleted. If a new directory was created, then the
  list of changed files will be empty.
  """

  # clean up the root a little bit
  while cvsroot[-1] == os.sep:
    cvsroot = cvsroot[:-1]

  # what directory in the repository was updated?
  target_dir = update_line[10:] # strip the "Update of " prefix

  l = len(cvsroot)
  if len(target_dir) <= l or target_dir[:l] != cvsroot \
     or target_dir[l] != os.sep:
    raise CouldNotParseTarget()

  # compute the directory relative to CVSROOT. this is the prefix used
  # in change_line.
  reldir = target_dir[l+1:]

  # on the change line, CVS separates each element by *exactly* one space.
  # here, we validate that a space occurs after the repository directory.
  l = len(reldir)
  if len(change_line) <= l or change_line[:l] != reldir \
     or change_line[l] != ' ':
    raise BadChangePrefix()

  # return an empty list of changed files when a new directory was created.
  # note: this string comes from CVS' src/add.c
  if change_line[l:] == ' - New directory':
    return reldir, [ ]

  return reldir, _re_fileversion.findall(change_line[l:])

# this regex is used to extract the changed file and its revisions. note
# that a single space occurs at the start: CVS separates each element with
# a single space (including a space between the repository dir and the
# first file listed).
# note: the space separator comes from CVS' src/logmsg.c
_re_fileversion = re.compile(" ([^,]+)\,([^,]+)\,([^, ]+)")


class CouldNotParseTarget(Exception):
  pass
class BadChangePrefix(Exception):
  pass

# the what_changed() function assumes len(os.sep) == 1
assert len(os.sep) == 1
