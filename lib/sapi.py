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
#
# generic server api - currently supports normal cgi, mod_python, and
# active server pages
#
# -----------------------------------------------------------------------

import types
import string
import os
import sys
import re


# global server object. It will be either a CgiServer or a proxy to
# an AspServer or ModPythonServer object.
server = None


class Server:
  def __init__(self):
    self.pageGlobals = {}

  def self(self):
    return self

  def close(self):
    pass


class ThreadedServer(Server):
  def __init__(self):
    Server.__init__(self)

    self.inheritableOut = 0

    global server
    if not isinstance(server, ThreadedServerProxy):
      server = ThreadedServerProxy()
    if not isinstance(sys.stdout, File):
      sys.stdout = File(server)
    server.registerThread(self)

  def file(self):
    return File(self)

  def close(self):
    server.unregisterThread()


class ThreadedServerProxy:
  """In a multithreaded server environment, ThreadedServerProxy stores the
  different server objects being used to display pages and transparently
  forwards access to them based on the current thread id."""

  def __init__(self):
    self.__dict__['servers'] = { }
    global thread
    import thread

  def registerThread(self, server):
    self.__dict__['servers'][thread.get_ident()] = server

  def unregisterThread(self):
    del self.__dict__['servers'][thread.get_ident()]

  def self(self):
    """This function bypasses the getattr and setattr trickery and returns
    the actual server object."""
    return self.__dict__['servers'][thread.get_ident()]

  def __getattr__(self, key):
    return getattr(self.self(), key)

  def __setattr__(self, key, value):
    setattr(self.self(), key, value)

  def __delattr__(self, key):
    delattr(self.self(), key)


class File:
  def __init__(self, server):
    self.closed = 0
    self.mode = 'w'
    self.name = "<AspFile file>"
    self.softspace = 0
    self.server = server

  def write(self, s):
    self.server.write(s)

  def writelines(self, list):
    for s in list:
      self.server.write(s)

  def flush(self):
    self.server.flush()

  def truncate(self, size):
    pass

  def close(self):
    pass


class CgiServer(Server):
  def __init__(self, inheritableOut = 1):
    Server.__init__(self)
    self.headerSent = 0
    self.headers = []
    self.inheritableOut = inheritableOut
    self.iis = os.environ.get('SERVER_SOFTWARE', '')[:13] == 'Microsoft-IIS'

    if sys.platform == "win32" and inheritableOut:
      import msvcrt
      msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

    global server
    server = self

    global cgi
    import cgi

  def addheader(self, name, value):
    self.headers.append((name, value))

  def header(self, content_type='text/html; charset=UTF-8', status=None):
    if not self.headerSent:
      self.headerSent = 1

      extraheaders = ''
      for (name, value) in self.headers:
        extraheaders = extraheaders + '%s: %s\r\n' % (name, value)

      # The only way ViewVC pages and error messages are visible under 
      # IIS is if a 200 error code is returned. Otherwise IIS instead
      # sends the static error page corresponding to the code number.
      if status is None or (status[:3] != '304' and self.iis):
        status = ''
      else:
        status = 'Status: %s\r\n' % status

      sys.stdout.write('%sContent-Type: %s\r\n%s\r\n'
                       % (status, content_type, extraheaders))

  def redirect(self, url):
    if self.iis: url = fix_iis_url(self, url)
    self.addheader('Location', url)
    self.header(status='301 Moved')
    sys.stdout.write('This document is located <a href="%s">here</a>.\n' % url)

  def escape(self, s, quote = None):
    return cgi.escape(s, quote)

  def getenv(self, name, value=None):
    ret = os.environ.get(name, value)
    if self.iis and name == 'PATH_INFO' and ret:
      ret = fix_iis_path_info(self, ret)
    return ret

  def params(self):
    return cgi.parse()

  def FieldStorage(fp=None, headers=None, outerboundary="",
                 environ=os.environ, keep_blank_values=0, strict_parsing=0):
    return cgi.FieldStorage(fp, headers, outerboundary, environ,
      keep_blank_values, strict_parsing)

  def write(self, s):
    sys.stdout.write(s)

  def flush(self):
    sys.stdout.flush()

  def file(self):
    return sys.stdout


