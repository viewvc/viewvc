#!/usr/bin/env python
# -*-python-*-
#
# Copyright (C) 1999-2009 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# This program originally written by Peter Funk <pf@artcom-gmbh.de>, with
# contributions by Ka-Ping Yee.
#
# -----------------------------------------------------------------------

#
# INSTALL-TIME CONFIGURATION
#
# These values will be set during the installation process. During
# development, they will remain None.
#

LIBRARY_DIR = None
CONF_PATHNAME = None

import sys
import os
import os.path
import stat
import string
import urllib
import rfc822
import socket
import select
import base64
import crypt
import BaseHTTPServer

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)
else:
  sys.path.insert(0, os.path.abspath(os.path.join(sys.argv[0], "../../lib")))

import sapi
import viewvc


class Options:
  port = 49152      # default TCP/IP port used for the server
  daemon = 0        # stay in the foreground by default
  repositories = {} # use default repositories specified in config
  host = sys.platform == 'mac' and '127.0.0.1' or 'localhost'
  script_alias = 'viewvc'
  config_file = None
  htpasswd_file = None


class StandaloneServer(sapi.CgiServer):
  """Custom sapi interface that uses a BaseHTTPRequestHandler HANDLER
  to generate output."""
  
  def __init__(self, handler):
    sapi.CgiServer.__init__(self, inheritableOut = sys.platform != "win32")
    self.handler = handler

  def header(self, content_type='text/html', status=None):
    if not self.headerSent:
      self.headerSent = 1
      if status is None:
        statusCode = 200
        statusText = 'OK'       
      else:        
        p = status.find(' ')
        if p < 0:
          statusCode = int(status)
          statusText = ''
        else:
          statusCode = int(status[:p])
          statusText = status[p+1:]
      self.handler.send_response(statusCode, statusText)
      self.handler.send_header("Content-type", content_type)
      for (name, value) in self.headers:
        self.handler.send_header(name, value)
      self.handler.end_headers()


class NotViewVCLocationException(Exception):
  """The request location was not aimed at ViewVC."""
  pass


class AuthenticationException(Exception):
  """Authentication requirements have not been met."""
  pass


class ViewVCHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
  """Custom HTTP request handler for ViewVC."""
  
  def do_GET(self):
    """Serve a GET request."""
    self.handle_request('GET')

  def do_POST(self):
    """Serve a POST request."""
    self.handle_request('POST')

  def handle_request(self, method):
    """Handle a request of type METHOD."""
    try:
      self.run_viewvc()
    except NotViewVCLocationException:
      # If the request was aimed at the server root, but there's a
      # non-empty script_alias, automatically redirect to the
      # script_alias.  Otherwise, just return a 404 and shrug.
      if (not self.path or self.path == "/") and options.script_alias:
        new_url = self.server.url + options.script_alias + '/'
        self.send_response(301, "Moved Permanently")
        self.send_header("Content-type", "text/html")
        self.send_header("Location", new_url)
        self.end_headers()
        self.wfile.write("""<html>
<head>
<meta http-equiv="refresh" content="10; url=%s" />
<title>Moved Temporarily</title>
</head>
<body>
<h1>Redirecting to ViewVC</h1>
<p>You will be automatically redirected to <a href="%s">ViewVC</a>.
   If this doesn't work, please click on the link above.</p>
</body>
</html>
""" % (new_url, new_url))
      else:
        self.send_error(404)
    except IOError: # ignore IOError: [Errno 32] Broken pipe
      pass
    except AuthenticationException:
      self.send_response(401, "Unauthorized")
      self.send_header("WWW-Authenticate", 'Basic realm="ViewVC"')
      self.send_header("Content-type", "text/html")
      self.end_headers()
      self.wfile.write("""<html>
<head>
<title>Authentication failed</title>
</head>
<body>
<h1>Authentication failed</h1>
<p>Authentication has failed.  Please retry with the correct username
   and password.</p>
</body>
</html>""")
      
  def is_viewvc(self):
    """Check whether self.path is, or is a child of, the ScriptAlias"""
    if not options.script_alias:
      return 1
    if self.path == '/' + options.script_alias:
      return 1
    alias_len = len(options.script_alias)
    if self.path[:alias_len+2] == '/' + options.script_alias + '/':
      return 1
    if self.path[:alias_len+2] == '/' + options.script_alias + '?':
      return 1
    return 0

  def validate_password(self, htpasswd_file, username, password):
    """Compare USERNAME and PASSWORD against HTPASSWD_FILE."""
    try:
      lines = open(htpasswd_file, 'r').readlines()
      for line in lines:
        file_user, file_pass = line.rstrip().split(':', 1)
        if username == file_user:
          return file_pass == crypt.crypt(password, file_pass[:2])
    except:
      pass
    return False
    
  def run_viewvc(self):
    """Run ViewVC to field a single request."""

    ### Much of this is adapter from Python's standard library
    ### module CGIHTTPServer.

    # Is this request even aimed at ViewVC?  If not, complain.
    if not self.is_viewvc():
      raise NotViewVCLocationException()

    # If htpasswd authentication is enabled, try to authenticate the user.
    self.username = None
    if options.htpasswd_file:
      authn = self.headers.get('authorization')
      if not authn:
        raise AuthenticationException()
      try:
        kind, data = authn.split(' ', 1)
        if kind == 'Basic':
          data = base64.b64decode(data)
          username, password = data.split(':', 1)
      except:
        raise AuthenticationException()
      if not self.validate_password(options.htpasswd_file, username, password):
        raise AuthenticationException()
      self.username = username

    # Setup the environment in preparation of executing ViewVC's core code.
    env = os.environ  
    
    scriptname = options.script_alias and '/' + options.script_alias or ''

    viewvc_url = self.server.url[:-1] + scriptname
    rest = self.path[len(scriptname):]
    i = rest.rfind('?')
    if i >= 0:
      rest, query = rest[:i], rest[i+1:]
    else:
      query = ''

    # Since we're going to modify the env in the parent, provide empty
    # values to override previously set values
    for k in env.keys():
      if k[:5] == 'HTTP_':
        del env[k]
    for k in ('QUERY_STRING', 'REMOTE_HOST', 'CONTENT_LENGTH',
              'HTTP_USER_AGENT', 'HTTP_COOKIE'):
      if env.has_key(k): 
        env[k] = ""

    # XXX Much of the following could be prepared ahead of time!
    env['SERVER_SOFTWARE'] = self.version_string()
    env['SERVER_NAME'] = self.server.server_name
    env['GATEWAY_INTERFACE'] = 'CGI/1.1'
    env['SERVER_PROTOCOL'] = self.protocol_version
    env['SERVER_PORT'] = str(self.server.server_port)
    env['REQUEST_METHOD'] = self.command
    uqrest = urllib.unquote(rest)
    env['PATH_INFO'] = uqrest
    env['SCRIPT_NAME'] = scriptname
    if query:
      env['QUERY_STRING'] = query
    env['HTTP_HOST'] = self.server.address[0]
    host = self.address_string()
    if host != self.client_address[0]:
      env['REMOTE_HOST'] = host
    env['REMOTE_ADDR'] = self.client_address[0]
    if self.username:
      env['REMOTE_USER'] = self.username
    if self.headers.typeheader is None:
      env['CONTENT_TYPE'] = self.headers.type
    else:
      env['CONTENT_TYPE'] = self.headers.typeheader
    length = self.headers.getheader('content-length')
    if length:
      env['CONTENT_LENGTH'] = length
    accept = []
    for line in self.headers.getallmatchingheaders('accept'):
      if line[:1] in string.whitespace:
        accept.append(line.strip())
      else:
        accept = accept + line[7:].split(',')
    env['HTTP_ACCEPT'] = ','.join(accept)
    ua = self.headers.getheader('user-agent')
    if ua:
      env['HTTP_USER_AGENT'] = ua
    modified = self.headers.getheader('if-modified-since')
    if modified:
      env['HTTP_IF_MODIFIED_SINCE'] = modified
    etag = self.headers.getheader('if-none-match')
    if etag:
      env['HTTP_IF_NONE_MATCH'] = etag
    # AUTH_TYPE
    # REMOTE_IDENT
    # XXX Other HTTP_* headers
      
    # Preserve state, because we execute script in current process:
    save_argv = sys.argv
    save_stdin = sys.stdin
    save_stdout = sys.stdout
    save_stderr = sys.stderr
    # For external tools like enscript we also need to redirect
    # the real stdout file descriptor.
    #
    # FIXME:  This code used to carry the following comment:
    #
    #   (On windows, reassigning the sys.stdout variable is sufficient
    #   because pipe_cmds makes it the standard output for child
    #   processes.)
    #
    # But we no longer use pipe_cmds.  So at the very least, the
    # comment is stale.  Is the code okay, though?
    if sys.platform != "win32":
      save_realstdout = os.dup(1) 
    try:
      try:
        sys.stdout = self.wfile
        if sys.platform != "win32":
          os.dup2(self.wfile.fileno(), 1)
        sys.stdin = self.rfile
        viewvc.main(StandaloneServer(self), cfg)
      finally:
        sys.argv = save_argv
        sys.stdin = save_stdin
        sys.stdout.flush()
        if sys.platform != "win32":
          os.dup2(save_realstdout, 1)
          os.close(save_realstdout)
        sys.stdout = save_stdout
        sys.stderr = save_stderr
    except SystemExit, status:
      self.log_error("ViewVC exit status %s", str(status))
    else:
      self.log_error("ViewVC exited ok")


