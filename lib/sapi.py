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
# generic server api - currently supports normal cgi, mod_python, and
# active server pages
#
# -----------------------------------------------------------------------

import types
import os
import sys
import re
import cgi


# Global server object. It will be one of the following:
#   1. a CgiServer object
#   2. an WsgiServer object
#   3. a proxy to either an AspServer or a ModPythonServer object
server = None


# Simple HTML string escaping.  Note that we always escape the
# double-quote character -- ViewVC shouldn't ever need to preserve
# that character as-is, and sometimes needs to embed escaped values
# into HTML attributes.
def escape(s):
  s = str(s)
  s = s.replace('&', '&amp;')
  s = s.replace('>', '&gt;')
  s = s.replace('<', '&lt;')
  s = s.replace('"', "&quot;")
  return s


class ServerUsageError(Exception):
  """The caller attempted to start transmitting an HTTP response after
  that ship had already sailed."""
  pass


class ServerImplementationError(Exception):
  """There's a problem with the implementation of the Server."""
  pass


class ServerFile:
  """A file-like object which wraps a ViewVC server."""
  def __init__(self, server):
    self.closed = 0
    self.mode = 'w'
    self.name = "<ServerFile file>"
    self._server = server

  def readable(self):
    return False

  def writable(self):
    return True

  def seekable(self):
    return False

  def write(self, s):
    self._server.write(s)

  def writelines(self, list):
    for s in list:
      self._server.write(s)

  def flush(self):
    self._server.flush()

  def truncate(self, size):
    pass

  def close(self):
    pass


class Server:
  def __init__(self):
    """Initialized the server.  Child classes should extend this."""
    self._response_started = False

  def self(self):
    """Return a self-reference."""
    return self

  def response_started(self):
    """Return True iff a response has been started."""
    return self._response_started

  def start_response(self, content_type, status):
    """Start a response.  Child classes should extend this method."""
    if self._response_started:
      raise ServerUsageException()
    self._response_started = True

  def escape(self, s):
    """HTML-escape the Unicode string S and return the result."""
    return escape(s)

  def add_header(self, name, value):
    """Add an HTTP header to the set of those that will be included in
    the response.  Child classes should override this method."""
    raise ServerImplementationError()
    
  def redirect(self, url):
    """Respond to the request with a 301 redirect, asking the user
    agent to aim its requests instead at URL.  Child classes should
    override this method."""
    raise ServerImplementationError()

  def getenv(self, name, default_value=None):
    """Return the value of environment variable NAME, or DEFAULT_VALUE
    if NAME isn't found in the server environment.  Child classes should
    override this method."""
    raise ServerImplementationError()

  def params(self):
    """Return a dictionary of query parameters parsed from the
    server's request URL.  Class class should override this method."""
    raise ServerImplementationError()

  def write(self, s):
    """Write the Unicode string S to the server output stream.  Child
    classes should override this method."""
    raise ServerImplementationError()

  def flush(self):
    """Flush the server output stream.  Child classes should override
    this method."""
    raise ServerImplementationError()

  def file(self):
    """Return the server output stream as a File-like object that
    expects bytestring intput.  Child classes should override
    this method."""
    raise ServerImplementationError()


class ThreadedServerProxy:
  """In a multithreaded server environment, ThreadedServerProxy stores the
  different server objects being used to display pages and transparently
  forwards access to them based on the current thread id."""

  def __init__(self):
    self.__dict__['servers'] = { }
    global _thread
    import _thread

  def registerThread(self, server):
    self.__dict__['servers'][_thread.get_ident()] = server

  def unregisterThread(self):
    del self.__dict__['servers'][_thread.get_ident()]

  def self(self):
    return self.__dict__['servers'][_thread.get_ident()]

  def __getattr__(self, key):
    return getattr(self.self(), key)

  def __setattr__(self, key, value):
    setattr(self.self(), key, value)

  def __delattr__(self, key):
    delattr(self.self(), key)


class ThreadedServer(Server):
  """Threader server implementation."""

  def __init__(self):
    Server.__init__(self)
    global server
    if not isinstance(server, ThreadedServerProxy):
      server = ThreadedServerProxy()
    if not isinstance(sys.stdout, ServerFile):
      sys.stdout = ServerFile(server)
    server.registerThread(self)

  def file(self):
    return ServerFile(self)

  def close(self):
    server.unregisterThread()


