# -*- Mode: python -*-
#
# Copyright (C) 2000-2002 The ViewCVS Group. All Rights Reserved.
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

import sys
import time
import types
import re
import compat
import MySQLdb

# set to 1 to store commit times in UTC, or 0 to use the ViewCVS machine's
# local timezone. Using UTC is recommended because it ensures that the 
# database will remain valid even if it is moved to another machine or the host
# computer's time zone is changed. UTC also avoids the ambiguity associated
# with daylight saving time (for example if a computer in New York recorded the
# local time 2002/10/27 1:30 am, there would be no way to tell whether the
# actual time was recorded before or after clocks were rolled back). Use local
# times for compatibility with databases used by ViewCVS 0.92 and earlier 
# versions.
dbi_utc_time = 1

class Cursor:
    def __init__(self, mysql_cursor):
        self.__cursor = mysql_cursor

    def execute(self, *args):
        apply(self.__cursor.execute, args)

    def fetchone(self):
        try:
            row = self.__cursor.fetchone()
        except IndexError:
            row = None
        
        return row
    

class Connection:
    def __init__(self, host, user, passwd, db):
        self.__mysql = MySQLdb.connect(
            host=host, user=user, passwd=passwd, db=db)

    def cursor(self):
        return Cursor(self.__mysql.cursor())

def DateTimeFromTicks(ticks):
  """Return a MySQL DATETIME value from a unix timestamp"""

  if dbi_utc_time:
    t = time.gmtime(ticks)
  else:
    t = time.localtime(ticks)
  return "%04d-%02d-%02d %02d:%02d:%02d" % t[:6]

_re_datetime = re.compile('([0-9]{4})-([0-9][0-9])-([0-9][0-9]) '
                          '([0-9][0-9]):([0-9][0-9]):([0-9][0-9])')

def TicksFromDateTime(datetime):
  """Return a unix timestamp from a MySQL DATETIME value"""

  if type(datetime) == types.StringType:
    matches = _re_datetime.match(datetime).groups()
    t = tuple(map(int, matches)) + (0, 0, 0)
  else: # datetime is an mx.DateTime object
    t = datetime.tuple()

  if dbi_utc_time:
    return compat.timegm(t)
  else:
    return time.mktime(t[:8] + (-1,))
    
def connect(host, user, passwd, db):
    return Connection(host, user, passwd, db)
