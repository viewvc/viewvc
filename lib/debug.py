# -*-python-*-
#
# Copyright (C) 1999-2020 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

#
# Note: a t_start/t_end pair consumes about 0.00005 seconds on a P3/700.
#       the lambda form (when debugging is disabled) should be even faster.
#

import sys
from common import ViewVCException

# Set to non-zero to track and print processing times
SHOW_TIMES = 0

# Set to a server-side path to force the tarball view to generate the
# tarball as a file on the server, instead of transmitting the data
# back to the browser.  This enables easy display of error
# considitions in the browser, as well as tarball inspection on the
# server.  NOTE:  The file will be a TAR archive, *not* gzip-compressed.
TARFILE_PATH = ''


if SHOW_TIMES:

  import time

  _timers = { }
  _times = { }

  def t_start(which):
    _timers[which] = time.time()

  def t_end(which):
    t = time.time() - _timers[which]
    if which in _times:
      _times[which] = _times[which] + t
    else:
      _times[which] = t

  def t_dump(out):
    out.write('<div>')
    names = sorted(_times.keys())
    for name in names:
      out.write('%s: %.6fs<br/>\n' % (name, _times[name]))
    out.write('</div>')

else:

  t_start = t_end = t_dump = lambda *args: None


def PrintException(server, exc_data):
  status = exc_data['status']
  msg = exc_data['msg']
  tb = exc_data['stacktrace']

  server.header(status=status)
  server.write(b"<h3>An Exception Has Occurred</h3>\n")

  s = ''
  if msg:
    s = '<p><pre>%s</pre></p>' % server.escape(msg)
  if status:
    s = s + ('<h4>HTTP Response Status</h4>\n<p><pre>\n%s</pre></p><hr />\n'
             % status)
  s = s.encode('utf-8', 'xmlcharrefreplace')
  server.write(s)

  server.write(b"<h4>Python Traceback</h4>\n<p><pre>")
  server.write(server.escape(tb).encode('utf-8', 'xmlcharrefreplace'))
  server.write(b"</pre></p>\n")


def GetExceptionData():
  # capture the exception before doing anything else
  exc_type, exc, exc_tb = sys.exc_info()

  exc_dict = {
    'status' : None,
    'msg' : None,
    'stacktrace' : None,
    }

  try:
    import traceback

    if isinstance(exc, ViewVCException):
      exc_dict['msg'] = exc.msg
      exc_dict['status'] = exc.status

    # Build a string from the formatted exception, but skipping the
    # first line.
    formatted = traceback.format_exception(exc_type, exc, exc_tb)
    if exc_tb is not None:
      formatted = formatted[1:]
    exc_dict['stacktrace'] = ''.join(formatted)

  finally:
    # prevent circular reference. sys.exc_info documentation warns
    # "Assigning the traceback return value to a local variable in a function
    # that is handling an exception will cause a circular reference..."
    # This is all based on 'exc_tb', and we're now done with it. Toss it.
    del exc_tb

  return exc_dict