class ViewVCHTTPServer(BaseHTTPServer.HTTPServer):
  """Customized HTTP server for ViewVC."""
  
  def __init__(self, host, port, callback):
    self.address = (host, port)
    self.url = 'http://%s:%d/' % (host, port)
    self.callback = callback
    BaseHTTPServer.HTTPServer.__init__(self, self.address, self.handler)

  def serve_until_quit(self):
    self.quit = 0
    while not self.quit:
      rd, wr, ex = select.select([self.socket.fileno()], [], [], 1)
      if rd:
        self.handle_request()

  def server_activate(self):
    BaseHTTPServer.HTTPServer.server_activate(self)
    if self.callback:
      self.callback(self)

  def server_bind(self):
    # set SO_REUSEADDR (if available on this platform)
    if hasattr(socket, 'SOL_SOCKET') and hasattr(socket, 'SO_REUSEADDR'):
      self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    BaseHTTPServer.HTTPServer.server_bind(self)


def serve(host, port, callback=None):
  """Start an HTTP server for HOST on PORT.  Call CALLBACK function
  when the server is ready to serve."""

  ViewVCHTTPServer.handler = ViewVCHTTPRequestHandler

  try:
    # XXX Move this code out of this function.
    # Early loading of configuration here.  Used to allow tinkering
    # with some configuration settings:
    handle_config(options.config_file)
    if options.repositories:
      cfg.general.default_root = "Development"
      for repo_name in options.repositories.keys():
        repo_path = os.path.normpath(options.repositories[repo_name])
        if os.path.exists(os.path.join(repo_path, "CVSROOT", "config")):
          cfg.general.cvs_roots[repo_name] = repo_path
        elif os.path.exists(os.path.join(repo_path, "format")):
          cfg.general.svn_roots[repo_name] = repo_path
    elif cfg.general.cvs_roots.has_key("Development") and \
         not os.path.isdir(cfg.general.cvs_roots["Development"]):
      sys.stderr.write("*** No repository found. Please use the -r option.\n")
      sys.stderr.write("   Use --help for more info.\n")
      raise KeyboardInterrupt # Hack!
    os.close(0) # To avoid problems with shell job control

    # always use default docroot location
    cfg.options.docroot = None

    # if cvsnt isn't found, fall back to rcs
    if (cfg.conf_path is None and cfg.utilities.cvsnt):
      import popen
      cvsnt_works = 0
      try:
        fp = popen.popen(cfg.utilities.cvsnt, ['--version'], 'rt')
        try:
          while 1:
            line = fp.readline()
            if not line:
              break
            if line.find("Concurrent Versions System (CVSNT)") >= 0:
              cvsnt_works = 1
              while fp.read(4096):
                pass
              break
        finally:
          fp.close()
      except:
        pass
      if not cvsnt_works:
        cfg.utilities.cvsnt = None

    ViewVCHTTPServer(host, port, callback).serve_until_quit()
  except (KeyboardInterrupt, select.error):
    pass
  print 'server stopped'


