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
# Note: a t_start/t_end pair consumes about 0.00005 seconds on a P3/700.
#       the lambda form (when debugging is disabled) should be even faster.
#

SHOW_TIMES = 0
SHOW_CHILD_PROCESSES = 0

if SHOW_TIMES:

  import time

  _timers = { }
  _times = { }

  def t_start(which):
    _timers[which] = time.time()

  def t_end(which):
    t = time.time() - _timers[which]
    if _times.has_key(which):
      _times[which] = _times[which] + t
    else:
      _times[which] = t

  def dump():
    for name, value in _times.items():
      print '%s: %.6f<br>' % (name, value)

else:

  t_start = t_end = dump = lambda *args: None

class ViewcvsException:
  def __init__(self, msg, httpCode = None):
    self.msg = msg
    self.httpCode = httpCode
    s = "<p><pre>"
    s += self.msg
    s += "</pre></p>\n"

    if self.httpCode:
      s += "<h4>HTTP-like status code:</h4>\n<p><pre>\n"
      s += self.httpCode
      s += "</pre></p><hr>\n"
    
    self.description = s

  def __str__(self):
    return "ViewCVS Unrecoverable Error"

def PrintStackTrace(text = ""):
  import sys
  import traceback
  import string
  import sapi

  print "<hr><p><font color=red>", text, "</font></p>\n<p><pre>"
  print sapi.server.escape(string.join(traceback.format_stack(), ''))
  print "</pre></p>"
  sys.stdout.flush()

def PrintException():
  import sys
  import traceback
  import string
  import sapi
  
  sapi.server.header()  
  print "<h3>Exception</h3>"
  info = sys.exc_info()
  
  # put message in a more prominent position (rather than at the end of the stack trace)
  if isinstance(info[1], ViewcvsException):
    print "<h4>ViewCVS Messages:</h4>"
    print info[1].description
  
  print "<h4>Python Messages:</h4>\n<p><pre>"
  print sapi.server.escape(string.join(apply(traceback.format_exception, info), ''))
  print "</pre></p>"
  del info

if SHOW_CHILD_PROCESSES:
  class Process:
    def __init__(self, command, inStream, outStream, errStream):
      self.command = command
      self.debugIn = inStream
      self.debugOut = outStream
      self.debugErr = errStream

      import sapi
      if not sapi.server.pageGlobals.has_key('processes'):
        sapi.server.pageGlobals['processes'] = [self]
      else:
        sapi.server.pageGlobals['processes'].append(self)

    def printInfo(self):
      print "Command Line", command

  def DumpChildren():
    import sapi, sys
    server = sapi.server.self()

    if not server.pageGlobals.has_key('processes'):
      return
    
    server.header()    
    lastOut = None
    i = 0

    for k in server.pageGlobals['processes']:
      i += 1
      print "<div align=center>Child Process", i, "</div>"
      print "<table border=1>"
      sys.stdout.write("<tr>\n  <td valign=top>Command Line</td>  <td><pre>")
      sys.stdout.write(server.escape(k.command))
      sys.stdout.write("</pre></td>\n</tr>\n")
      sys.stdout.write("<tr>\n  <td valign=top>Standard In:</td>  <td>")
      if k.debugIn is lastOut and not (lastOut is None):
        sys.stdout.write("<i>Output from process %i</i>" % (i - 1))
      elif k.debugIn:
        sys.stdout.write("<pre>")
        sys.stdout.write(server.escape(k.debugIn.getvalue()))
        sys.stdout.write("</pre>")
      sys.stdout.write("</td>\n</tr>\n")
      
      if k.debugOut is k.debugErr:
        sys.stdout.write("<tr>\n  <td valign=top>Standard Out & Error:</td>  <td><pre>")
        if k.debugOut:
          sys.stdout.write(server.escape(k.debugOut.getvalue()))
        sys.stdout.write("</pre></td>\n</tr>\n")
      else:
        sys.stdout.write("<tr>\n  <td valign=top>Standard Out:</td>  <td><pre>")
        if k.debugOut:
          sys.stdout.write(server.escape(k.debugOut.getvalue()))
        sys.stdout.write("</pre></td>\n</tr>\n")
        sys.stdout.write("<tr>\n  <td valign=top>Standard Error:</td>  <td><pre>")
        if k.debugErr:
          sys.stdout.write(server.escape(k.debugErr.getvalue()))
        sys.stdout.write("</pre></td>\n</tr>\n")

      sys.stdout.write("</table>\n")
      lastOut = k.debugOut
else:

  def DumpChildren():
    pass
    
