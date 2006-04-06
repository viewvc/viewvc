# -*- Mode: python -*-
#
# Copyright (C) 2000-2001 The ViewCVS Group. All Rights Reserved.
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
import MySQLdb


dbi_error = "dbi error"


## make some checks in MySQLdb
_no_datetime = """\
ERROR: Your version of MySQLdb requires the mxDateTime module
       for the Timestamp() and TimestampFromTicks() methods.
       You will need to install mxDateTime to use the ViewCVS
       database.
"""

if not hasattr(MySQLdb, "Timestamp") or \
   not hasattr(MySQLdb, "TimestampFromTicks"):
    sys.stderr.write(_no_datetime)
    sys.exit(1)


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


def Timestamp(year, month, date, hour, minute, second):
    return MySQLdb.Timestamp(year, month, date, hour, minute, second)


def TimestampFromTicks(ticks):
    return MySQLdb.TimestampFromTicks(ticks)


def connect(host, user, passwd, db):
    return Connection(host, user, passwd, db)
