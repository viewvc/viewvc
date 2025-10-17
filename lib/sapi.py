# -*-python-*-
#
# Copyright (C) 1999-2025 The ViewCVS Group. All Rights Reserved.
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
from urllib.parse import parse_qs


# Global server object.
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


# Python 3.13 dropped the `cgi` module, so we have to implement our own
# (narrowly focused) version of `cgi.parse()`.
def cgi_parse(environ=os.environ) -> dict:
    """Parse query parameters from the CGI environment."""

    if "environ" in environ:
        qs = environ["QUERY_STRING"]
    else:
        qs = sys.argv[1] if sys.argv[1:] else ""
        environ["QUERY_STRING"] = qs
    return parse_qs(qs, encoding="utf-8") if qs else {}


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
            raise ServerUsageError("Server response has already been started")
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
        return cgi_parse(self._environ)

    def write(self, s):
        self._wsgi_write(s)

    def flush(self):
        pass

    def file(self):
        return ServerFile(self)


def redirect_notice(url):
    return f'This document is located <a href="{url}">here</a>.'
