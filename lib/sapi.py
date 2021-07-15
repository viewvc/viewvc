# -*-python-*-
#
# Copyright (C) 1999-2021 The ViewCVS Group. All Rights Reserved.
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

import os
import sys
import cgi


# Global server object. It will be one of the following:
#   1. a CgiServer object
#   2. an WsgiServer object
server = None


# Simple HTML string escaping.  Note that we always escape the
# double-quote character -- ViewVC shouldn't ever need to preserve
# that character as-is, and sometimes needs to embed escaped values
# into HTML attributes.
def escape(s):
    s = str(s)
    s = s.replace("&", "&amp;")
    s = s.replace(">", "&gt;")
    s = s.replace("<", "&lt;")
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
        self.mode = "w"
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
            raise ServerUsageError()
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
        if NAME isn't found in the server environment.  Unlike os.getenv(),
        the raw value of enviroment variable should be always decoded as
        UTF-8 and the type of return value should be str or None.  Child
        classes should override this method."""
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


class CgiServer(Server):
    """CGI server implementation."""

    def __init__(self):
        Server.__init__(self)
        self._headers = []
        self._iis = os.environ.get("SERVER_SOFTWARE", "")[:13] == "Microsoft-IIS"
        global server
        server = self

    def add_header(self, name, value):
        self._headers.append((name, value))

    def start_response(self, content_type="text/html; charset=UTF-8", status=None):
        Server.start_response(self, content_type, status)

        extraheaders = ""
        for (name, value) in self._headers:
            extraheaders = extraheaders + "%s: %s\r\n" % (name, value)

        # The only way ViewVC pages and error messages are visible under
        # IIS is if a 200 error code is returned. Otherwise IIS instead
        # sends the static error page corresponding to the code number.
        if status is None or (status[:3] != "304" and self._iis):
            status = ""
        else:
            status = "Status: %s\r\n" % status

        self.write_text("%sContent-Type: %s\r\n%s\r\n" % (status, content_type, extraheaders))

    def redirect(self, url):
        if self._iis:
            url = fix_iis_url(self, url)
        self.add_header("Location", url)
        self.start_response(status="301 Moved")
        self.write_text(redirect_notice(url))

    def getenv(self, name, value=None):
        # we should always use UTF-8 to decode OS's environment variable.
        if sys.getfilesystemencoding() == "UTF-8":
            ret = os.environ.get(name, value)
        else:
            if os.supports_bytes_environ:
                if isinstance(value, str):
                    value = value.encode("utf-8", "surrogateescape")
                ret = os.environb.get(name.encode(sys.getfilesystemencoding()), value)
            else:
                ret = os.environ.get(name, value)
                if isinstance(ret, str):
                    ret = ret.encode(sys.getfilesystemencoding(), "surrogateescape")
            if isinstance(ret, bytes):
                ret = ret.decode("utf-8", "surrogateescape")
        if self._iis and name == "PATH_INFO":
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
        self._write_response = write_response
        self._headers = []
        self._wsgi_write = None
        global server
        server = self

    def add_header(self, name, value):
        self._headers.append((name, value))

    def start_response(self, content_type="text/html; charset=UTF-8", status=None):
        Server.start_response(self, content_type, status)
        if not status:
            status = "200 OK"
        self._headers.insert(
            0,
            ("Content-Type", content_type),
        )
        self._wsgi_write = self._write_response(status, self._headers)

    def redirect(self, url):
        self.add_header("Location", url)
        self.start_response(status="301 Moved")
        self._wsgi_write(redirect_notice(url))

    def getenv(self, name, default_value=None):
        value = self._environ.get(name, default_value)
        # PEP 3333 demands that PATH_INFO et al carry only latin-1
        # strings, so multibyte versioned path names arrive munged, with
        # each byte being a character.  But ViewVC generates it's own URLs
        # from Unicode strings, where UTF-8 is used during URI-encoding.
        # So we need to reinterpret path-carrying CGI environment
        # variables as UTF-8 instead of as latin-1.
        if name in ["PATH_INFO", "SCRIPT_NAME"]:
            value = value.encode("latin-1").decode("utf-8", errors="surrogateescape")
        return value

    def params(self):
        return cgi.parse(environ=self._environ, fp=self._environ["wsgi.input"])

    def write(self, s):
        self._wsgi_write(s)

    def flush(self):
        pass

    def file(self):
        return ServerFile(self)


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
    if url[0] == "/":
        if server.getenv("HTTPS") == "on":
            dport = "443"
            prefix = "https://"
        else:
            dport = "80"
            prefix = "http://"
        prefix = prefix + server.getenv("HTTP_HOST")
        if server.getenv("SERVER_PORT") != dport:
            prefix = prefix + ":" + server.getenv("SERVER_PORT")
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
    return path_info[len(server.getenv("SCRIPT_NAME", "")) :]


def redirect_notice(url):
    return 'This document is located <a href="%s">here</a>.' % (url)
