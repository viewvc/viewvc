#!/usr/bin/env python
# $Id$
# vim:sw=4:ts=4:et:nowrap
# [Emacs: -*- python -*-]
#
# Copyright (C) 1999-2001 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://viewcvs.sourceforge.net/license-1.html.
#
# Contact information:
#   This file: Peter Funk, Oldenburger Str.86, 27777 Ganderkesee, Germany
#   ViewCVS project: Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewcvs.sourceforge.net/
#
# Note: this module is designed to deploy instantly and run under any
# version of Python from 1.5 and up.  That's why some 2.0 features 
# (like string methods) are conspicuously avoided.

# XXX Security issues?

"""Run "standalone.py -p <port>" to start an HTTP server on a given port 
on the local machine to generate ViewCVS web pages.
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
# This value will be set during the installation process. During
# development, it will remain None.
#

LIBRARY_DIR = None

import sys
import os
import string
import urllib
import socket
import select
import BaseHTTPServer

class Options:
    port = 7467 # default TCP/IP port used for the server
    start_gui = 0 # No GUI unless requested.
    repository = None # use default repository specified in config

# --- web browser interface: ----------------------------------------------

def serve(port, callback=None):
    """start a HTTP server on the given port.  call 'callback' when the
    server is ready to serve"""

    class ViewCVS_Handler(BaseHTTPServer.BaseHTTPRequestHandler):
         
        def do_GET(self):
            """Serve a GET request."""
            if not self.path or self.path == "/":
                self.redirect()
            elif self.is_viewcvs():
                self.run_viewcvs()
            elif self.path[:7] == "/icons/":
                # XXX icon type should not be hardcoded to GIF:
                self.send_response(200)
                self.send_header("Content-type", "image/gif") 
                self.end_headers()
                apache_icons.serve_icon(self.path, self.wfile)
            else:
                self.send_error(404)

        def do_POST(self):
            """Serve a POST request."""
            if self.is_viewcvs():
                self.run_viewcvs()
            else:
                self.send_error(501, "Can only POST to viewcvs")

        def is_viewcvs(self):
            """Check whether self.path matches the hardcoded ScriptAlias
            /viewcvs"""
            if self.path[:8] == "/viewcvs":
                return 1
            return 0

        def redirect(self):
            """redirect the browser to the viewcvs URL"""
            self.send_response(301, "moved (redirection follows)")
            self.send_header("Content-type", "text/html")
            self.send_header("Location", self.server.url + 'viewcvs/')
            self.end_headers()
            self.wfile.write("""<html>
