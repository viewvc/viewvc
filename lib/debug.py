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
  import sys, traceback, string, sapi
  out, server = sys.stdout, sapi.server.self()
  out.write("<hr><p><font color=red>%s</font></p>\n<p><pre>" % text)
  out.write(server.escape(string.join(traceback.format_stack(), '')))
  out.write("</pre></p>")
  out.flush()

def PrintException():
  import sys, traceback, string, sapi
  out, server = sys.stdout, sapi.server.self()
  
  server.header()  
  out.write("<h3>Exception</h3>\n")
  info = sys.exc_info()
  
  # put message in a prominent position (rather than 
  # at the end of the stack trace)
  if isinstance(info[1], ViewcvsException):
    out.write("<h4>ViewCVS Messages:</h4>\n%s\n" % info[1].description)
  
  stacktrace = string.join(apply(traceback.format_exception, info), '')
  
  out.write("<h4>Python Messages:</h4>\n<p><pre>")
  out.write(server.escape(stacktrace))
  out.write("</pre></p>\n")
  
  del info

if SHOW_CHILD_PROCESSES:
  class Process:
    def __init__(self, command, inStream, outStream, errStream):
      self.command = command
      self.debugIn = inStream
      self.debugOut = outStream
      self.debugErr = errStream

      import sapi
      if not sapi.server is None:
        if not sapi.server.pageGlobals.has_key('processes'):
          sapi.server.pageGlobals['processes'] = [self]
        else:
          sapi.server.pageGlobals['processes'].append(self)

  def DumpChildren():
    import sapi, sys, os
    out, server = sys.stdout, sapi.server.self()

    if not 'processes' in server.pageGlobals:
      return
    
    server.header()
    lastOut = None
    i = 0

    for k in server.pageGlobals['processes']:
      i += 1
      out.write("<table border=1>\n")
      out.write("<tr><td colspan=2>Child Process%i</td></tr>" % i)
      out.write("<tr>\n  <td valign=top>Command Line</td>  <td><pre>")
      out.write(server.escape(k.command))
      out.write("</pre></td>\n</tr>\n")
      out.write("<tr>\n  <td valign=top>Standard In:</td>  <td>")

      if k.debugIn is lastOut and not lastOut is None:
        out.write("<i>Output from process %i</i>" % (i - 1))
      elif k.debugIn:
        out.write("<pre>")
        out.write(server.escape(k.debugIn.getvalue()))
        out.write("</pre>")
        
      out.write("</td>\n</tr>\n")
      
      if k.debugOut is k.debugErr:
        out.write("<tr>\n  <td valign=top>Standard Out & Error:</td>  <td><pre>")
        if k.debugOut:
          out.write(server.escape(k.debugOut.getvalue()))
        out.write("</pre></td>\n</tr>\n")
        
      else:
        out.write("<tr>\n  <td valign=top>Standard Out:</td>  <td><pre>")
        if k.debugOut:
          out.write(server.escape(k.debugOut.getvalue()))
        out.write("</pre></td>\n</tr>\n")
        out.write("<tr>\n  <td valign=top>Standard Error:</td>  <td><pre>")
        if k.debugErr:
          out.write(server.escape(k.debugErr.getvalue()))
        out.write("</pre></td>\n</tr>\n")

      out.write("</table>\n")
      out.flush()
      lastOut = k.debugOut

    out.write("<table border=1>\n")
    out.write("<tr><td colspan=2>Environment Variables</td></tr>")
    for k, v in os.environ.items():
      out.write("<tr>\n  <td valign=top><pre>")
      out.write(server.escape(k))
      out.write("</pre></td>\n  <td valign=top><pre>")
      out.write(server.escape(v))
      out.write("</pre></td>\n</tr>")
    out.write("</table>")
         
else:

  def DumpChildren():
    pass
    
