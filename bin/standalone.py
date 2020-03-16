#!/usr/bin/env python
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
import socket
import select
import base64
if sys.version_info[0] >= 3:
  PY3 = True
  from urllib.parse import unquote as _unquote
  import http.server as _http_server
else:
  PY3 = False
  from urllib import unquote as _unquote
  import BaseHTTPServer as _http_server

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)
else:
  sys.path.insert(0, os.path.abspath(os.path.join(sys.argv[0], "../../lib")))

import sapi
import viewvc


# The 'crypt' module is only available on Unix platforms.  We'll try
# to use 'fcrypt' if it's available (for more information, see
# http://carey.geek.nz/code/python-fcrypt/).
has_crypt = False
try:
  import crypt
  has_crypt = True
  def _check_passwd(user_passwd, real_passwd):
    return real_passwd == crypt.crypt(user_passwd, real_passwd[:2])
except ImportError:
  try:
    import fcrypt
    has_crypt = True
    def _check_passwd(user_passwd, real_passwd):
      return real_passwd == fcrypt.crypt(user_passwd, real_passwd[:2])
  except ImportError:
    def _check_passwd(user_passwd, real_passwd):
      return False


class Options:
  port = 49152      # default TCP/IP port used for the server
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


class ViewVCHTTPRequestHandler(_http_server.BaseHTTPRequestHandler):
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
          return _check_passwd(password, file_pass)
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
      if k in env:
        env[k] = ""

    # XXX Much of the following could be prepared ahead of time!
    env['SERVER_SOFTWARE'] = self.version_string()
    env['SERVER_NAME'] = self.server.server_name
    env['GATEWAY_INTERFACE'] = 'CGI/1.1'
    env['SERVER_PROTOCOL'] = self.protocol_version
    env['SERVER_PORT'] = str(self.server.server_port)
    env['REQUEST_METHOD'] = self.command
    uqrest = _unquote(rest)
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
    if PY3:
        env['CONTENT_TYPE'] = self.headers.get_content_type()
        length = self.headers.get('content-length', None)
    else:
      if self.headers.typeheader is None:
        env['CONTENT_TYPE'] = self.headers.type
      else:
        env['CONTENT_TYPE'] = self.headers.typeheader
      length = self.headers.get('content-length', None)
    if length:
      env['CONTENT_LENGTH'] = length
    accept = []
    for line in self.headers.getallmatchingheaders('accept'):
      if line[:1] in string.whitespace:
        accept.append(line.strip())
      else:
        accept = accept + line[7:].split(',')
    env['HTTP_ACCEPT'] = ','.join(accept)
    if PY3:
      ua = self.headers.get('user-agent', None)
    else:
      ua = self.headers.getheader('user-agent')
    if ua:
      env['HTTP_USER_AGENT'] = ua
    if PY3:
      modified = self.headers.get('if-modified-since', None)
    else:
      modified = self.headers.getheader('if-modified-since')
    if modified:
      env['HTTP_IF_MODIFIED_SINCE'] = modified
    if PY3:
      etag = self.headers.get('if-none-match', None)
    else:
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
        sys.argv = []
        sys.stdout = self.wfile
        if sys.platform != "win32":
          os.dup2(self.wfile.fileno(), 1)
        sys.stdin = self.rfile
        viewvc.main(StandaloneServer(self), cfg)
      finally:
        sys.argv = save_argv
        sys.stdin = save_stdin
        sys.stdout.closed or sys.stdout.flush()
        if sys.platform != "win32":
          os.dup2(save_realstdout, 1)
          os.close(save_realstdout)
        sys.stdout = save_stdout
        sys.stderr = save_stderr
    except SystemExit as status:
      self.log_error("ViewVC exit status %s", str(status))
    else:
      self.log_error("ViewVC exited ok")


class ViewVCHTTPServer(_http_server.HTTPServer):
  """Customized HTTP server for ViewVC."""

  def __init__(self, host, port, callback):
    self.address = (host, port)
    self.url = 'http://%s:%d/' % (host, port)
    self.callback = callback
    _http_server.HTTPServer.__init__(self, self.address, self.handler)

  def serve_until_quit(self):
    self.quit = 0
    while not self.quit:
      rd, wr, ex = select.select([self.socket.fileno()], [], [], 1)
      if rd:
        self.handle_request()

  def server_activate(self):
    _http_server.HTTPServer.server_activate(self)
    if self.callback:
      self.callback(self)

  def server_bind(self):
    # set SO_REUSEADDR (if available on this platform)
    if hasattr(socket, 'SOL_SOCKET') and hasattr(socket, 'SO_REUSEADDR'):
      self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _http_server.HTTPServer.server_bind(self)

  def handle_error(self, request, client_address):
    """Handle an error gracefully. use stderr instead of stdout
    to avoid double fault.
    """
    sys.stderr.write('-'*40 + '\n')
    sys.stderr.write('Exception happened during processing of request from '
                     '%s\n' % str(client_address))
    import traceback
    traceback.print_exc()
    sys.stderr.write('-'*40 + '\n')


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
    elif "Development" in cfg.general.cvs_roots and \
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
  print('server stopped')