def handle_config(config_file):
  global cfg
  cfg = viewvc.load_config(config_file or CONF_PATHNAME)


def main(argv):
  """Command-line interface (looks at argv to decide what to do)."""
  import getopt
  class BadUsage(Exception): pass

  try:
    opts, args = getopt.getopt(argv[1:], 'dc:p:r:h:s:', 
                               ['daemon', 'config-file=', 'host=',
                                'port=', 'repository=', 'script-alias=',
                                'htpasswd-file='])
    for opt, val in opts:
      if opt in ('-r', '--repository'):
        if options.repositories: # option may be used more than once:
          num = len(options.repositories.keys())+1
          symbolic_name = "Repository"+str(num)
          options.repositories[symbolic_name] = val
        else:
          options.repositories["Development"] = val
      elif opt in ('-d', '--daemon'):
        options.daemon = 1
      elif opt in ('-p', '--port'):
        try:
          options.port = int(val)
        except ValueError:
          raise BadUsage, "Port '%s' is not a valid port number" % (val)
      elif opt in ('-h', '--host'):
        options.host = val
      elif opt in ('-s', '--script-alias'):
        options.script_alias = '/'.join(filter(None, val.split('/')))
      elif opt in ('-c', '--config-file'):
        if not os.path.isfile(val):
          raise BadUsage, "'%s' does not appear to be a valid " \
                          "configuration file." % (val)
        options.config_file = val
      elif opt in ('-c', '--htpasswd-file'):
        if not os.path.isfile(val):
          raise BadUsage, "'%s' does not appear to be a valid " \
                          "htpasswd file." % (val)
        options.htpasswd_file = val
        
    if not options.port:
      raise BadUsage, "You must supply a valid port."
    
    if options.daemon:
      pid = os.fork()
      if pid != 0:
        sys.exit()
        
    def ready(server):
      print 'server ready at %s%s' % (server.url, options.script_alias)
    serve(options.host, options.port, ready)
    return
  except (getopt.error, BadUsage), err:
    cmd = os.path.basename(sys.argv[0])
    port = options.port
    host = options.host
    script_alias = options.script_alias
    if str(err):
      sys.stderr.write("ERROR: %s\n\n" % (str(err)))
    sys.stderr.write("""Usage: %(cmd)s [OPTIONS]

Run a simple, standalone HTTP server configured to serve up ViewVC
requests.

Options:

  --config-file=PATH (-c)    Use the file at PATH as the ViewVC configuration
                             file.  If not specified, ViewVC will try to use
                             the configuration file in its installation tree;
                             otherwise, built-in default values are used.
                             
  --daemon (-d)              Background the server process.
  
  --host=HOST (-h)           Start the server listening on HOST.  You need
                             to provide the hostname if you want to
                             access the standalone server from a remote
                             machine.  [default: %(host)s]

  --port=PORT (-p)           Start the server on the given PORT.
                             [default: %(port)d]

  --repository=PATH (-r)     Serve up the Subversion or CVS repository located
                             at PATH.  This option may be used more than once.

  --script-alias=PATH (-s)   Specify the ScriptAlias, the artificial path
                             location that at which ViewVC appears to be
                             located.  For example, if your ScriptAlias is
                             "cgi-bin/viewvc", then ViewVC will be accessible
                             at "http://%(host)s:%(port)s/cgi-bin/viewvc".
                             [default: %(script_alias)s]

  --htpasswd-file=FILE       Demand authentication from clients, validating
                             authentication credentials against Apache
                             htpasswd file FILE.
""" % locals())

if __name__ == '__main__':
  options = Options()
  main(sys.argv)
