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

# XXX Unresolved issues: avoid forking for each request.
# XXX Make /icons/ source directory configurable.  currently it is simply 
#     hardcoded to /usr/local/httpd.
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
# These values will be set during the installation process. During
# development, they will remain None.
#

LIBRARY_DIR = None

import sys
import os
import string
import urllib

# --- web browser interface: ----------------------------------------------

def serve(port, callback=None):
    import BaseHTTPServer, SimpleHTTPServer, select

    class ViewCVS_Handler(SimpleHTTPServer.SimpleHTTPRequestHandler):
         
        def do_GET(self):
            """Serve a GET request."""
            if not self.path or self.path == "/":
                self.redirect()
            elif self.is_viewcvs():
                self.run_viewcvs()
            else:
                save_cwd = os.getcwd() # XXX: Ugly hack around SimpleHTTPServer
                if self.path[:7] == "/icons/":
                    APACHE_ROOT="/usr/local/httpd" # FIXME.
                    os.chdir(APACHE_ROOT)
                self.base.do_GET(self)
                os.chdir(save_cwd)

        def do_POST(self):
            """Serve a POST request."""
            if self.is_viewcvs():
                self.run_viewcvs()
            else:
                self.send_error(501, "Can only POST to viewcvs")

        def send_head(self):
            """Version of send_head that support viewcvs"""
            if self.is_viewcvs():
                return self.run_viewcvs()
            else:
                return self.base.send_head(self)

        def is_viewcvs(self):
            if self.path[:8] == "/viewcvs":
                return 1
            return 0

        def redirect(self):
            self.send_response(200, "redirection follows")
            self.send_header("Content-type", "text/html")
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
            """This a quick and dirty cut'n'rape from Pythons 
            standard library module CGIHTTPServer."""
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
            env['PATH_TRANSLATED'] = self.translate_path(uqrest)
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

            self.send_response(200, "Script output follows")
            self.send_header("Content-type", "text/html")
            self.end_headers()
            # Preserve state, because we execute script in current process:
            save_argv = sys.argv
            save_stdin = sys.stdin
            save_stdout = sys.stdout
            save_stderr = sys.stderr
            try:
                try:
                    sys.stdout = self.wfile
                    sys.stdin = self.rfile
                    viewcvs.main()
                finally:
                    sys.argv = save_argv
                    sys.stdin = save_stdin
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
            self.base.__init__(self, self.address, self.handler)

        def serve_until_quit(self):
            import select
            self.quit = 0
            while not self.quit:
                rd, wr, ex = select.select([self.socket.fileno()], [], [], 1)
                if rd: self.handle_request()

        def server_activate(self):
            self.base.server_activate(self)
            if self.callback: self.callback(self)

    ViewCVS_Server.base = BaseHTTPServer.HTTPServer
    ViewCVS_Server.handler = ViewCVS_Handler
    ViewCVS_Handler.base = SimpleHTTPServer.SimpleHTTPRequestHandler
    try:
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
            self.server_frm.pack(side='top', fill='x')

            self.window.update()
            self.minwidth = self.window.winfo_width()
            self.minheight = self.window.winfo_height()
            self.expanded = 0
            self.window.wm_geometry('%dx%d' % (self.minwidth, self.minheight))
            self.window.wm_minsize(self.minwidth, self.minheight)

            import threading
            threading.Thread(target=serve, args=(port, self.ready)).start()

        def ready(self, server):
            self.server = server
            self.title_lbl.config(
                text='ViewCVS standalone server at\n' + server.url)
            self.open_btn.config(state='normal')
            self.quit_btn.config(state='normal')

        def open(self, event=None, url=None):
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

    port = 7467
    start_gui = 0
    try:
        opts, args = getopt.getopt(argv[1:], 'gp:', ['gui', 'port='])
        for opt, val in opts:
            if opt in ('-g', '--gui'):
                start_gui = 1
            if opt in ('-p', '--port'):
                try:
                    port = int(val)
                except ValueError:
                    raise BadUsage
        if start_gui:
            gui(port)
            return
        elif port:
            def ready(server):
                print 'server ready at %s' % server.url
            serve(port, ready)
            return
        raise BadUsage
    except (getopt.error, BadUsage):
        cmd = sys.argv[0]
        print """ViewCVS standalone - a simple standalone HTTP-Server

%(cmd)s -p <port> or --port=<port>
    Start an HTTP server on the given port on the local machine.

%(cmd)s -g or --gui
    Pop up a graphical interface for serving and testing ViewCVS .
""" % locals()

if __name__ == '__main__': 
    if LIBRARY_DIR:
        sys.path.insert(0, LIBRARY_DIR)
    else:
        sys.path[:0] = ['lib']
        os.chdir('lib')
    import viewcvs
    cli(sys.argv)
