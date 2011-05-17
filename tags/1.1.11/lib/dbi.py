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

import sys
import time
import types
import re
import compat
import MySQLdb

# set to 1 to store commit times in UTC, or 0 to use the ViewVC machine's
# local timezone. Using UTC is recommended because it ensures that the 
# database will remain valid even if it is moved to another machine or the host
# computer's time zone is changed. UTC also avoids the ambiguity associated
# with daylight saving time (for example if a computer in New York recorded the
# local time 2002/10/27 1:30 am, there would be no way to tell whether the
# actual time was recorded before or after clocks were rolled back). Use local
# times for compatibility with databases used by ViewCVS 0.92 and earlier 
# versions.
utc_time = 1

def DateTimeFromTicks(ticks):
  """Return a MySQL DATETIME value from a unix timestamp"""

  if utc_time:
    t = time.gmtime(ticks)
  else:
    t = time.localtime(ticks)
  return "%04d-%02d-%02d %02d:%02d:%02d" % t[:6]

_re_datetime = re.compile('([0-9]{4})-([0-9][0-9])-([0-9][0-9]) '
                          '([0-9][0-9]):([0-9][0-9]):([0-9][0-9])')

def TicksFromDateTime(datetime):
  """Return a unix timestamp from a MySQL DATETIME value"""

  if type(datetime) == types.StringType:
    # datetime is a MySQL DATETIME string
    matches = _re_datetime.match(datetime).groups()
    t = tuple(map(int, matches)) + (0, 0, 0)
  elif hasattr(datetime, "timetuple"):
    # datetime is a Python >=2.3 datetime.DateTime object
    t = datetime.timetuple()
  else:
    # datetime is an eGenix mx.DateTime object
    t = datetime.tuple()

  if utc_time:
    return compat.timegm(t)
  else:
    return time.mktime(t[:8] + (-1,))
    
def connect(host, port, user, passwd, db):
    return MySQLdb.connect(host=host, port=port, user=user, passwd=passwd, db=db)
