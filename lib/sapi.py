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
import re
from urllib.parse import parse_qs, unquote
from typing import Union, List

try:
    from idna import encode as idna_encode, decode as idna_decode, IDNAError
except ImportError:
    idna_encode = None

    def idna_decode(x: str) -> str:
        return x


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

    if "QUERY_STRING" in environ:
        qs = environ["QUERY_STRING"]
    else:
        qs = sys.argv[1] if sys.argv[1:] else ""
        environ["QUERY_STRING"] = qs
    return parse_qs(qs, encoding="utf-8") if qs else {}


#
# Regular expressions for RFC3986 uri-host syntax validation
#
_R_DIGIT = r"[0-9]"
_R_HEXDIG = r"[0-9a-f]"
# Although the syntax of pct-encode in RFC3986 allows arbitrary code
# through 0x00 to 0xff, some of the code cannot be used in pct-encoded code
# for the reg-name syntax
# List of allowed codes:
#     minus("-")             : 0x2d
#     period(".")            : 0x2e
#     digit                  : 0x30-0x39
#     alphabet               : 0x41-0x5a, 0x61-0x7a
#     UTF-8 continuation byte: 0x80-0xbf
#     UTF-8 valid first byte : 0xc2-0xf4
_R_PCT_ENCODED = r"%(2[de]|3[0-9]|[46][1-9a-f]|[57][0-9a]|[89abde][0-9a-f]|c[2-9a-f]|f[0-4])"
_R_GEN_DELIMS = r"[]:/?#@[]"
_R_SUB_DELIMS = r"[!$&\x27()*+,;=]"
_R_RESERVED = rf"({_R_GEN_DELIMS}|{_R_SUB_DELIMS})"
_R_UNRESERVED = r"[0-9a-z._~-]"
_R_DEC_OCTET = rf"({_R_DIGIT}|[1-9]{_R_DIGIT}|1{_R_DIGIT}{{2}}|2[0-4]{_R_DIGIT}|25[0-5])"
_R_H16 = rf"{_R_HEXDIG}{{1,4}}"
_R_IPV4ADDRESS = rf"{_R_DEC_OCTET}\.{_R_DEC_OCTET}\.{_R_DEC_OCTET}\.{_R_DEC_OCTET}"
_R_LS32 = rf"({_R_H16}:{_R_H16}|{_R_IPV4ADDRESS})"
_R_IPV6ADDRESS = (
    rf"(({_R_H16}:){{6}}{_R_LS32}|"
    rf"::({_R_H16}:){{5}}{_R_LS32}|"
    rf"({_R_H16})?::({_R_H16}:){{4}}{_R_LS32}|"
    rf"(({_R_H16}:)?{_R_H16})?::({_R_H16}:){{3}}{_R_LS32}|"
    rf"(({_R_H16}:){{,2}}{_R_H16})?::({_R_H16}:){{2}}{_R_LS32}|"
    rf"(({_R_H16}:){{,3}}{_R_H16})?::{_R_H16}:{_R_LS32}|"
    rf"(({_R_H16}:){{,4}}{_R_H16})?::{_R_LS32}|"
    rf"(({_R_H16}:){{,5}}{_R_H16})?::{_R_H16}|"
    rf"(({_R_H16}:){{,6}}{_R_H16})?::)"
)
_R_IPVFUTURE = rf"v{_R_HEXDIG}+\.({_R_UNRESERVED}|{_R_SUB_DELIMS}|:)+"
_R_IP_LITERAL = rf"\[({_R_IPV6ADDRESS}|{_R_IPVFUTURE})\]"
_R_REG_NAME = rf"({_R_UNRESERVED}|{_R_PCT_ENCODED}|{_R_SUB_DELIMS})*"
_R_URI_HOST = rf"({_R_IP_LITERAL}|(?P<ipv4addr>{_R_IPV4ADDRESS})|(?P<reg_name>{_R_REG_NAME}))"
_R_PORT = rf"{_R_DIGIT}*"
_R_HOST = rf"(?P<host>{_R_URI_HOST})(:(?P<port>{_R_PORT}))?"
_re_host = re.compile(_R_HOST)
_re_dn = re.compile(r"([0-9a-z]([0-9a-z-]*[0-9a-z])*\.)*[0-9a-z]([0-9a-z-]*[0-9a-z])?\.?")


