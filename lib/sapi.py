# generic server api - currently supports normal cgi, and active server pages
#
# Russ Yanofsky -- rey4@columbia.edu

import types
import string
import os
import sys

# global server object. It will be either a CgiServer or an AspServer,
# depending on the environment

server = None

class CgiServer:

  def __init__(self):
    self.inheritableOut = 1
    self.header_sent = 0
    self.pageGlobals = {}

    if os.environ.get('SERVER_SOFTWARE', '')[:13] == 'Microsoft-IIS':
      self.iis = 1
    else:
      self.iis = 0

    if sys.platform == "win32":
      import msvcrt
      msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

    global server
    server = self

    global cgi
    import cgi

  def header(self, content_type='text/html', status='200 OK'):
    if not self.header_sent:
      self.header_sent = 1
      sys.stdout.write('Status: %s\r\nContent-Type: %s\r\n\r\n'
                       % (status, content_type))

  def redirect(self, url):
    print 'Status: 301 Moved'
    if self.iis: url = IIS_FixURL(url)
    sys.stdout.write('Location: ' +  url + '\r\n\r\n')
    print 'This document is located <a href="%s">here</a>.' % url
    sys.exit(0)

  def params(self):
    return cgi.parse()

  def escape(self, s, quote = None):
    return cgi.escape(s, quote)

  def getenv(self, name, value=None):
    # If the viewcvs cgi's are in the /viewcvs/ folder on the web server and a
    # request looks like
    #
    #      /viewcvs/viewcvs.cgi/myproject/?someoption
    #
    # The CGI environment variables will look like this:
    #
    #      SCRIPT_NAME  =  /viewcvs/viewcvs.cgi
    #      PATH_INFO    =  /viewcvs/viewcvs.cgi/myproject/
    #
    # I'm not sure how these variables are supposed to work on a unix server,
    # but this next statement was needed in order to get existing script
    # to work properly on windows.

    if self.iis and name == 'PATH_INFO':
      return os.environ.get('PATH_INFO', '')[len(os.environ.get('SCRIPT_NAME', '')):]
    else:
      return os.environ.get(name, value)

  def FieldStorage(fp=None, headers=None, outerboundary="",
                 environ=os.environ, keep_blank_values=0, strict_parsing=0):
    return cgi.FieldStorage(fp, headers, outerboundary, environ,
      keep_blank_values, strict_parsing)

  def self(self):
    return self

  def getFile(self):
    return sys.stdout

  def close():
    pass

def IIS_FixURL(url):
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
    if os.environ['HTTPS'] == 'on':
      dport = "443"
      prefix = "https://"
    else:
      dport = "80"
      prefix = "http://"
    prefix = prefix + os.environ['HTTP_HOST']
    if os.environ['SERVER_PORT'] != dport:
      prefix = prefix + ":" + os.environ['SERVER_PORT']
    return prefix + url
  return url

class AspServer:

  def __init__(self, Server, Request, Response, Application):
    self.inheritableOut = 0
    self.header_sent = 0
    self.server = Server
    self.request = Request
    self.response = Response
    self.application = Application
    self.pageGlobals = {}

    global server
    if not isinstance(server, AspProxy):
      server = AspProxy()
    if not isinstance(sys.stdout, AspFile):
      sys.stdout = AspFile(server)

    server.registerThread(self)

  def escape(self, s, quote = None):
    return self.server.HTMLEncode(str(s))

  def params(self):
    p = {}
    for i in self.request.Form:
      p[str(i)] = map(str, self.request.Form[i])
    for i in self.request.QueryString:
      p[str(i)] = map(str, self.request.QueryString[i])
    return p

  def header(self, content_type='text/html', status='200 OK'):
    ### what to do with the status?

    # In normal circumstances setting self.response.ContentType
    # after headers have already been sent simply results in
    # an AttributeError exception, but sometimes it leads to
    # a fatal ASP error. For this reason I'm keeping
    # the self.header_sent member, and only checking for the
    # exception as a secondary measure
    if not self.header_sent:
      try:
        self.header_sent = 1
        self.response.ContentType = content_type
      except AttributeError:
        pass

  def redirect(self, url):
    self.response.Redirect(url)
    sys.exit()

  def getenv(self, name, value = None):
    if name == 'PATH_INFO':
      p = self.request.ServerVariables('PATH_INFO')()
      s = self.request.ServerVariables('SCRIPT_NAME')()
      return str(p[len(s):])
    else:
      r = self.request.ServerVariables(name)()
      if type(r) == types.UnicodeType:
        return str(r)
      else:
        return value

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

  def getFile(self):
    return AspFile(self)

  def close(self):
    server.unregisterThread()

class AspFile:
  def __init__(self, server):
    self.closed = 0
    self.mode = 'w'
    self.name = "<AspFile file>"
    self.softspace = 0
    self.server = server

  def flush(self):
    self.server.response.Flush()

  def write(self, s):
    t = type(s)
    if t is types.StringType:
      s = buffer(s)
    elif not t is types.BufferType:
      s = buffer(str(s))

    self.server.response.BinaryWrite(s)

  def writelines(self, list):
    for str in list:
      self.server.response.BinaryWrite(str)

  def truncate(self, size):
    pass

  def close(self):
    pass

class AspProxy:
  """In a multithreaded server environment, AspProxy stores the different server
  objects being used to display pages and transparently forwards access to them
  based on the current thread id."""

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

class ModPythonServer:
  def __init__(self, request):
    self.inheritableOut = 0
    self.request = request
    self.pageGlobals = {}

    global server
    if not isinstance(server, AspProxy):
      server = AspProxy()
    if not isinstance(sys.stdout, ModPythonFile):
      sys.stdout = ModPythonFile(server)

    server.registerThread(self)

    global cgi
    import cgi

  def escape(self, s, quote = None):
    return cgi.escape(s, quote)

  def params(self):
    import mod_python.util
    if self.request.args is None:
      return {}
    else:
      return mod_python.util.parse_qs(self.request.args)

  def header(self, content_type='text/html', status='200 OK'):
    ### what to do with the status?
    self.request.content_type = content_type

  def redirect(self, url):
    import mod_python.apache
    self.request.headers_out['Location'] = url
    self.request.status = mod_python.apache.HTTP_MOVED_TEMPORARILY
    self.request.write("You are being redirected to <a href=\"%s\">%s</a>"
      % (url, url))
    sys.exit()

  def getenv(self, name, value = None):
    try:
      return self.request.subprocess_env[name]
    except KeyError:
      return value

  def FieldStorage(self, fp=None, headers=None, outerboundary="",
                 environ=os.environ, keep_blank_values=0, strict_parsing=0):
    import mod_python.util
    return mod_python.util.FieldStorage(self.request, keep_blank_values, strict_parsing)

  def getFile(self):
    return ModPythonFile(self)

  def close(self, code = 0):
    server.unregisterThread()

class ModPythonFile:
  def __init__(self, server):
    import StringIO
    self.closed = 0
    self.mode = 'w'
    self.name = "<ModPythonFile file>"
    self.softspace = 0
    self.server = server

  def flush(self):
    pass

  def write(self, s):
    self.server.request.write(s)

  def writelines(self, ls):
    raise "not implemented"

  def truncate(self, size):
    pass

  def close(self):
    pass