class CgiServer(Server):
  """CGI server implementation."""

  def __init__(self):
    Server.__init__(self)
    self._headers = []
    self._iis = os.environ.get('SERVER_SOFTWARE', '')[:13] == 'Microsoft-IIS'
    global server
    server = self

  def add_header(self, name, value):
    self._headers.append((name, value))

  def start_response(self, content_type='text/html; charset=UTF-8', status=None):
    Server.start_response(self, content_type, status)

    extraheaders = ''
    for (name, value) in self._headers:
      extraheaders = extraheaders + '%s: %s\r\n' % (name, value)

    # The only way ViewVC pages and error messages are visible under
    # IIS is if a 200 error code is returned. Otherwise IIS instead
    # sends the static error page corresponding to the code number.
    if status is None or (status[:3] != '304' and self._iis):
      status = ''
    else:
      status = 'Status: %s\r\n' % status

    self.write_text('%sContent-Type: %s\r\n%s\r\n'
                    % (status, content_type, extraheaders))

  def redirect(self, url):
    if self._iis:
      url = fix_iis_url(self, url)
    self.add_header('Location', url)
    self.start_response(status='301 Moved')
    self.write_text(redirect_notice(url))

  def getenv(self, name, value=None):
    ret = os.environ.get(name, value)
    if self._iis and name == 'PATH_INFO' and ret:
      ret = fix_iis_path_info(self, ret)
    return ret

  def params(self):
    return cgi.parse()

  def write_text(self, s):
    sys.stdout.write(s)
    sys.stdout.flush()

  def write(self, s):
    sys.stdout.buffer.write(s)

  def flush(self):
    sys.stdout.buffer.flush()

  def file(self):
    return sys.stdout.buffer


class WsgiServer(Server):
  def __init__(self, environ, write_response):
    Server.__init__(self)
    self._environ = environ
    self._write_response = write_response;
    self._headers = []
    self._wsgi_write = None
    global server
    server = self

  def add_header(self, name, value):
    self._headers.append((name, value))

  def start_response(self, content_type='text/html; charset=UTF-8', status=None):
    Server.start_response(self, content_type, status)
    if not status:
      status = "200 OK"
    self._headers.insert(0, ("Content-Type", content_type),)
    self._wsgi_write = self._write_response(status, self._headers)

  def redirect(self, url):
    self.add_header('Location', url)
    self.start_response(status='301 Moved')
    self._wsgi_write(redirect_notice(url))

  def getenv(self, name, value=None):
    return self._environ.get(name, value)

  def params(self):
    return cgi.parse(environ=self._environ, fp=self._environ["wsgi.input"])

  def write(self, s):
    self._wsgi_write(s)

  def flush(self):
    pass

  def file(self):
    return ServerFile(self)

# Does ASP support Python >= 3.x ?
class AspServer(ThreadedServer):
  """ASP-based server."""

  def __init__(self, Server, Request, Response, Application):
    ThreadedServer.__init__(self)
    self._server = Server
    self._request = Request
    self._response = Response
    self._application = Application

  def add_header(self, name, value):
    self._response.AddHeader(name, value)

  def start_response(self, content_type='text/html; charset=UTF-8', status=None):
    ThreadedServer.start_response(self, content_type, status)
    self._response.ContentType = content_type
    if status is not None:
      self._response.Status = status

  def redirect(self, url):
    self._response.Redirect(url)

  def getenv(self, name, value = None):
    ret = self._request.ServerVariables(name)()
    if not type(ret) is types.UnicodeType:
      return value
    ret = str(ret)
    if name == 'PATH_INFO':
      ret = fix_iis_path_info(self, ret)
    return ret

  def params(self):
    d = {}
    for i in self._request.Form:
      d[str(i)] = list(map(str, self._request.Form[i]))
    for i in self._request.QueryString:
      d[str(i)] = list(map(str, self._request.QueryString[i]))
    return d

  def write(self, s):
    t = type(s)
    if t is types.StringType:
      s = buffer(s)
    elif not t is types.BufferType:
      s = buffer(str(s))
    self._response.BinaryWrite(s)

  def flush(self):
    self._response.Flush()


class ModPythonServer(ThreadedServer):
  """Server for use with mod_python under Apache HTTP Server."""

  def __init__(self, request):
    ThreadedServer.__init__(self)
    self._re_status = re.compile('\\d+')
    self._request = request
    self._request.add_cgi_vars()

  def add_header(self, name, value):
    self._request.headers_out.add(name, value)

  def start_response(self, content_type='text/html; charset=UTF-8', status=None):
    ThreadedServer.start_response(self, content_type, status)
    self._request.content_type = content_type
    if status is not None:
      m = self._re_status.match(status)
      if not m is None:
        self._request.status = int(m.group())

  def redirect(self, url):
    import mod_python.apache
    self._request.headers_out['Location'] = url
    self._request.status = mod_python.apache.HTTP_MOVED_TEMPORARILY
    self._request.write(redirect_notice(url))

  def getenv(self, name, value = None):
    try:
      return self._request.subprocess_env[name]
    except KeyError:
      return value

  def params(self):
    import mod_python.util
    if self._request.args is None:
      return {}
    else:
      return mod_python.util.parse_qs(self._request.args)

  def write(self, s):
    self._request.write(s)

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


def redirect_notice(url):
  return 'This document is located <a href="%s">here</a>.' % (url)
