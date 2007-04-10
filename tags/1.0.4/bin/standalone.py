#!/usr/bin/env python
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

"""Run "standalone.py -p <port>" to start an HTTP server on a given port 
on the local machine to generate ViewVC web pages.
"""

__author__ = "Peter Funk <pf@artcom-gmbh.de>"
__date__ = "11 November 2001"
__version__ = "$Revision$"
__credits__ = """Guido van Rossum, for an excellent programming language.
Greg Stein, for writing ViewCVS in the first place.
Ka-Ping Yee, for the GUI code and the framework stolen from pydoc.py.
"""

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
import BaseHTTPServer

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)
else:
  sys.path.insert(0, os.path.abspath(os.path.join(sys.argv[0], "../../lib")))

import sapi
import viewvc
import compat; compat.for_standalone()


class Options:
    port = 7467 # default TCP/IP port used for the server
    start_gui = 0 # No GUI unless requested.
    repositories = {} # use default repositories specified in config
    if sys.platform == 'mac':
        host = '127.0.0.1' 
    else:
        host = 'localhost'
    script_alias = 'viewvc'

# --- web browser interface: ----------------------------------------------

class StandaloneServer(sapi.CgiServer):
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
              p = string.find(status, ' ')
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
            

def serve(host, port, callback=None):
    """start a HTTP server on the given port.  call 'callback' when the
    server is ready to serve"""

    class ViewVC_Handler(BaseHTTPServer.BaseHTTPRequestHandler):
         
        def do_GET(self):
            """Serve a GET request."""
            if not self.path or self.path == "/":
                self.redirect()
            elif self.is_viewvc():
                try:
                    self.run_viewvc()
                except IOError:
                    # ignore IOError: [Errno 32] Broken pipe
                    pass
            else:
                self.send_error(404)

        def do_POST(self):
            """Serve a POST request."""
            if self.is_viewvc():
                self.run_viewvc()
            else:
                self.send_error(501, "Can only POST to %s"
                                % (options.script_alias))

        def is_viewvc(self):
            """Check whether self.path is, or is a child of, the ScriptAlias"""
            if self.path == '/' + options.script_alias:
                return 1
            if self.path[:len(options.script_alias)+2] == \
                   '/' + options.script_alias + '/':
                return 1
            if self.path[:len(options.script_alias)+2] == \
                   '/' + options.script_alias + '?':
                return 1
            return 0

        def redirect(self):
            """redirect the browser to the viewvc URL"""
            new_url = self.server.url + options.script_alias + '/'
            self.send_response(301, "Moved (redirection follows)")
            self.send_header("Content-type", "text/html")
            self.send_header("Location", new_url)
            self.end_headers()
            self.wfile.write("""<html>
<head>
<meta http-equiv="refresh" content="1; URL=%s">
</head>
<body>
<h1>Redirection to <a href="%s">ViewVC</a></h1>
Wait a second.   You will be automatically redirected to <b>ViewVC</b>.
If this doesn't work, please click on the link above.
</body>
</html>
""" % tuple([new_url]*2))

        def run_viewvc(self):
            """This is a quick and dirty cut'n'rape from Python's 
            standard library module CGIHTTPServer."""
            scriptname = '/' + options.script_alias
            assert string.find(self.path, scriptname) == 0
            viewvc_url = self.server.url[:-1] + scriptname
            rest = self.path[len(scriptname):]
            i = string.rfind(rest, '?')
            if i >= 0:
                rest, query = rest[:i], rest[i+1:]
            else:
                query = ''
            # sys.stderr.write("Debug: '"+scriptname+"' '"+rest+"' '"+query+"'\n")
            env = os.environ
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
            # AUTH_TYPE
            # REMOTE_USER
            # REMOTE_IDENT
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
                    accept.append(string.strip(line))
                else:
                    accept = accept + string.split(line[7:], ',')
            env['HTTP_ACCEPT'] = string.joinfields(accept, ',')
            ua = self.headers.getheader('user-agent')
            if ua:
                env['HTTP_USER_AGENT'] = ua
            modified = self.headers.getheader('if-modified-since')
            if modified:
                env['HTTP_IF_MODIFIED_SINCE'] = modified
            etag = self.headers.getheader('if-none-match')
            if etag:
                env['HTTP_IF_NONE_MATCH'] = etag
            # XXX Other HTTP_* headers
            decoded_query = string.replace(query, '+', ' ')

            # Preserve state, because we execute script in current process:
            save_argv = sys.argv
            save_stdin = sys.stdin
            save_stdout = sys.stdout
            save_stderr = sys.stderr
            # For external tools like enscript we also need to redirect
            # the real stdout file descriptor. (On windows, reassigning the
            # sys.stdout variable is sufficient because pipe_cmds makes it
            # the standard output for child processes.)
            if sys.platform != "win32": save_realstdout = os.dup(1) 
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

    class ViewVC_Server(BaseHTTPServer.HTTPServer):
        def __init__(self, host, port, callback):
            self.address = (host, port)
            self.url = 'http://%s:%d/' % (host, port)
            self.callback = callback
            BaseHTTPServer.HTTPServer.__init__(self, self.address,
                                               self.handler)

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
            if hasattr(socket, 'SOL_SOCKET') \
               and hasattr(socket, 'SO_REUSEADDR'):
                self.socket.setsockopt(socket.SOL_SOCKET,
                                       socket.SO_REUSEADDR, 1)
            BaseHTTPServer.HTTPServer.server_bind(self)

    ViewVC_Server.handler = ViewVC_Handler

    try:
        # XXX Move this code out of this function.
        # Early loading of configuration here.  Used to
        # allow tinkering with some configuration settings:
        handle_config()
        if options.repositories:
            cfg.general.default_root = "Development"
            cfg.general.cvs_roots.update(options.repositories)
        elif cfg.general.cvs_roots.has_key("Development") and \
             not os.path.isdir(cfg.general.cvs_roots["Development"]):
            sys.stderr.write("*** No repository found. Please use the -r option.\n")
            sys.stderr.write("   Use --help for more info.\n")
            raise KeyboardInterrupt # Hack!
        os.close(0) # To avoid problems with shell job control

        # always use default docroot location
        cfg.options.docroot = None

        # if cvsnt isn't found, fall back to rcs
        if (cfg.conf_path is None
            and cfg.general.cvsnt_exe_path):
          import popen
          cvsnt_works = 0
          try:
            fp = popen.popen(cfg.general.cvsnt_exe_path, ['--version'], 'rt')
            try:
              while 1:
                line = fp.readline()
                if not line: break
                if string.find(line, "Concurrent Versions System (CVSNT)")>=0:
                  cvsnt_works = 1
                  while fp.read(4096):
                    pass
                  break
            finally:
              fp.close()
          except:
            pass
          if not cvsnt_works:
            cfg.cvsnt_exe_path = None

        ViewVC_Server(host, port, callback).serve_until_quit()
    except (KeyboardInterrupt, select.error):
        pass
    print 'server stopped'

