# -*-python-*-
#
# Copyright (C) 1999-2018 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

"""commonly used functions and classes for Version Control lib driver
for accessible Subversion repositories, using swib Python bindig for
Subversion.
"""

from svn import core

### Require Subversion 1.3.1 or better.
if (core.SVN_VER_MAJOR, core.SVN_VER_MINOR, core.SVN_VER_PATCH) < (1, 3, 1):
  raise Exception, "Version requirement not met (needs 1.3.1 or better)"

### Pre-1.5 SubversionException's might not have the .msg and .apr_err members
def _fix_subversion_exception(e):
  if not hasattr(e, 'apr_err'):
    e.apr_err = e[1]
  if not hasattr(e, 'message'):
    e.message = e[0]


def _rev2optrev(rev):
  assert isinstance(rev, (int, long))
  rt = core.svn_opt_revision_t()
  rt.kind = core.svn_opt_revision_number
  rt.value.number = rev
  return rt


# Given a dictionary REVPROPS of revision properties, pull special
# ones out of them and return a 4-tuple containing the log message,
# the author, the date (converted from the date string property), and
# a dictionary of any/all other revprops.
def _split_revprops(revprops):
  if not revprops:
    return None, None, None, {}
  special_props = []
  for prop in core.SVN_PROP_REVISION_LOG, \
              core.SVN_PROP_REVISION_AUTHOR, \
              core.SVN_PROP_REVISION_DATE:
    if revprops.has_key(prop):
      special_props.append(revprops[prop])
      del(revprops[prop])
    else:
      special_props.append(None)
  msg, author, datestr = tuple(special_props)
  date = _datestr_to_date(datestr)
  return msg, author, date, revprops


def _datestr_to_date(datestr):
  try:
    return core.svn_time_from_cstring(datestr) // 1000000
  except:
    return None

