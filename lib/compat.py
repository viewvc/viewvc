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
# compat.py: compatibility functions for operation across Python 1.5.x to 2.2.x
#
# -----------------------------------------------------------------------
#

import urllib
import string
import time
import re
import os


#
# urllib.urlencode() is new to Python 1.5.2
#
try:
  urlencode = urllib.urlencode
except AttributeError:
  def urlencode(dict):
    "Encode a dictionary as application/x-url-form-encoded."
    if not dict:
      return ''
    quote = urllib.quote_plus
    keyvalue = [ ]
    for key, value in dict.items():
      keyvalue.append(quote(key) + '=' + quote(str(value)))
    return string.join(keyvalue, '&')

#
# time.strptime() is new to Python 1.5.2
#
if hasattr(time, 'strptime'):
  def cvs_strptime(timestr):
    'Parse a CVS-style date/time value.'
    return time.strptime(timestr, '%Y/%m/%d %H:%M:%S')
else:
  _re_rev_date = re.compile('([0-9]{4})/([0-9][0-9])/([0-9][0-9]) '
                            '([0-9][0-9]):([0-9][0-9]):([0-9][0-9])')
  def cvs_strptime(timestr):
    'Parse a CVS-style date/time value.'
    matches = _re_rev_date.match(timestr).groups()
    return tuple(map(int, matches)) + (0, 1, 0)

#
# os.makedirs() is new to Python 1.5.2
#
try:
  makedirs = os.makedirs
except AttributeError:
  def makedirs(path, mode=0777):
    head, tail = os.path.split(path)
    if head and tail and not os.path.exists(head):
      makedirs(head, mode)
    os.mkdir(path, mode)

# 
# the following stuff is *ONLY* needed for standalone.py.
# For that reason I've encapsulated it into a function.
#

def for_standalone():
  import SocketServer
  if not hasattr(SocketServer.TCPServer, "close_request"):
    #
    # method close_request() was missing until Python 2.1
    #
    class TCPServer(SocketServer.TCPServer):
      def process_request(self, request, client_address):
        """Call finish_request.

        Overridden by ForkingMixIn and ThreadingMixIn.

        """
        self.finish_request(request, client_address)
        self.close_request(request)

      def close_request(self, request):
        """Called to clean up an individual request."""
        request.close()

    SocketServer.TCPServer = TCPServer