class AspServer(ThreadedServer):
  def __init__(self, Server, Request, Response, Application):
    ThreadedServer.__init__(self)
    self.headerSent = 0
    self.server = Server
    self.request = Request
    self.response = Response
    self.application = Application

  def addheader(self, name, value):
    self.response.AddHeader(name, value)

  def header(self, content_type=None, status=None):
    # Normally, setting self.response.ContentType after headers have already
    # been sent simply results in an AttributeError exception, but sometimes
    # it leads to a fatal ASP error. For this reason I'm keeping the
    # self.headerSent member and only checking for the exception as a
    # secondary measure
    if not self.headerSent:
      try:
        self.headerSent = 1
        if content_type is None:
          self.response.ContentType = 'text/html; charset=UTF-8'
        else:
          self.response.ContentType = content_type
        if status is not None: self.response.Status = status
      except AttributeError:
        pass

  def redirect(self, url):
    self.response.Redirect(url)

  def escape(self, s, quote = None):
    return self.server.HTMLEncode(str(s))

  def getenv(self, name, value = None):
    ret = self.request.ServerVariables(name)()
    if not type(ret) is types.UnicodeType:
      return value
    ret = str(ret)
    if name == 'PATH_INFO':
      ret = fix_iis_path_info(self, ret)
    return ret

  def params(self):
    p = {}
    for i in self.request.Form:
      p[str(i)] = map(str, self.request.Form[i])
    for i in self.request.QueryString:
      p[str(i)] = map(str, self.request.QueryString[i])
    return p

  def FieldStorage(self, fp=None, headers=None, outerboundary="",
                 environ=os.environ, keep_blank_values=0, strict_parsing=0):

    # Code based on a very helpful usenet post by "Max M" (maxm@mxm.dk)
    # Subject "Re: Help! IIS and Python"
    # http://groups.google.com/groups?selm=3C7C0AB6.2090307%40mxm.dk

    from StringIO import StringIO
    from cgi import FieldStorage

    environ = {}
    for i in self.request.ServerVariables:
      environ[str(i)] = str(self.request.ServerVariables(i)())

    # this would be bad for uploaded files, could use a lot of memory
    binaryContent, size = self.request.BinaryRead(int(environ['CONTENT_LENGTH']))

    fp = StringIO(str(binaryContent))
    fs = FieldStorage(fp, None, "", environ, keep_blank_values, strict_parsing)
    fp.close()
    return fs

  def write(self, s):
    t = type(s)
    if t is types.StringType:
      s = buffer(s)
    elif not t is types.BufferType:
      s = buffer(str(s))

    self.response.BinaryWrite(s)

  def flush(self):
    self.response.Flush()


_re_status = re.compile("\\d+")


class ModPythonServer(ThreadedServer):
  def __init__(self, request):
    ThreadedServer.__init__(self)
    self.request = request
    self.headerSent = 0
    
    global cgi
    import cgi

  def addheader(self, name, value):
    self.request.headers_out.add(name, value)

  def header(self, content_type=None, status=None):
    if content_type is None: 
      self.request.content_type = 'text/html; charset=UTF-8'
    else:
      self.request.content_type = content_type
    self.headerSent = 1

    if status is not None:
      m = _re_status.match(status)
      if not m is None:
        self.request.status = int(m.group())

  def redirect(self, url):
    import mod_python.apache
    self.request.headers_out['Location'] = url
    self.request.status = mod_python.apache.HTTP_MOVED_TEMPORARILY
    self.request.write("You are being redirected to <a href=\"%s\">%s</a>"
                       % (url, url))

  def escape(self, s, quote = None):
    return cgi.escape(s, quote)

  def getenv(self, name, value = None):
    try:
      return self.request.subprocess_env[name]
    except KeyError:
      return value

  def params(self):
    import mod_python.util
    if self.request.args is None:
      return {}
    else:
      return mod_python.util.parse_qs(self.request.args)

  def FieldStorage(self, fp=None, headers=None, outerboundary="",
                 environ=os.environ, keep_blank_values=0, strict_parsing=0):
    import mod_python.util
    return mod_python.util.FieldStorage(self.request, keep_blank_values, strict_parsing)

  def write(self, s):
    self.request.write(s)

  def flush(self):
    pass


def fix_iis_url(server, url):
  """When a CGI application under IIS outputs a "Location" header with a url
  beginning with a forward slash, IIS tries to optimise the redirect by not
  returning any output from the original CGI script at all and instead just
  returning the new page in its place. Because of this, the browser does
  not know it is getting a different page than it requested. As a result,
  The address bar that appears in the browser window shows the wrong location
  and if the new page is in a different folder than the old one, any relative
  links on it will be broken.

  This function can be used to circumvent the IIS "optimization" of local
  redirects. If it is passed a location that begins with a forward slash it
  will return a URL constructed with the information in CGI environment.
  If it is passed a URL or any location that doens't begin with a forward slash
  it will return just argument unaltered.
  """
  if url[0] == '/':
    if server.getenv('HTTPS') == 'on':
      dport = "443"
      prefix = "https://"
    else:
      dport = "80"
      prefix = "http://"
    prefix = prefix + server.getenv('HTTP_HOST')
    if server.getenv('SERVER_PORT') != dport:
      prefix = prefix + ":" + server.getenv('SERVER_PORT')
    return prefix + url
  return url


def fix_iis_path_info(server, path_info):
  """Fix the PATH_INFO value in IIS"""
  # If the viewvc cgi's are in the /viewvc/ folder on the web server and a
  # request looks like
  #
  #      /viewvc/viewvc.cgi/myproject/?someoption
  #
  # The CGI environment variables on IIS will look like this:
  #
  #      SCRIPT_NAME  =  /viewvc/viewvc.cgi
  #      PATH_INFO    =  /viewvc/viewvc.cgi/myproject/
  #
  # Whereas on Apache they look like:
  #
  #      SCRIPT_NAME  =  /viewvc/viewvc.cgi
  #      PATH_INFO    =  /myproject/
  #
  # This function converts the IIS PATH_INFO into the nonredundant form
  # expected by ViewVC
  return path_info[len(server.getenv('SCRIPT_NAME', '')):]