class UriValidateException(Exception):
    pass


def normalize_urihost(s: str, default_port: Union[int, str, None] = None) -> str:
    "Validate and normalize a host string described in RFC 3986 section 3.2.2"

    if not s:
        return s
    m = _re_host.fullmatch(s.lower())
    if not m:
        raise UriValidateException(f'Bad Syntax: "{s}"')
    host = m["host"]
    port = m["port"]
    if port:
        if not host:
            raise UriValidateException(f'Empty host part is not allowed with port spec: "{s}"')
        if not (0 <= int(port) <= 65535):
            raise UriValidateException(f"Invalid port number: {port}")
    reg_name = m["reg_name"]
    if reg_name is not None:
        assert host == reg_name
        if reg_name:
            if not _re_dn.fullmatch(reg_name):
                try:
                    reg_name = unquote(reg_name, errors="strict")
                except UnicodeDecodeError:
                    raise UriValidateException("Illegal sequence of percent encoding")
                if idna_encode is not None:
                    try:
                        host = idna_encode(reg_name)
                    except IDNAError as e:
                        raise UriValidateException(str(e))
                else:
                    if not _re_dn.fullmatch(reg_name):
                        raise UriValidateException(
                            "Illegal sequence of percent encoding "
                            "(we don't support native representation of IDN)"
                        )
        else:
            assert port is not None
        if host.endswith("."):
            host = host[:-1]
        if len(host) > 253:
            raise UriValidateException("Hostname too long")
        for label in host.split("."):
            if len(label) > 63:
                raise UriValidateException("Host label too long")

    if (port is None) or (default_port is not None and int(port) == int(default_port)):
        return host
    return f"{host}:{port}"


def is_allowed_hosts(urihost: str, allowed_hosts: List[str]) -> bool:
    """Check if the URIHOST value matches in any of the element in
    ALLOWED_HOSTS.  Value enclosed by // in ALLOWED_HOSTS are treated
    as regular explession. The matching is done in case insensitive,
    and supports IDN if idna module is avaliable."""

    if not allowed_hosts:
        return True
    if ":" in urihost:
        host, port = urihost.split(":")
    else:
        host = urihost
        port = None
    dec_urihost = idna_decode(host) if port is None else f"{idna_decode(host)}:{port}"
    for allowed in allowed_hosts:
        if not allowed.startswith("/"):
            if allowed.lower() in (dec_urihost, urihost):
                return True
        elif allowed.endswith("/"):
            if re.search(allowed[1:-1], dec_urihost, flags=re.IGNORECASE):
                return True
    return False


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
    def __init__(self, uri_host: Union[str, None] = None, scheme: Union[str, None] = None):
        """Initialized the server.  Child classes should extend this."""
        self._response_started = False
        self.scheme = "http" if scheme is None else scheme
        default_port = {"http": 80, "https": 443}.get(self.scheme)
        try:
            self.uri_host = normalize_urihost(
                uri_host if uri_host is not None else "", default_port
            )
            self.error = None
        except UriValidateException as e:
            # To send "400 Bad Request" status code to the client, it need
            # the instance of this class. So we store the exception here.
            self.uri_host = None
            self.error = e

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
        uri_host = environ.get("HTTP_HOST", "")
        scheme = "https" if environ.get("HTTPS") == "on" else "http"
        Server.__init__(self, uri_host, scheme)
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
        self._wsgi_write(redirect_notice(url).encode('utf-8'))

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