def handle_config(config_file):
  global cfg
  cfg = viewvc.load_config(config_file or CONF_PATHNAME)


def usage():
  clean_options = Options()
  cmd = os.path.basename(sys.argv[0])
  port = clean_options.port
  host = clean_options.host
  script_alias = clean_options.script_alias
  sys.stderr.write("""Usage: %(cmd)s [OPTIONS]

Run a simple, standalone HTTP server configured to serve up ViewVC requests.

Options:

  --config-file=FILE (-c)    Read configuration options from FILE.  If not
                             specified, ViewVC will look for a configuration
                             file in its installation tree, falling back to
                             built-in default values.

  --daemon (-d)              Background the server process.

  --help                     Show this usage message and exit.

  --host=HOSTNAME (-h)       Listen on HOSTNAME.  Required for access from a
                             remote machine.  [default: %(host)s]

  --htpasswd-file=FILE       Authenticate incoming requests, validating against
                             against FILE, which is an Apache HTTP Server
                             htpasswd file.  (CRYPT only; no DIGEST support.)

  --port=PORT (-p)           Listen on PORT.  [default: %(port)d]

  --repository=PATH (-r)     Serve the Subversion or CVS repository located
                             at PATH.  This option may be used more than once.

  --script-alias=PATH (-s)   Use PATH as the virtual script location (similar
                             to Apache HTTP Server's ScriptAlias directive).
                             For example, "--script-alias=repo/view" will serve
                             ViewVC at "http://HOSTNAME:PORT/repo/view".
                             [default: %(script_alias)s]
""" % locals())
  sys.exit(0)


def badusage(errstr):
  cmd = os.path.basename(sys.argv[0])
  sys.stderr.write("ERROR: %s\n\n"
                   "Try '%s --help' for detailed usage information.\n"
                   % (errstr, cmd))
  sys.exit(1)


def main(argv):
  """Command-line interface (looks at argv to decide what to do)."""
  import getopt

  short_opts = ''.join(['c:',
                        'd',
                        'h:',
                        'p:',
                        'r:',
                        's:',
                        ])
  long_opts = ['daemon',
               'config-file=',
               'help',
               'host=',
               'htpasswd-file=',
               'port=',
               'repository=',
               'script-alias=',
               ]

  opt_daemon = False
  opt_host = None
  opt_port = None
  opt_htpasswd_file = None
  opt_config_file = None
  opt_script_alias = None
  opt_repositories = []

  # Parse command-line options.
  try:
    opts, args = getopt.getopt(argv[1:], short_opts, long_opts)
    for opt, val in opts:
      if opt in ['--help']:
        usage()
      elif opt in ['-r', '--repository']: # may be used more than once
        opt_repositories.append(val)
      elif opt in ['-d', '--daemon']:
        opt_daemon = 1
      elif opt in ['-p', '--port']:
        opt_port = val
      elif opt in ['-h', '--host']:
        opt_host = val
      elif opt in ['-s', '--script-alias']:
        opt_script_alias = val
      elif opt in ['-c', '--config-file']:
        opt_config_file = val
      elif opt in ['--htpasswd-file']:
        opt_htpasswd_file = val
  except getopt.error as err:
    badusage(str(err))

  # Validate options that need validating.
  class BadUsage(Exception): pass
  try:
    if opt_port is not None:
      try:
        options.port = int(opt_port)
      except ValueError:
        raise BadUsage("Port '%s' is not a valid port number" % (opt_port))
      if not options.port:
        raise BadUsage("You must supply a valid port.")
    if opt_htpasswd_file is not None:
      if not os.path.isfile(opt_htpasswd_file):
        raise BadUsage("'%s' does not appear to be a valid htpasswd file."
                       % (opt_htpasswd_file))
      if not has_crypt:
        raise BadUsage("Unable to locate suitable `crypt' module for use "
                       "with --htpasswd-file option.  If your Python "
                       "distribution does not include this module (as is "
                       "the case on many non-Unix platforms), consider "
                       "installing the `fcrypt' module instead (see "
                       "http://carey.geek.nz/code/python-fcrypt/).")
      options.htpasswd_file = opt_htpasswd_file
    if opt_config_file is not None:
      if not os.path.isfile(opt_config_file):
        raise BadUsage("'%s' does not appear to be a valid configuration file."
                       % (opt_config_file))
      options.config_file = opt_config_file
    if opt_host is not None:
      options.host = opt_host
    if opt_script_alias is not None:
      options.script_alias = '/'.join(filter(None, opt_script_alias.split('/')))
    for repository in opt_repositories:
      if 'Development' not in options.repositories:
        rootname = 'Development'
      else:
        rootname = 'Repository%d' % (len(options.repositories.keys()) + 1)
      options.repositories[rootname] = repository
  except BadUsage as err:
    badusage(str(err))

  # Fork if we're in daemon mode.
  if opt_daemon:
    pid = os.fork()
    if pid != 0:
      sys.exit()

  # Finaly, start the server.
  def ready(server):
    print('server ready at %s%s' % (server.url, options.script_alias))
  serve(options.host, options.port, ready)


if __name__ == '__main__':
  options = Options()
  main(sys.argv)