def handle_config():
  global cfg
  cfg = viewvc.load_config(CONF_PATHNAME)

# --- graphical interface: --------------------------------------------------

def nogui(missing_module):
    sys.stderr.write(
        "Sorry! Your Python was compiled without the %s module"%missing_module+
        " enabled.\nI'm unable to run the GUI part.  Please omit the '-g'\n"+
        "and '--gui' options or install another Python interpreter.\n")
    raise SystemExit, 1

def gui(host, port):
    """Graphical interface (starts web server and pops up a control window)."""
    class GUI:
        def __init__(self, window, host, port):
            self.window = window
            self.server = None
            self.scanner = None

            try:
                import Tkinter
            except ImportError:
                nogui("Tkinter")

            self.server_frm = Tkinter.Frame(window)
            self.title_lbl = Tkinter.Label(self.server_frm,
                text='Starting server...\n ')
            self.open_btn = Tkinter.Button(self.server_frm,
                text='open browser', command=self.open, state='disabled')
            self.quit_btn = Tkinter.Button(self.server_frm,
                text='quit serving', command=self.quit, state='disabled')


            self.window.title('ViewVC standalone')
            self.window.protocol('WM_DELETE_WINDOW', self.quit)
            self.title_lbl.pack(side='top', fill='x')
            self.open_btn.pack(side='left', fill='x', expand=1)
            self.quit_btn.pack(side='right', fill='x', expand=1)

            # Early loading of configuration here.  Used to
            # allow tinkering with configuration settings through the gui:
            handle_config()
            if not LIBRARY_DIR:
                cfg.options.cvsgraph_conf = "../cgi/cvsgraph.conf.dist"

            self.options_frm = Tkinter.Frame(window)

            # cvsgraph toggle:
            self.cvsgraph_ivar = Tkinter.IntVar()
            self.cvsgraph_ivar.set(cfg.options.use_cvsgraph)
            self.cvsgraph_toggle = Tkinter.Checkbutton(self.options_frm,
                text="enable cvsgraph (needs binary)", var=self.cvsgraph_ivar,
                command=self.toggle_use_cvsgraph)
            self.cvsgraph_toggle.pack(side='top', anchor='w')

            # enscript toggle:
            self.enscript_ivar = Tkinter.IntVar()
            self.enscript_ivar.set(cfg.options.use_enscript)
            self.enscript_toggle = Tkinter.Checkbutton(self.options_frm,
                text="enable enscript (needs binary)", var=self.enscript_ivar,
                command=self.toggle_use_enscript)
            self.enscript_toggle.pack(side='top', anchor='w')

            # show_subdir_lastmod toggle:
            self.subdirmod_ivar = Tkinter.IntVar()
            self.subdirmod_ivar.set(cfg.options.show_subdir_lastmod)
            self.subdirmod_toggle = Tkinter.Checkbutton(self.options_frm,
                text="show subdir last mod (dir view)", var=self.subdirmod_ivar,
                command=self.toggle_subdirmod)
            self.subdirmod_toggle.pack(side='top', anchor='w')

            # use_re_search toggle:
            self.useresearch_ivar = Tkinter.IntVar()
            self.useresearch_ivar.set(cfg.options.use_re_search)
            self.useresearch_toggle = Tkinter.Checkbutton(self.options_frm,
                text="allow regular expr search", var=self.useresearch_ivar,
                command=self.toggle_useresearch)
            self.useresearch_toggle.pack(side='top', anchor='w')

            # use_localtime toggle:
            self.use_localtime_ivar = Tkinter.IntVar()
            self.use_localtime_ivar.set(cfg.options.use_localtime)
            self.use_localtime_toggle = Tkinter.Checkbutton(self.options_frm,
                text="use localtime (instead of UTC)", 
                var=self.use_localtime_ivar,
                command=self.toggle_use_localtime)
            self.use_localtime_toggle.pack(side='top', anchor='w')

            # use_pagesize integer var:
            self.usepagesize_lbl = Tkinter.Label(self.options_frm,
                text='Paging (number of items per page, 0 disables):')
            self.usepagesize_lbl.pack(side='top', anchor='w')
            self.use_pagesize_ivar = Tkinter.IntVar()
            self.use_pagesize_ivar.set(cfg.options.use_pagesize)
            self.use_pagesize_entry = Tkinter.Entry(self.options_frm,
                width=10, textvariable=self.use_pagesize_ivar)
            self.use_pagesize_entry.bind('<Return>', self.set_use_pagesize)
            self.use_pagesize_entry.pack(side='top', anchor='w')

            # directory view template:
            self.dirtemplate_lbl = Tkinter.Label(self.options_frm,
                text='Chooose HTML Template for the Directory pages:')
            self.dirtemplate_lbl.pack(side='top', anchor='w')
            self.dirtemplate_svar = Tkinter.StringVar()
            self.dirtemplate_svar.set(cfg.templates.directory)
            self.dirtemplate_entry = Tkinter.Entry(self.options_frm,
                width = 40, textvariable=self.dirtemplate_svar)
            self.dirtemplate_entry.bind('<Return>', self.set_templates_directory)
            self.dirtemplate_entry.pack(side='top', anchor='w')
            self.templates_dir = Tkinter.Radiobutton(self.options_frm,
                text="directory.ezt", value="templates/directory.ezt", 
                var=self.dirtemplate_svar, command=self.set_templates_directory)
            self.templates_dir.pack(side='top', anchor='w')
            self.templates_dir_alt = Tkinter.Radiobutton(self.options_frm,
                text="dir_alternate.ezt", value="templates/dir_alternate.ezt", 
                var=self.dirtemplate_svar, command=self.set_templates_directory)
            self.templates_dir_alt.pack(side='top', anchor='w')

            # log view template:
            self.logtemplate_lbl = Tkinter.Label(self.options_frm,
                text='Chooose HTML Template for the Log pages:')
            self.logtemplate_lbl.pack(side='top', anchor='w')
            self.logtemplate_svar = Tkinter.StringVar()
            self.logtemplate_svar.set(cfg.templates.log)
            self.logtemplate_entry = Tkinter.Entry(self.options_frm,
                width = 40, textvariable=self.logtemplate_svar)
            self.logtemplate_entry.bind('<Return>', self.set_templates_log)
            self.logtemplate_entry.pack(side='top', anchor='w')
            self.templates_log = Tkinter.Radiobutton(self.options_frm,
                text="log.ezt", value="templates/log.ezt", 
                var=self.logtemplate_svar, command=self.set_templates_log)
            self.templates_log.pack(side='top', anchor='w')
            self.templates_log_table = Tkinter.Radiobutton(self.options_frm,
                text="log_table.ezt", value="templates/log_table.ezt", 
                var=self.logtemplate_svar, command=self.set_templates_log)
            self.templates_log_table.pack(side='top', anchor='w')

            # query view template:
            self.querytemplate_lbl = Tkinter.Label(self.options_frm,
                text='Template for the database query page:')
            self.querytemplate_lbl.pack(side='top', anchor='w')
            self.querytemplate_svar = Tkinter.StringVar()
            self.querytemplate_svar.set(cfg.templates.query)
            self.querytemplate_entry = Tkinter.Entry(self.options_frm,
                width = 40, textvariable=self.querytemplate_svar)
            self.querytemplate_entry.bind('<Return>', self.set_templates_query)
            self.querytemplate_entry.pack(side='top', anchor='w')
            self.templates_query = Tkinter.Radiobutton(self.options_frm,
                text="query.ezt", value="templates/query.ezt", 
                var=self.querytemplate_svar, command=self.set_templates_query)
            self.templates_query.pack(side='top', anchor='w')

            # pack and set window manager hints:
            self.server_frm.pack(side='top', fill='x')
            self.options_frm.pack(side='top', fill='x')

            self.window.update()
            self.minwidth = self.window.winfo_width()
            self.minheight = self.window.winfo_height()
            self.expanded = 0
            self.window.wm_geometry('%dx%d' % (self.minwidth, self.minheight))
            self.window.wm_minsize(self.minwidth, self.minheight)

            try:
                import threading
            except ImportError:
                nogui("thread")
            threading.Thread(target=serve, 
                             args=(host, port, self.ready)).start()

        def toggle_use_cvsgraph(self, event=None):
            cfg.options.use_cvsgraph = self.cvsgraph_ivar.get()

        def toggle_use_enscript(self, event=None):
            cfg.options.use_enscript = self.enscript_ivar.get()

        def toggle_use_localtime(self, event=None):
            cfg.options.use_localtime = self.use_localtime_ivar.get()

        def toggle_subdirmod(self, event=None):
            cfg.options.show_subdir_lastmod = self.subdirmod_ivar.get()

        def toggle_useresearch(self, event=None):
            cfg.options.use_re_search = self.useresearch_ivar.get()

        def set_use_pagesize(self, event=None):
            cfg.options.use_pagesize = self.use_pagesize_ivar.get()

        def set_templates_log(self, event=None):
            cfg.templates.log = self.logtemplate_svar.get()

        def set_templates_directory(self, event=None):
            cfg.templates.directory = self.dirtemplate_svar.get()

        def set_templates_query(self, event=None):
            cfg.templates.query = self.querytemplate_svar.get()

        def ready(self, server):
            """used as callback parameter to the serve() function"""
            self.server = server
            self.title_lbl.config(
                text='ViewVC standalone server at\n' + server.url)
            self.open_btn.config(state='normal')
            self.quit_btn.config(state='normal')

        def open(self, event=None, url=None):
            """opens a browser window on the local machine"""
            url = url or self.server.url
            try:
                import webbrowser
                webbrowser.open(url)
            except ImportError: # pre-webbrowser.py compatibility
                if sys.platform == 'win32':
                    os.system('start "%s"' % url)
                elif sys.platform == 'mac':
                    try:
                        import ic
                        ic.launchurl(url)
                    except ImportError: pass
                else:
                    rc = os.system('netscape -remote "openURL(%s)" &' % url)
                    if rc: os.system('netscape "%s" &' % url)

        def quit(self, event=None):
            if self.server:
                self.server.quit = 1
            self.window.quit()

    import Tkinter
    try:
        gui = GUI(Tkinter.Tk(), host, port)
        Tkinter.mainloop()
    except KeyboardInterrupt:
        pass