<head>
<meta http-equiv="refresh" content="1; URL=%s">
</head>
<body>
<h1>Redirection to <a href="%s">ViewCVS</a></h1>
Wait a second.   You will be automatically redirected to <b>ViewCVS</b>.
If this doesn't work, please click on the link above.
</body>
</html>
""" % tuple([self.server.url + "viewcvs/"]*2))

        def run_viewcvs(self):
            """This is a quick and dirty cut'n'rape from Pythons 
            standard library module CGIHTTPServer."""
            assert self.path[:8] == "/viewcvs"
            viewcvs_url, rest = self.server.url[:-1]+"/viewcvs", self.path[8:]
            i = string.rfind(rest, '?')
            if i >= 0:
                rest, query = rest[:i], rest[i+1:]
            else:
                query = ''
            i = string.find(rest, '/')
            if i >= 0:
                script, rest = rest[:i], rest[i:]
            else:
                script, rest = rest, ''
            scriptname = viewcvs_url + script
            # sys.stderr.write("Debug: '"+scriptname+"' '"+rest+"' '"+query+"'\n")
            env = os.environ
            # Since we're going to modify the env in the parent, provide empty
            # values to override previously set values
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
            # XXX Other HTTP_* headers
            decoded_query = string.replace(query, '+', ' ')

            self.send_response(200)
            # FIXME: I'm not sure about this:  Sometimes it hurts, sometimes 
            #        it is required.  Please enlight me
            if 1:
                self.send_header("Content-type", "text/html")
                self.end_headers()

            # Preserve state, because we execute script in current process:
            save_argv = sys.argv
            save_stdin = sys.stdin
            save_stdout = sys.stdout
            save_stderr = sys.stderr
            # For external tools like enscript we also need to redirect
            # the real stdout file descriptor:
            save_realstdout = os.dup(1) 
            try:
                try:
                    sys.stdout = self.wfile
                    os.close(1) 
                    assert os.dup(self.wfile.fileno()) == 1
                    sys.stdin = self.rfile
                    viewcvs.run_cgi()
                finally:
                    sys.argv = save_argv
                    sys.stdin = save_stdin
                    sys.stdout.flush()
                    os.close(1)
                    assert os.dup(save_realstdout) == 1
                    sys.stdout = save_stdout
                    sys.stderr = save_stderr
            except SystemExit, status:
                self.log_error("ViewCVS exit status %s", str(status))
            else:
                self.log_error("ViewCVS exited ok")

    class ViewCVS_Server(BaseHTTPServer.HTTPServer):
        def __init__(self, port, callback):
            host = (sys.platform == 'mac') and '127.0.0.1' or 'localhost'
            self.address = ('', port)
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

    ViewCVS_Server.handler = ViewCVS_Handler

    try:
        # XXX Move this code out of this function.
        # Early loading of configuration here.  Used to
        # allow tinkering with some configuration settings:
        viewcvs.handle_config()
        if options.repository:
            if viewcvs.cfg.general.cvs_roots.has_key("Development"):
                viewcvs.cfg.general.cvs_roots["Development"] = options.repository
            else:
                sys.stderr.write("*** No default ViewCVS configuration. Edit viewcvs.conf\n")
                raise KeyboardInterrupt # Hack!
        elif viewcvs.cfg.general.cvs_roots.has_key("Development") and \
             not os.path.isdir(viewcvs.cfg.general.cvs_roots["Development"]):
            sys.stderr.write("*** No repository found. Please use the -r option.\n")
            sys.stderr.write("   Use --help for more info.\n")
            raise KeyboardInterrupt # Hack!
        os.close(0) # To avoid problems with shell job control
        ViewCVS_Server(port, callback).serve_until_quit()
    except (KeyboardInterrupt, select.error):
        pass
    print 'server stopped'

# --- graphical interface: --------------------------------------------------

def gui(port):
    """Graphical interface (starts web server and pops up a control window)."""
    class GUI:
        def __init__(self, window, port):
            self.window = window
            self.server = None
            self.scanner = None

            import Tkinter
            self.server_frm = Tkinter.Frame(window)
            self.title_lbl = Tkinter.Label(self.server_frm,
                text='Starting server...\n ')
            self.open_btn = Tkinter.Button(self.server_frm,
                text='open browser', command=self.open, state='disabled')
            self.quit_btn = Tkinter.Button(self.server_frm,
                text='quit serving', command=self.quit, state='disabled')


            self.window.title('ViewCVS standalone')
            self.window.protocol('WM_DELETE_WINDOW', self.quit)
            self.title_lbl.pack(side='top', fill='x')
            self.open_btn.pack(side='left', fill='x', expand=1)
            self.quit_btn.pack(side='right', fill='x', expand=1)

            # Early loading of configuration here.  Used to
            # allow tinkering with configuration settings through the gui:
            viewcvs.handle_config()
            if not LIBRARY_DIR:
                viewcvs.cfg.options.cvsgraph_conf = "../cgi/cvsgraph.conf.dist"

            self.options_frm = Tkinter.Frame(window)

            # cvsgraph toggle:
            self.cvsgraph_ivar = Tkinter.IntVar()
            self.cvsgraph_ivar.set(viewcvs.cfg.options.use_cvsgraph)
            self.cvsgraph_toggle = Tkinter.Checkbutton(self.options_frm,
                text="enable cvsgraph (needs binary)", var=self.cvsgraph_ivar,
                command=self.toggle_use_cvsgraph)
            self.cvsgraph_toggle.pack(side='top', anchor='w')

            # enscript toggle:
            self.enscript_ivar = Tkinter.IntVar()
            self.enscript_ivar.set(viewcvs.cfg.options.use_enscript)
            self.enscript_toggle = Tkinter.Checkbutton(self.options_frm,
                text="enable enscript (needs binary)", var=self.enscript_ivar,
                command=self.toggle_use_enscript)
            self.enscript_toggle.pack(side='top', anchor='w')

            # show_subdir_lastmod toggle:
            self.subdirmod_ivar = Tkinter.IntVar()
            self.subdirmod_ivar.set(viewcvs.cfg.options.show_subdir_lastmod)
            self.subdirmod_toggle = Tkinter.Checkbutton(self.options_frm,
                text="show subdir last mod (dir view)", var=self.subdirmod_ivar,
                command=self.toggle_subdirmod)
            self.subdirmod_toggle.pack(side='top', anchor='w')

            # use_re_search toggle:
            self.useresearch_ivar = Tkinter.IntVar()
            self.useresearch_ivar.set(viewcvs.cfg.options.use_re_search)
            self.useresearch_toggle = Tkinter.Checkbutton(self.options_frm,
                text="allow regular expr search", var=self.useresearch_ivar,
                command=self.toggle_useresearch)
            self.useresearch_toggle.pack(side='top', anchor='w')

            # directory view template:
            self.dirtemplate_lbl = Tkinter.Label(self.options_frm,
                text='Chooose HTML Template for the Directory pages:')
            self.dirtemplate_lbl.pack(side='top', anchor='w')
            self.dirtemplate_svar = Tkinter.StringVar()
            self.dirtemplate_svar.set(viewcvs.cfg.templates.directory)
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
            self.logtemplate_svar.set(viewcvs.cfg.templates.log)
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
            self.querytemplate_svar.set(viewcvs.cfg.templates.query)
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

            import threading
            threading.Thread(target=serve, args=(port, self.ready)).start()

        def toggle_use_cvsgraph(self, event=None):
            viewcvs.cfg.options.use_cvsgraph = self.cvsgraph_ivar.get()

        def toggle_use_enscript(self, event=None):
            viewcvs.cfg.options.use_enscript = self.enscript_ivar.get()

        def toggle_subdirmod(self, event=None):
            viewcvs.cfg.options.show_subdir_lastmod = self.subdirmod_ivar.get()

        def toggle_useresearch(self, event=None):
            viewcvs.cfg.options.use_re_search = self.useresearch_ivar.get()

        def set_templates_log(self, event=None):
            viewcvs.cfg.templates.log = self.logtemplate_svar.get()

        def set_templates_directory(self, event=None):
            viewcvs.cfg.templates.directory = self.dirtemplate_svar.get()

        def set_templates_query(self, event=None):
            viewcvs.cfg.templates.query = self.querytemplate_svar.get()

        def ready(self, server):
            """used as callback parameter to the serve() function"""
            self.server = server
            self.title_lbl.config(
                text='ViewCVS standalone server at\n' + server.url)
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
        gui = GUI(Tkinter.Tk(), port)
        Tkinter.mainloop()
    except KeyboardInterrupt:
        pass

# --- command-line interface: ----------------------------------------------

def cli(argv):
    """Command-line interface (looks at argv to decide what to do)."""
    import getopt
    class BadUsage(Exception): pass

    try:
        opts, args = getopt.getopt(argv[1:], 'gp:r:', 
            ['gui', 'port=', 'repository='])
        for opt, val in opts:
            if opt in ('-g', '--gui'):
                options.start_gui = 1
            elif opt in ('-r', '--repository'):
                options.repository = val
            elif opt in ('-p', '--port'):
                try:
                    options.port = int(val)
                except ValueError:
                    raise BadUsage
        if options.start_gui:
            gui(options.port)
            return
        elif options.port:
            def ready(server):
                print 'server ready at %s' % server.url
            serve(options.port, ready)
            return
        raise BadUsage
    except (getopt.error, BadUsage):
        cmd = sys.argv[0]
        port = options.port
        print """ViewCVS standalone - a simple standalone HTTP-Server

Usage: %(cmd)s [ <options> ]

Available Options:
-p <port> or --port=<port>
    Start an HTTP server on the given port on the local machine.
    Default port is %(port)d.

-r <path> or --repository=<path>
    Specify another path for the default CVS repository "Development".
    If you don't have your repository at /home/cvsroot you will need to
    use this option or you have to install first and edit viewcvs.conf.

-g or --gui
    Pop up a graphical interface for serving and testing ViewCVS.

""" % locals()

if __name__ == '__main__': 
    if LIBRARY_DIR:
        sys.path.insert(0, LIBRARY_DIR)
    else:
        sys.path[:0] = ['lib']
        os.chdir('lib')
    import viewcvs
    import apache_icons
    options = Options()
    cli(sys.argv)