# --- command-line interface: ----------------------------------------------

def cli(argv):
    """Command-line interface (looks at argv to decide what to do)."""
    import getopt
    class BadUsage(Exception): pass

    try:
        opts, args = getopt.getopt(argv[1:], 'gp:r:h:s:', 
            ['gui', 'port=', 'repository=', 'script-alias='])
        for opt, val in opts:
            if opt in ('-g', '--gui'):
                options.start_gui = 1
            elif opt in ('-r', '--repository'):
                if options.repositories: # option may be used more than once:
                    num = len(options.repositories.keys())+1
                    symbolic_name = "Repository"+str(num)
                    options.repositories[symbolic_name] = val
                else:
                    options.repositories["Development"] = val
            elif opt in ('-p', '--port'):
                try:
                    options.port = int(val)
                except ValueError:
                    raise BadUsage
            elif opt in ('-h', '--host'):
                options.host = val
            elif opt in ('-s', '--script-alias'):
                options.script_alias = \
                    string.join(filter(None, string.split(val, '/')), '/')
        if options.start_gui:
            gui(options.host, options.port)
            return
        elif options.port:
            def ready(server):
                print 'server ready at %s%s' % (server.url,
                                                options.script_alias)
            serve(options.host, options.port, ready)
            return
        raise BadUsage
    except (getopt.error, BadUsage):
        cmd = os.path.basename(sys.argv[0])
        port = options.port
        host = options.host
        script_alias = options.script_alias
        print """ViewVC standalone - a simple standalone HTTP-Server

Usage: %(cmd)s [OPTIONS]

Available Options:

-h <host>, --host=<host>:
    Start the HTTP server listening on <host>.  You need to provide
    the hostname if you want to access the standalone server from a
    remote machine.  [default: %(host)s]

-p <port>, --port=<port>:
    Start an HTTP server on the given port.  [default: %(port)d]

-r <path>, --repository=<path>:
    Specify a path for a CVS repository.  Repository definitions are
    typically read from the viewvc.conf file, if available.  This
    option may be used more than once.

-s <path>, --script-alias=<path>:
    Specify the ScriptAlias, the artificial path location that at
    which ViewVC appears to be located.  For example, if your
    ScriptAlias is "cgi-bin/viewvc", then ViewVC will appear to be
    accessible at the URL "http://%(host)s:%(port)s/cgi-bin/viewvc".
    [default: %(script_alias)s]
    
-g, --gui:
    Pop up a graphical interface for serving and testing ViewVC.
    NOTE: this requires a valid X11 display connection.
""" % locals()

if __name__ == '__main__':
    options = Options()
    cli(sys.argv)
