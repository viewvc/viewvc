# -*-python-*-
#
# Copyright (C) 1999-2011 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# viewvc: View CVS/SVN repositories via a web browser
#
# -----------------------------------------------------------------------

__version__ = '1.1.11'

# this comes from our library; measure the startup time
import debug
debug.t_start('startup')
debug.t_start('imports')

# standard modules that we know are in the path or builtin
import sys
import os
import gzip
import mimetypes
import re
import rfc822
import stat
import string
import struct
import tempfile
import time
import types
import urllib

# These modules come from our library (the stub has set up the path)
import accept
import compat
import config
import ezt
import popen
import sapi
import vcauth
import vclib
import vclib.ccvs
import vclib.svn

try:
  import idiff
except (SyntaxError, ImportError):
  idiff = None

debug.t_end('imports')

#########################################################################

checkout_magic_path = '*checkout*'
# According to RFC 1738 the '~' character is unsafe in URLs.
# But for compatibility with URLs bookmarked with old releases of ViewCVS:
oldstyle_checkout_magic_path = '~checkout~'
docroot_magic_path = '*docroot*'
viewcvs_mime_type = 'text/vnd.viewcvs-markup'
alt_mime_type = 'text/x-cvsweb-markup'
view_roots_magic = '*viewroots*'

# Put here the variables we need in order to hold our state - they
# will be added (with their current value) to (almost) any link/query
# string you construct.
_sticky_vars = [
  'hideattic',
  'sortby',
  'sortdir',
  'logsort',
  'diff_format',
  'search',
  'limit_changes',
  ]

# for reading/writing between a couple descriptors
CHUNK_SIZE = 8192

# for rcsdiff processing of header
_RCSDIFF_IS_BINARY = 'binary-diff'
_RCSDIFF_ERROR = 'error'

# special characters that don't need to be URL encoded
_URL_SAFE_CHARS = "/*~"


class Request:
  def __init__(self, server, cfg):
    self.server = server
    self.cfg = cfg

    self.script_name = _normalize_path(server.getenv('SCRIPT_NAME', ''))
    self.browser = server.getenv('HTTP_USER_AGENT', 'unknown')

    # process the Accept-Language: header, and load the key/value
    # files, given the selected language
    hal = server.getenv('HTTP_ACCEPT_LANGUAGE','')
    try:
      self.lang_selector = accept.language(hal)
    except accept.AcceptLanguageParseError:
      self.lang_selector = accept.language('en')
    self.language = self.lang_selector.select_from(cfg.general.languages)
    self.kv = cfg.load_kv_files(self.language)

    # check for an authenticated username
    self.username = server.getenv('REMOTE_USER')

    # if we allow compressed output, see if the client does too
    self.gzip_compress_level = 0
    if cfg.options.allow_compress:
      http_accept_encoding = os.environ.get("HTTP_ACCEPT_ENCODING", "")
      if "gzip" in filter(None,
                          map(lambda x: string.strip(x),
                              string.split(http_accept_encoding, ","))):
        self.gzip_compress_level = 9  # make this configurable?

  def run_viewvc(self):

    cfg = self.cfg

    # This function first parses the query string and sets the following
    # variables. Then it executes the request.
    self.view_func = None  # function to call to process the request
    self.repos = None      # object representing current repository
    self.rootname = None   # name of current root (as used in viewvc.conf)
    self.roottype = None   # current root type ('svn' or 'cvs')
    self.rootpath = None   # physical path to current root
    self.pathtype = None   # type of path, either vclib.FILE or vclib.DIR
    self.where = None      # path to file or directory in current root
    self.query_dict = {}   # validated and cleaned up query options
    self.path_parts = None # for convenience, equals where.split('/')
    self.pathrev = None    # current path revision or tag
    self.auth = None       # authorizer module in use

    # redirect if we're loading from a valid but irregular URL
    # These redirects aren't neccessary to make ViewVC work, it functions
    # just fine without them, but they make it easier for server admins to
    # implement access restrictions based on URL
    needs_redirect = 0

    # Process the query params
    for name, values in self.server.params().items():
      # we only care about the first value
      value = values[0]
      
      # patch up old queries that use 'cvsroot' to look like they used 'root'
      if name == 'cvsroot':
        name = 'root'
        needs_redirect = 1

      # same for 'only_with_tag' and 'pathrev'
      if name == 'only_with_tag':
        name = 'pathrev'
        needs_redirect = 1

      # redirect view=rev to view=revision, too
      if name == 'view' and value == 'rev':
        value = 'revision'
        needs_redirect = 1

      # validate the parameter
      _validate_param(name, value)
      
      # if we're here, then the parameter is okay
      self.query_dict[name] = value

    # Resolve the view parameter into a handler function.
    self.view_func = _views.get(self.query_dict.get('view', None), 
                                self.view_func)

    # Process PATH_INFO component of query string
    path_info = self.server.getenv('PATH_INFO', '')

    # clean it up. this removes duplicate '/' characters and any that may
    # exist at the front or end of the path.
    ### we might want to redirect to the cleaned up URL
    path_parts = _path_parts(path_info)

    if path_parts:
      # handle magic path prefixes
      if path_parts[0] == docroot_magic_path:
        # if this is just a simple hunk of doc, then serve it up
        self.where = _path_join(path_parts[1:])
        return view_doc(self)
      elif path_parts[0] in (checkout_magic_path,
                             oldstyle_checkout_magic_path):
        path_parts.pop(0)
        self.view_func = view_checkout
        if not cfg.options.checkout_magic:
          needs_redirect = 1

      # handle tarball magic suffixes
      if self.view_func is download_tarball:
        if (self.query_dict.get('parent')):
          del path_parts[-1]
        elif path_parts[-1][-7:] == ".tar.gz":
          path_parts[-1] = path_parts[-1][:-7]

    # Figure out root name
    self.rootname = self.query_dict.get('root')
    if self.rootname == view_roots_magic:
      del self.query_dict['root']
      self.rootname = ""
      needs_redirect = 1
    elif self.rootname is None:
      if cfg.options.root_as_url_component:
        if path_parts:
          self.rootname = path_parts.pop(0)
        else:
          self.rootname = ""
      elif self.view_func != view_roots:
        self.rootname = cfg.general.default_root
    elif cfg.options.root_as_url_component:
      needs_redirect = 1

    self.where = _path_join(path_parts)
    self.path_parts = path_parts

    if self.rootname:
      roottype, rootpath = locate_root(cfg, self.rootname)
      if roottype:
        # Overlay root-specific options.
        cfg.overlay_root_options(self.rootname)
        
        # Setup an Authorizer for this rootname and username
        self.auth = setup_authorizer(cfg, self.username)

        # Create the repository object
        try:
          if roottype == 'cvs':
            self.rootpath = vclib.ccvs.canonicalize_rootpath(rootpath)
            self.repos = vclib.ccvs.CVSRepository(self.rootname,
                                                  self.rootpath,
                                                  self.auth,
                                                  cfg.utilities,
                                                  cfg.options.use_rcsparse)
            # required so that spawned rcs programs correctly expand
            # $CVSHeader$
            os.environ['CVSROOT'] = self.rootpath
          elif roottype == 'svn':
            self.rootpath = vclib.svn.canonicalize_rootpath(rootpath)
            self.repos = vclib.svn.SubversionRepository(self.rootname,
                                                        self.rootpath,
                                                        self.auth,
                                                        cfg.utilities,
                                                        cfg.options.svn_config_dir)
          else:
            raise vclib.ReposNotFound()
        except vclib.ReposNotFound:
          pass
      if self.repos is None:
        raise debug.ViewVCException(
          'The root "%s" is unknown. If you believe the value is '
          'correct, then please double-check your configuration.'
          % self.rootname, "404 Not Found")

    if self.repos:
      self.repos.open()
      type = self.repos.roottype()
      if type == vclib.SVN:
        self.roottype = 'svn'
      elif type == vclib.CVS:
        self.roottype = 'cvs'
      else:
        raise debug.ViewVCException(
          'The root "%s" has an unknown type ("%s").  Expected "cvs" or "svn".'
          % (self.rootname, type),
          "500 Internal Server Error")
      
    # If this is using an old-style 'rev' parameter, redirect to new hotness.
    # Subversion URLs will now use 'pathrev'; CVS ones use 'revision'.
    if self.repos and self.query_dict.has_key('rev'):
      if self.roottype == 'svn' \
             and not self.query_dict.has_key('pathrev') \
             and not self.view_func == view_revision:
        self.query_dict['pathrev'] = self.query_dict['rev']
        del self.query_dict['rev']
      else: # elif not self.query_dict.has_key('revision'): ?
        self.query_dict['revision'] = self.query_dict['rev']
        del self.query_dict['rev']
      needs_redirect = 1

    if self.repos and self.view_func is not redirect_pathrev:
      # If this is an intended-to-be-hidden CVSROOT path, complain.
      if cfg.options.hide_cvsroot \
         and is_cvsroot_path(self.roottype, path_parts):
        raise debug.ViewVCException("Unknown location: /%s" % self.where,
                                    "404 Not Found")

      # Make sure path exists
      self.pathrev = pathrev = self.query_dict.get('pathrev')
      self.pathtype = _repos_pathtype(self.repos, path_parts, pathrev)

      if self.pathtype is None:
        # Path doesn't exist, see if it could be an old-style ViewVC URL
        # with a fake suffix.
        result = _strip_suffix('.diff', path_parts, pathrev, vclib.FILE,     \
                               self.repos, view_diff) or                     \
                 _strip_suffix('.tar.gz', path_parts, pathrev, vclib.DIR,    \
                               self.repos, download_tarball) or              \
                 _strip_suffix('root.tar.gz', path_parts, pathrev, vclib.DIR,\
                               self.repos, download_tarball) or              \
                 _strip_suffix(self.rootname + '-root.tar.gz',               \
                               path_parts, pathrev, vclib.DIR,               \
                               self.repos, download_tarball) or              \
                 _strip_suffix('root',                                       \
                               path_parts, pathrev, vclib.DIR,               \
                               self.repos, download_tarball) or              \
                 _strip_suffix(self.rootname + '-root',                      \
                               path_parts, pathrev, vclib.DIR,               \
                               self.repos, download_tarball)
        if result:
          self.path_parts, self.pathtype, self.view_func = result
          self.where = _path_join(self.path_parts)
          needs_redirect = 1
        else:
          raise debug.ViewVCException("Unknown location: /%s" % self.where,
                                      "404 Not Found")

      # If we have an old ViewCVS Attic URL which is still valid, redirect
      if self.roottype == 'cvs':
        attic_parts = None
        if (self.pathtype == vclib.FILE and len(self.path_parts) > 1
            and self.path_parts[-2] == 'Attic'):
          attic_parts = self.path_parts[:-2] + self.path_parts[-1:]
        elif (self.pathtype == vclib.DIR and len(self.path_parts) > 0
              and self.path_parts[-1] == 'Attic'):
          attic_parts = self.path_parts[:-1]
        if attic_parts:
          self.path_parts = attic_parts
          self.where = _path_join(attic_parts)
          needs_redirect = 1

    if self.view_func is None:
      # view parameter is not set, try looking at pathtype and the 
      # other parameters
      if not self.rootname:
        self.view_func = view_roots
      elif self.pathtype == vclib.DIR:
        # ViewCVS 0.9.2 used to put ?tarball=1 at the end of tarball urls
        if self.query_dict.has_key('tarball'):
          self.view_func = download_tarball
        else:
          self.view_func = view_directory
      elif self.pathtype == vclib.FILE:
        if self.query_dict.has_key('r1') and self.query_dict.has_key('r2'):
          self.view_func = view_diff
        elif self.query_dict.has_key('annotate'):
          self.view_func = view_annotate
        elif self.query_dict.has_key('graph'):
          if not self.query_dict.has_key('makeimage'):
            self.view_func = view_cvsgraph
          else: 
            self.view_func = view_cvsgraph_image
        elif self.query_dict.has_key('revision') \
                 or cfg.options.default_file_view != "log":
          if cfg.options.default_file_view == "markup" \
             or self.query_dict.get('content-type', None) \
                 in (viewcvs_mime_type, alt_mime_type):
            self.view_func = view_markup
          else:
            self.view_func = view_checkout
        else:
          self.view_func = view_log

    # If we've chosen the roots or revision view, our effective
    # location is not really "inside" the repository, so we have no
    # path and therefore no path parts or type, either.
    if self.view_func is view_revision or self.view_func is view_roots:
      self.where = ''
      self.path_parts = []
      self.pathtype = None
      
    # if we have a directory and the request didn't end in "/", then redirect
    # so that it does.
    if (self.pathtype == vclib.DIR and path_info[-1:] != '/'
        and self.view_func is not download_tarball
        and self.view_func is not redirect_pathrev):
      needs_redirect = 1

    # startup is done now.
    debug.t_end('startup')

    # If we need to redirect, do so.  Otherwise, handle our requested view.
    if needs_redirect:
      self.server.redirect(self.get_url())
    else:
      self.view_func(self)

  def get_url(self, escape=0, partial=0, prefix=0, **args):
    """Constructs a link to another ViewVC page just like the get_link
    function except that it returns a single URL instead of a URL
    split into components.  If PREFIX is set, include the protocol and
    server name portions of the URL."""

    url, params = apply(self.get_link, (), args)
    qs = compat.urlencode(params)
    if qs:
      result = urllib.quote(url, _URL_SAFE_CHARS) + '?' + qs
    else:
      result = urllib.quote(url, _URL_SAFE_CHARS)

    if partial:
      result = result + (qs and '&' or '?')
    if escape:
      result = self.server.escape(result)
    if prefix:
      result = '%s://%s%s' % \
               (self.server.getenv("HTTPS") == "on" and "https" or "http",
                self.server.getenv("HTTP_HOST"),
                result)
    return result

  def get_form(self, **args):
    """Constructs a link to another ViewVC page just like the get_link
    function except that it returns a base URL suitable for use as an
    HTML form action, and an iterable object with .name and .value
    attributes representing stuff that should be in <input
    type=hidden> tags with the link parameters."""

    url, params = apply(self.get_link, (), args)
    action = self.server.escape(urllib.quote(url, _URL_SAFE_CHARS))
    hidden_values = []
    for name, value in params.items():
      hidden_values.append(_item(name=self.server.escape(name),
                                 value=self.server.escape(value)))
    return action, hidden_values

  def get_link(self, view_func=None, where=None, pathtype=None, params=None):
    """Constructs a link pointing to another ViewVC page. All arguments
    correspond to members of the Request object. If they are set to 
    None they take values from the current page. Return value is a base
    URL and a dictionary of parameters"""

    cfg = self.cfg

    if view_func is None:
      view_func = self.view_func

    if params is None:
      params = self.query_dict.copy()
    else:
      params = params.copy()
      
    # must specify both where and pathtype or neither
    assert (where is None) == (pathtype is None)

    # if we are asking for the revision info view, we don't need any
    # path information
    if (view_func is view_revision or view_func is view_roots
        or view_func is redirect_pathrev):
      where = pathtype = None
    elif where is None:
      where = self.where
      pathtype = self.pathtype

    # no need to add sticky variables for views with no links
    sticky_vars = not (view_func is view_checkout 
                       or view_func is download_tarball)

    # The logic used to construct the URL is an inverse of the
    # logic used to interpret URLs in Request.run_viewvc

    url = self.script_name

    # add checkout magic if neccessary
    if view_func is view_checkout and cfg.options.checkout_magic:
      url = url + '/' + checkout_magic_path

    # add root to url
    rootname = None
    if view_func is not view_roots:
      if cfg.options.root_as_url_component:
        # remove root from parameter list if present
        try:
          rootname = params['root']
        except KeyError:
          rootname = self.rootname
        else:
          del params['root']

        # add root path component
        if rootname is not None:
          url = url + '/' + rootname

      else:
        # add root to parameter list
        try:
          rootname = params['root']
        except KeyError:
          rootname = params['root'] = self.rootname

        # no need to specify default root
        if rootname == cfg.general.default_root:
          del params['root']   

    # add 'pathrev' value to parameter list
    if (self.pathrev is not None
        and not params.has_key('pathrev')
        and view_func is not view_revision
        and rootname == self.rootname):
      params['pathrev'] = self.pathrev

    # add path
    if where:
      url = url + '/' + where

    # add trailing slash for a directory
    if pathtype == vclib.DIR:
      url = url + '/'

    # normalize top level URLs for use in Location headers and A tags
    elif not url:
      url = '/'

    # no need to explicitly specify directory view for a directory
    if view_func is view_directory and pathtype == vclib.DIR:
      view_func = None

    # no need to explicitly specify roots view when in root_as_url
    # mode or there's no default root
    if view_func is view_roots and (cfg.options.root_as_url_component
                                    or not cfg.general.default_root):
      view_func = None

    # no need to explicitly specify annotate view when
    # there's an annotate parameter
    if view_func is view_annotate and params.get('annotate') is not None:
      view_func = None

    # no need to explicitly specify diff view when
    # there's r1 and r2 parameters
    if (view_func is view_diff and params.get('r1') is not None
        and params.get('r2') is not None):
      view_func = None

    # no need to explicitly specify checkout view when it's the default
    # view or when checkout_magic is enabled
    if view_func is view_checkout:
      if ((cfg.options.default_file_view == "co" and pathtype == vclib.FILE)
          or cfg.options.checkout_magic):
        view_func = None

    # no need to explicitly specify markup view when it's the default view
    if view_func is view_markup:
      if (cfg.options.default_file_view == "markup" \
          and pathtype == vclib.FILE):
        view_func = None

    # set the view parameter
    view_code = _view_codes.get(view_func)
    if view_code and not (params.has_key('view') and params['view'] is None):
      params['view'] = view_code

    # add sticky values to parameter list
    if sticky_vars:
      for name in _sticky_vars:
        value = self.query_dict.get(name)
        if value is not None and not params.has_key(name):
          params[name] = value

    # remove null values from parameter list
    for name, value in params.items():
      if value is None:
        del params[name]

    return url, params

def _path_parts(path):
  """Split up a repository path into a list of path components"""
  # clean it up. this removes duplicate '/' characters and any that may
  # exist at the front or end of the path.
  return filter(None, string.split(path, '/'))

def _normalize_path(path):
  """Collapse leading slashes in the script name

  You only get multiple slashes in the script name when users accidentally
  type urls like http://abc.com//viewvc.cgi/, but we correct for it
  because we output the script name in links and web browsers
  interpret //viewvc.cgi/ as http://viewvc.cgi/
  """
  
  i = 0
  for c in path:
    if c != '/':
      break
    i = i + 1

  if i:
    return path[i-1:]

  return path

def _validate_param(name, value):
  """Validate whether the given value is acceptable for the param name.

  If the value is not allowed, then an error response is generated, and
  this function throws an exception. Otherwise, it simply returns None.
  """

  # First things first -- check that we have a legal parameter name.
  try:
    validator = _legal_params[name]
  except KeyError:
    raise debug.ViewVCException(
      'An illegal parameter name was provided.',
      '400 Bad Request')

  # Is there a validator?  Is it a regex or a function?  Validate if
  # we can, returning without incident on valid input.
  if validator is None:
    return
  elif hasattr(validator, 'match'):
    if validator.match(value):
      return
  else:
    if validator(value):
      return

  # If we get here, the input value isn't valid.
  raise debug.ViewVCException(
    'An illegal value was provided for the "%s" parameter.' % (name),
    '400 Bad Request')

def _validate_regex(value):
  ### we need to watch the flow of these parameters through the system
  ### to ensure they don't hit the page unescaped. otherwise, these
  ### parameters could constitute a CSS attack.
  try:
    re.compile(value)
    return True
  except:
    return None

def _validate_view(value):
  # Return true iff VALUE is one of our allowed views.
  return _views.has_key(value)

def _validate_mimetype(value):
  # For security purposes, we only allow mimetypes from a predefined set
  # thereof.
  return value in (viewcvs_mime_type, alt_mime_type, 'text/plain')

# obvious things here. note that we don't need uppercase for alpha.
_re_validate_alpha = re.compile('^[a-z]+$')
_re_validate_number = re.compile('^[0-9]+$')
_re_validate_boolint = re.compile('^[01]$')

# when comparing two revs, we sometimes construct REV:SYMBOL, so ':' is needed
_re_validate_revnum = re.compile('^[-_.a-zA-Z0-9:~\\[\\]/]*$')

# date time values
_re_validate_datetime = re.compile(r'^(\d\d\d\d-\d\d-\d\d(\s+\d\d:\d\d'
                                   '(:\d\d)?)?)?$')

# the legal query parameters and their validation functions
_legal_params = {
  'root'          : None,
  'view'          : _validate_view,
  'search'        : _validate_regex,
  'p1'            : None,
  'p2'            : None,
  
  'hideattic'     : _re_validate_boolint,
  'limit_changes' : _re_validate_number,
  'sortby'        : _re_validate_alpha,
  'sortdir'       : _re_validate_alpha,
  'logsort'       : _re_validate_alpha,
  'diff_format'   : _re_validate_alpha,
  'pathrev'       : _re_validate_revnum,
  'dir_pagestart' : _re_validate_number,
  'log_pagestart' : _re_validate_number,
  'annotate'      : _re_validate_revnum,
  'graph'         : _re_validate_revnum,
  'makeimage'     : _re_validate_boolint,
  'r1'            : _re_validate_revnum,
  'tr1'           : _re_validate_revnum,
  'r2'            : _re_validate_revnum,
  'tr2'           : _re_validate_revnum,
  'revision'      : _re_validate_revnum,
  'content-type'  : _validate_mimetype,

  # for query
  'file_match'    : _re_validate_alpha,
  'branch_match'  : _re_validate_alpha,
  'who_match'     : _re_validate_alpha,
  'comment_match' : _re_validate_alpha,
  'dir'           : None,
  'file'          : None,
  'branch'        : None,
  'who'           : None,
  'comment'       : None,
  'querysort'     : _re_validate_alpha,
  'date'          : _re_validate_alpha,
  'hours'         : _re_validate_number,
  'mindate'       : _re_validate_datetime,
  'maxdate'       : _re_validate_datetime,
  'format'        : _re_validate_alpha,

  # for redirect_pathrev
  'orig_path'     : None,
  'orig_pathtype' : None,
  'orig_pathrev'  : None,
  'orig_view'     : None,

  # deprecated
  'parent'        : _re_validate_boolint,
  'rev'           : _re_validate_revnum,
  'tarball'       : _re_validate_boolint,
  'hidecvsroot'   : _re_validate_boolint,
  }

def _path_join(path_parts):
  return string.join(path_parts, '/')

def _strip_suffix(suffix, path_parts, rev, pathtype, repos, view_func):
  """strip the suffix from a repository path if the resulting path
  is of the specified type, otherwise return None"""
  if not path_parts:
    return None
  l = len(suffix)
  if path_parts[-1][-l:] == suffix:
    path_parts = path_parts[:]
    if len(path_parts[-1]) == l:
      del path_parts[-1]
    else:
      path_parts[-1] = path_parts[-1][:-l]
    t = _repos_pathtype(repos, path_parts, rev)
    if pathtype == t:
      return path_parts, t, view_func
  return None

def _repos_pathtype(repos, path_parts, rev):
  """Return the type of a repository path, or None if the path doesn't
  exist"""
  try:
    return repos.itemtype(path_parts, rev)
  except vclib.ItemNotFound:
    return None

def _orig_path(request, rev_param='revision', path_param=None):
  "Get original path of requested file at old revision before copies or moves"

  # The 'pathrev' variable is interpreted by nearly all ViewVC views to
  # provide a browsable snapshot of a repository at some point in its history.
  # 'pathrev' is a tag name for CVS repositories and a revision number for
  # Subversion repositories. It's automatically propagated between pages by
  # logic in the Request.get_link() function which adds it to links like a
  # sticky variable. When 'pathrev' is set, directory listings only include
  # entries that exist in the specified revision or tag. Similarly, log pages
  # will only show revisions preceding the point in history specified by
  # 'pathrev.' Markup, checkout, and annotate pages show the 'pathrev'
  # revision of files by default when no other revision is specified.
  #
  # In Subversion repositories, paths are always considered to refer to the
  # pathrev revision. For example, if there is a "circle.jpg" in revision 3,
  # which is renamed and modified as "square.jpg" in revision 4, the original
  # circle image is visible at the following URLs:
  #
  #     *checkout*/circle.jpg?pathrev=3
  #     *checkout*/square.jpg?revision=3
  #     *checkout*/square.jpg?revision=3&pathrev=4
  # 
  # Note that the following:
  #
  #     *checkout*/circle.jpg?rev=3
  #
  # now gets redirected to one of the following URLs:
  #
  #     *checkout*/circle.jpg?pathrev=3  (for Subversion)
  #     *checkout*/circle.jpg?revision=3  (for CVS)
  #
  rev = request.query_dict.get(rev_param, request.pathrev)
  path = request.query_dict.get(path_param, request.where)
  
  if rev is not None and hasattr(request.repos, '_getrev'):
    try:
      pathrev = request.repos._getrev(request.pathrev)
      rev = request.repos._getrev(rev)
    except vclib.InvalidRevision:
      raise debug.ViewVCException('Invalid revision', '404 Not Found')
    return _path_parts(request.repos.get_location(path, pathrev, rev)), rev
  return _path_parts(path), rev

def setup_authorizer(cfg, username, rootname=None):
  """Setup the authorizer.  If ROOTNAME is provided, assume that
  per-root options have not been overlayed.  Otherwise, assume they
  have (and fetch the authorizer for the configured root)."""
  
  if rootname is None:
    authorizer = cfg.options.authorizer
    params = cfg.get_authorizer_params()
  else:
    authorizer, params = cfg.get_authorizer_and_params_hack(rootname)

  # No configured authorizer?  No problem.
  if not authorizer:
    return None

  # First, try to load a module with the configured name.
  import imp
  fp = None
  try:
    try:
      fp, path, desc = imp.find_module("%s" % (authorizer), vcauth.__path__)
      my_auth = imp.load_module('viewvc', fp, path, desc)
    except ImportError:
      raise debug.ViewVCException(
        'Invalid authorizer (%s) specified for root "%s"' \
        % (authorizer, rootname),
        '500 Internal Server Error')
  finally:
    if fp:
      fp.close()

  # Finally, instantiate our Authorizer.
  return my_auth.ViewVCAuthorizer(username, params)

def check_freshness(request, mtime=None, etag=None, weak=0):
  cfg = request.cfg

  # See if we are supposed to disable etags (for debugging, usually)
  if not cfg.options.generate_etags:
    return 0
  
  request_etag = request_mtime = None
  if etag is not None:
    if weak:
      etag = 'W/"%s"' % etag
    else:
      etag = '"%s"' % etag
    request_etag = request.server.getenv('HTTP_IF_NONE_MATCH')
  if mtime is not None:
    try:
      request_mtime = request.server.getenv('HTTP_IF_MODIFIED_SINCE')
      request_mtime = rfc822.mktime_tz(rfc822.parsedate_tz(request_mtime))
    except:
      request_mtime = None

  # if we have an etag, use that for freshness checking.
  # if not available, then we use the last-modified time.
  # if not available, then the document isn't fresh.
  if etag is not None:
    isfresh = (request_etag == etag)
  elif mtime is not None:
    isfresh = (request_mtime >= mtime)
  else:
    isfresh = 0

  # require revalidation after the configured amount of time
  if cfg and cfg.options.http_expiration_time >= 0:
    expiration = compat.formatdate(time.time() +
                                   cfg.options.http_expiration_time)
    request.server.addheader('Expires', expiration)
    request.server.addheader('Cache-Control',
                             'max-age=%d' % cfg.options.http_expiration_time)

  if isfresh:
    request.server.header(status='304 Not Modified')
  else:
    if etag is not None:
      request.server.addheader('ETag', etag)
    if mtime is not None:
      request.server.addheader('Last-Modified', compat.formatdate(mtime))
  return isfresh

def get_view_template(cfg, view_name, language="en"):
  # See if the configuration specifies a template for this view.  If
  # not, use the default template path for this view.
  tname = vars(cfg.templates).get(view_name) or view_name + ".ezt"

  # Template paths are relative to the configurated template_dir (if
  # any, "templates" otherwise), so build the template path as such.
  tname = os.path.join(cfg.options.template_dir or "templates", tname)

  # Allow per-language template selection.
  tname = string.replace(tname, '%lang%', language)

  # Finally, construct the whole template path.
  tname = cfg.path(tname)

  debug.t_start('ezt-parse')
  template = ezt.Template(tname)
  debug.t_end('ezt-parse')

  return template

def get_writeready_server_file(request, content_type=None, encoding=None,
                               content_length=None):
  """Return a file handle to a response body stream, after outputting
  any queued special headers (on REQUEST.server) and (optionally) a
  'Content-Type' header whose value is CONTENT_TYPE and character set
  is ENCODING.

  If CONTENT_LENGTH is provided and compression is not in use, also
  generate a 'Content-Length' header for this response.

  After this function is called, it is too late to add new headers to
  the response."""

  if request.gzip_compress_level:
    request.server.addheader('Content-Encoding', 'gzip')
  elif content_length is not None:
    request.server.addheader('Content-Length', content_length)
  
  if content_type and encoding:
    request.server.header("%s; charset=%s" % (content_type, encoding))
  elif content_type:
    request.server.header(content_type)
  else:
    request.server.header()

  if request.gzip_compress_level:
    fp = gzip.GzipFile('', 'wb', request.gzip_compress_level,
                       request.server.file())
  else:
    fp = request.server.file()
  
  return fp
  
def generate_page(request, view_name, data, content_type=None):
  server_fp = get_writeready_server_file(request, content_type)
  template = get_view_template(request.cfg, view_name, request.language)
  template.generate(server_fp, data)

def nav_path(request):
  """Return current path as list of items with "name" and "href" members

  The href members are view_directory links for directories and view_log
  links for files, but are set to None when the link would point to
  the current view"""

  if not request.repos:
    return []

  is_dir = request.pathtype == vclib.DIR

  # add root item
  items = []
  root_item = _item(name=request.server.escape(request.repos.name), href=None)
  if request.path_parts or request.view_func is not view_directory:
    root_item.href = request.get_url(view_func=view_directory,
                                     where='', pathtype=vclib.DIR,
                                     params={}, escape=1)
  items.append(root_item)

  # add path part items
  path_parts = []
  for part in request.path_parts:
    path_parts.append(part)
    is_last = len(path_parts) == len(request.path_parts)

    item = _item(name=part, href=None)

    if not is_last or (is_dir and request.view_func is not view_directory):
      item.href = request.get_url(view_func=view_directory,
                                  where=_path_join(path_parts),
                                  pathtype=vclib.DIR,
                                  params={}, escape=1)
    elif not is_dir and request.view_func is not view_log:
      item.href = request.get_url(view_func=view_log,
                                  where=_path_join(path_parts),
                                  pathtype=vclib.FILE,
                                  params={}, escape=1)
    items.append(item)

  return items

def prep_tags(request, tags):
  url, params = request.get_link(params={'pathrev': None})
  params = compat.urlencode(params)
  if params:
    url = urllib.quote(url, _URL_SAFE_CHARS) + '?' + params + '&pathrev='
  else:
    url = urllib.quote(url, _URL_SAFE_CHARS) + '?pathrev='
  url = request.server.escape(url)

  links = [ ]
  for tag in tags:
    links.append(_item(name=tag.name, href=url+tag.name))
  links.sort(lambda a, b: cmp(a.name, b.name))
  return links

def guess_mime(filename):
  return mimetypes.guess_type(filename)[0]

def is_viewable_image(mime_type):
  return mime_type and mime_type in ('image/gif', 'image/jpeg', 'image/png')

def is_text(mime_type):
  return not mime_type or mime_type[:5] == 'text/'

def is_cvsroot_path(roottype, path_parts):
  return roottype == 'cvs' and path_parts and path_parts[0] == 'CVSROOT'

def is_plain_text(mime_type):
  return not mime_type or mime_type == 'text/plain'

def default_view(mime_type, cfg):
  "Determine whether file should be viewed through markup page or sent raw"
  # If the mime type is text/anything or a supported image format we view
  # through the markup page. If the mime type is something else, we send
  # it directly to the browser. That way users can see things like flash
  # animations, pdfs, word documents, multimedia, etc, which wouldn't be
  # very useful marked up. If the mime type is totally unknown (happens when
  # we encounter an unrecognized file extension) we also view it through
  # the markup page since that's better than sending it text/plain.
  if ('markup' in cfg.options.allowed_views and 
      (is_viewable_image(mime_type) or is_text(mime_type))):
    return view_markup
  return view_checkout

def get_file_view_info(request, where, rev=None, mime_type=None, pathrev=-1):
  """Return an object holding common hrefs and a viewability flag used
  for various views of FILENAME at revision REV whose MIME type is
  MIME_TYPE.

  The object's members include:
     view_href
     download_href
     download_text_href
     annotate_href
     revision_href
     prefer_markup
     
  """
  
  rev = rev and str(rev) or None
  mime_type = mime_type or guess_mime(where)
  if pathrev == -1: # cheesy default value, since we need to preserve None
    pathrev = request.pathrev

  view_href = None
  download_href = None
  download_text_href = None
  annotate_href = None
  revision_href = None

  if 'markup' in request.cfg.options.allowed_views:
    view_href = request.get_url(view_func=view_markup,
                                where=where,
                                pathtype=vclib.FILE,
                                params={'revision': rev,
                                        'pathrev': pathrev},
                                escape=1)
  if 'co' in request.cfg.options.allowed_views:
    download_href = request.get_url(view_func=view_checkout,
                                    where=where,
                                    pathtype=vclib.FILE,
                                    params={'revision': rev,
                                            'pathrev': pathrev},
                                    escape=1)
    if not is_plain_text(mime_type):
      download_text_href = request.get_url(view_func=view_checkout,
                                           where=where,
                                           pathtype=vclib.FILE,
                                           params={'content-type': 'text/plain',
                                                   'revision': rev,
                                                   'pathrev': pathrev},
                                           escape=1)
  if 'annotate' in request.cfg.options.allowed_views:
    annotate_href = request.get_url(view_func=view_annotate,
                                    where=where,
                                    pathtype=vclib.FILE,
                                    params={'annotate': rev,
                                            'pathrev': pathrev},
                                    escape=1)
  if request.roottype == 'svn':
    revision_href = request.get_url(view_func=view_revision,
                                    params={'revision': rev},
                                    escape=1)

  prefer_markup = default_view(mime_type, request.cfg) == view_markup

  return _item(view_href=view_href,
               download_href=download_href,
               download_text_href=download_text_href,
               annotate_href=annotate_href,
               revision_href=revision_href,
               prefer_markup=ezt.boolean(prefer_markup))


# Matches URLs
_re_rewrite_url = re.compile('((http|https|ftp|file|svn|svn\+ssh)'
                             '(://[-a-zA-Z0-9%.~:_/]+)((\?|\&)'
                             '([-a-zA-Z0-9%.~:_]+)=([-a-zA-Z0-9%.~:_])+)*'
                             '(#([-a-zA-Z0-9%.~:_]+)?)?)')
# Matches email addresses
_re_rewrite_email = re.compile('([-a-zA-Z0-9_.\+]+)@'
                               '(([-a-zA-Z0-9]+\.)+[A-Za-z]{2,4})')

# Matches revision references
_re_rewrite_svnrevref = re.compile(r'\b(r|rev #?|revision #?)([0-9]+)\b')

class ViewVCHtmlFormatter:
  """Format a string as HTML-encoded output with customizable markup
  rules, for example turning strings that look like URLs into anchor links.

  NOTE:  While there might appear to be some unused portions of this
  interface, there is a good chance that there are consumers outside
  of ViewVC itself that make use of these things.
  """
  
  def __init__(self):
    self._formatters = []

  def format_url(self, mobj, userdata, maxlen=0):
    """Return a 2-tuple containing:
         - the text represented by MatchObject MOBJ, formatted as
           linkified URL, with no more than MAXLEN characters in the
           non-HTML-tag bits.  If MAXLEN is 0, there is no maximum.
         - the number of non-HTML-tag characters returned.
    """
    s = mobj.group(0)
    trunc_s = maxlen and s[:maxlen] or s
    return '<a href="%s">%s</a>' % (sapi.escape(s),
                                    sapi.escape(trunc_s)), \
           len(trunc_s)

  def format_email(self, mobj, userdata, maxlen=0):
    """Return a 2-tuple containing:
         - the text represented by MatchObject MOBJ, formatted as
           linkified email address, with no more than MAXLEN characters
           in the non-HTML-tag bits.  If MAXLEN is 0, there is no maximum.
         - the number of non-HTML-tag characters returned.
    """
    s = mobj.group(0)
    trunc_s = maxlen and s[:maxlen] or s
    return '<a href="mailto:%s">%s</a>' % (urllib.quote(s),
                                           self._entity_encode(trunc_s)), \
           len(trunc_s)

  def format_email_obfuscated(self, mobj, userdata, maxlen=0):
    """Return a 2-tuple containing:
         - the text represented by MatchObject MOBJ, formatted as an
           entity-encoded email address, with no more than MAXLEN characters
           in the non-HTML-tag bits.  If MAXLEN is 0, there is no maximum.
         - the number of non-HTML-tag characters returned.
    """    
    s = mobj.group(0)
    trunc_s = maxlen and s[:maxlen] or s
    return self._entity_encode(trunc_s), len(trunc_s)

  def format_email_truncated(self, mobj, userdata, maxlen=0):
    """Return a 2-tuple containing:
         - the text represented by MatchObject MOBJ, formatted as an
           HTML-escaped truncated email address of no more than MAXLEN
           characters.  If MAXLEN is 0, there is no maximum.
         - the number of characters returned.
    """
    s = mobj.group(1)
    s_len = len(s)
    if (maxlen == 0) or (s_len < (maxlen - 1)):
      return self._entity_encode(s) + '&#64;&hellip;', s_len + 2
    elif s_len < maxlen:
      return self._entity_encode(s) + '&#64;', s_len + 1
    else:
      trunc_s = mobj.group(1)[:maxlen]
      return self._entity_encode(trunc_s), len(trunc_s)

  def format_svnrevref(self, mobj, userdata, maxlen=0):
    """Return a 2-tuple containing:
         - the text represented by MatchObject MOBJ, formatted as an
           linkified URL to a ViewVC Subversion revision view, with no
           more than MAXLEN characters in the non-HTML-tag portions.
           If MAXLEN is 0, there is no maximum.
         - the number of characters returned.

       USERDATA is a function that accepts a revision reference
       and returns a URL to that revision.
    """
    s = mobj.group(0)
    revref = mobj.group(2)
    trunc_s = maxlen and s[:maxlen] or s
    revref_url = userdata(revref)
    return '<a href="%s">%s</a>' % (sapi.escape(revref_url),
                                    sapi.escape(trunc_s)), \
           len(trunc_s)

  def format_text(self, s, unused, maxlen=0):
    """Return a 2-tuple containing:
         - the text S, HTML-escaped, containing no more than MAXLEN
           characters.  If MAXLEN is 0, there is no maximum.
         - the number of characters returned.
    """   
    trunc_s = maxlen and s[:maxlen] or s
    return sapi.escape(trunc_s), len(trunc_s)
  
  def add_formatter(self, regexp, conv, userdata=None):
    """Register a formatter which finds instances of strings matching
    REGEXP, and using the function CONV and USERDATA to format them.

    CONV is a function which accepts three parameters:
      - the MatchObject which holds the string portion to be formatted,
      - the USERDATA object,
      - the maximum number of characters from that string to use for
        human-readable output (or 0 to indicate no maximum).
    """
    if type(regexp) == type(''):
      regexp = re.compile(regexp)
    self._formatters.append([regexp, conv, userdata])

  def get_result(self, s, maxlen=0):
    """Format S per the set of formatters registered with this object,
    and limited to MAXLEN visible characters (or unlimited if MAXLEN
    is 0).  Return a 3-tuple containing the formatted result string,
    the number of visible characters in the result string, and a
    boolean flag indicating whether or not S was truncated.
    """
    out = ''
    out_len = 0
    for token in self._tokenize_text(s):
      chunk, chunk_len = token.converter(token.match, token.userdata, maxlen)
      out = out + chunk
      out_len = out_len + chunk_len
      if maxlen:
        maxlen = maxlen - chunk_len
        if maxlen <= 0:
          return out, out_len, 1
    return out, out_len, 0

  def _entity_encode(self, s):
    return string.join(map(lambda x: '&#%d;' % (ord(x)), s), '')

  def _tokenize_text(self, s):
    tokens = []
    # We could just have a "while s:" here instead of "for line: while
    # line:", but for really large log messages with heavy
    # tokenization, the cost in both performance and memory
    # consumption of the approach taken was atrocious.
    for line in string.split(string.replace(s, '\r\n', '\n'), '\n'):
      line = line + '\n'
      while line:
        best_match = best_conv = best_userdata = None
        for test in self._formatters:
          match = test[0].search(line)
          # If we find and match and (a) its our first one, or (b) it
          # matches text earlier than our previous best match, or (c) it
          # matches text at the same location as our previous best match
          # but extends to cover more text than that match, then this is
          # our new best match.
          #
          # Implied here is that when multiple formatters match exactly
          # the same text, the first formatter in the registration list wins.
          if match \
             and ((best_match is None) \
                  or (match.start() < best_match.start())
                  or ((match.start() == best_match.start()) \
                      and (match.end() > best_match.end()))):
            best_match = match
            best_conv = test[1]
            best_userdata = test[2]
        # If we found a match...
        if best_match:
          # ... add any non-matching stuff first, then the matching bit.
          start = best_match.start()
          end = best_match.end()
          if start > 0:
            tokens.append(_item(match=line[:start],
                                converter=self.format_text,
                                userdata=None))
          tokens.append(_item(match=best_match,
                              converter=best_conv,
                              userdata=best_userdata))
          line = line[end:]
        else:
          # Otherwise, just add the rest of the string.
          tokens.append(_item(match=line,
                              converter=self.format_text,
                              userdata=None))
          line = ''
    return tokens


def format_log(request, log, maxlen=0, htmlize=1):
  if not log:
    return log

  cfg = request.cfg
  if htmlize:
    lf = ViewVCHtmlFormatter()
    lf.add_formatter(_re_rewrite_url, lf.format_url)
    if request.roottype == 'svn':
      def revision_to_url(rev):
        return request.get_url(view_func=view_revision,
                               params={'revision': rev},
                               escape=1)
      lf.add_formatter(_re_rewrite_svnrevref, lf.format_svnrevref,
                       revision_to_url)
    if cfg.options.mangle_email_addresses == 2:
      lf.add_formatter(_re_rewrite_email, lf.format_email_truncated)
    elif cfg.options.mangle_email_addresses == 1:
      lf.add_formatter(_re_rewrite_email, lf.format_email_obfuscated)
    else:
      lf.add_formatter(_re_rewrite_email, lf.format_email)
    log, log_len, truncated = lf.get_result(log, maxlen)
    return log + (truncated and '&hellip;' or '')
  else:
    if cfg.options.mangle_email_addresses == 2:
      log = re.sub(_re_rewrite_email, r'\1@...', log)
    return maxlen and log[:maxlen] or log

_time_desc = {
         1 : 'second',
        60 : 'minute',
      3600 : 'hour',
     86400 : 'day',
    604800 : 'week',
   2628000 : 'month',
  31536000 : 'year',
  }

def get_time_text(request, interval, num):
  "Get some time text, possibly internationalized."
  ### some languages have even harder pluralization rules. we'll have to
  ### deal with those on demand
  if num == 0:
    return ''
  text = _time_desc[interval]
  if num == 1:
    attr = text + '_singular'
    fmt = '%d ' + text
  else:
    attr = text + '_plural'
    fmt = '%d ' + text + 's'
  try:
    fmt = getattr(request.kv.i18n.time, attr)
  except AttributeError:
    pass
  return fmt % num

def little_time(request):
  try:
    return request.kv.i18n.time.little_time
  except AttributeError:
    return 'very little time'

def html_time(request, secs, extended=0):
  secs = long(time.time()) - secs
  if secs < 2:
    return little_time(request)
  breaks = _time_desc.keys()
  breaks.sort()
  i = 0
  while i < len(breaks):
    if secs < 2 * breaks[i]:
      break
    i = i + 1
  value = breaks[i - 1]
  s = get_time_text(request, value, secs / value)

  if extended and i > 1:
    secs = secs % value
    value = breaks[i - 2]
    ext = get_time_text(request, value, secs / value)
    if ext:
      ### this is not i18n compatible. pass on it for now
      s = s + ', ' + ext
  return s

def common_template_data(request, revision=None, mime_type=None):
  """Return a ezt.TemplateData instance with data dictionary items
  common to most ViewVC views."""
  
  cfg = request.cfg

  # Initialize data dictionary members (sorted alphanumerically)
  data = ezt.TemplateData({
    'annotate_href' : None,
    'cfg' : cfg,
    'docroot' : cfg.options.docroot is None \
                and request.script_name + '/' + docroot_magic_path \
                or cfg.options.docroot,
    'download_href' : None,
    'download_text_href' : None,
    'graph_href': None,
    'kv'  : request.kv,
    'lockinfo' : None,
    'log_href' : None,
    'nav_path' : nav_path(request),
    'pathtype' : None,
    'prefer_markup' : ezt.boolean(0),
    'queryform_href' : None,
    'rev'      : None,
    'revision_href' : None,
    'rootname' : request.rootname \
                 and request.server.escape(request.rootname) or None,
    'rootpath' : request.rootpath,
    'roots_href' : None,
    'roottype' : request.roottype,
    'rss_href' : None,
    'tarball_href' : None,
    'up_href'  : None,
    'username' : request.username,
    'view'     : _view_codes[request.view_func],
    'view_href' : None,
    'vsn' : __version__,
    'where' : request.server.escape(request.where),
  })

  rev = revision
  if not rev:
    rev = request.query_dict.get('annotate')
  if not rev:
    rev = request.query_dict.get('revision')
  if not rev and request.roottype == 'svn':
    rev = request.query_dict.get('pathrev')
  try:
    data['rev'] = hasattr(request.repos, '_getrev') \
                  and request.repos._getrev(rev) or rev
  except vclib.InvalidRevision:
    raise debug.ViewVCException('Invalid revision', '404 Not Found')

  if request.pathtype == vclib.DIR:
    data['pathtype'] = 'dir'
  elif request.pathtype == vclib.FILE:
    data['pathtype'] = 'file'

  if request.path_parts:
    dir = _path_join(request.path_parts[:-1])
    data['up_href'] = request.get_url(view_func=view_directory,
                                      where=dir, pathtype=vclib.DIR,
                                      params={}, escape=1)

  if 'roots' in cfg.options.allowed_views:
    data['roots_href'] = request.get_url(view_func=view_roots,
                                         escape=1, params={})

  if request.pathtype == vclib.FILE:
    fvi = get_file_view_info(request, request.where, data['rev'], mime_type)
    data['view_href'] = fvi.view_href
    data['download_href'] = fvi.download_href
    data['download_text_href'] = fvi.download_text_href
    data['annotate_href'] = fvi.annotate_href
    data['revision_href'] = fvi.revision_href
    data['prefer_markup'] = fvi.prefer_markup
    data['log_href'] = request.get_url(view_func=view_log, params={}, escape=1)
    if request.roottype == 'cvs' and cfg.options.use_cvsgraph:
      data['graph_href'] = request.get_url(view_func=view_cvsgraph,
                                           params={}, escape=1)
    file_data = request.repos.listdir(request.path_parts[:-1],
                                      request.pathrev, {})
    def _only_this_file(item):
      return item.name == request.path_parts[-1]
    entries = filter(_only_this_file, file_data)
    if len(entries) == 1:
      request.repos.dirlogs(request.path_parts[:-1], request.pathrev,
                            entries, {})
      data['lockinfo'] = entries[0].lockinfo
  elif request.pathtype == vclib.DIR:
    data['view_href'] = request.get_url(view_func=view_directory,
                                       params={}, escape=1)
    if 'tar' in cfg.options.allowed_views:
      data['tarball_href'] = request.get_url(view_func=download_tarball, 
                                             params={},
                                             escape=1)
    if request.roottype == 'svn':
      data['revision_href'] = request.get_url(view_func=view_revision,
                                              params={'revision': data['rev']},
                                              escape=1)

      data['log_href'] = request.get_url(view_func=view_log,
                                         params={}, escape=1)

  if is_querydb_nonempty_for_root(request):
    if request.pathtype == vclib.DIR:
      params = {}
      if request.roottype == 'cvs' and request.pathrev:
        params['branch'] = request.pathrev
      data['queryform_href'] = request.get_url(view_func=view_queryform,
                                               params=params,
                                               escape=1)
      data['rss_href'] = request.get_url(view_func=view_query,
                                         params={'date': 'month',
                                                 'format': 'rss'},
                                         escape=1)
    elif request.pathtype == vclib.FILE:
      parts = _path_parts(request.where)
      where = _path_join(parts[:-1])
      data['rss_href'] = request.get_url(view_func=view_query,
                                         where=where,
                                         pathtype=request.pathtype,
                                         params={'date': 'month',
                                                 'format': 'rss',
                                                 'file': parts[-1],
                                                 'file_match': 'exact'},
                                         escape=1)
  return data

def retry_read(src, reqlen=CHUNK_SIZE):
  while 1:
    chunk = src.read(CHUNK_SIZE)
    if not chunk:
      # need to check for eof methods because the cStringIO file objects
      # returned by ccvs don't provide them
      if hasattr(src, 'eof') and src.eof() is None:
        time.sleep(1)
        continue
    return chunk
  
def copy_stream(src, dst, htmlize=0):
  while 1:
    chunk = retry_read(src)
    if not chunk:
      break
    if htmlize:
      chunk = sapi.escape(chunk)
    dst.write(chunk)

class MarkupPipeWrapper:
  """An EZT callback that outputs a filepointer, plus some optional
  pre- and post- text."""

  def __init__(self, fp, pretext=None, posttext=None, htmlize=0):
    self.fp = fp
    self.pretext = pretext
    self.posttext = posttext
    self.htmlize = htmlize

  def __call__(self, ctx):
    if self.pretext:
      ctx.fp.write(self.pretext)
    copy_stream(self.fp, ctx.fp, self.htmlize)
    self.fp.close()
    if self.posttext:
      ctx.fp.write(self.posttext)

_re_rewrite_escaped_url = re.compile('((http|https|ftp|file|svn|svn\+ssh)'
                                     '(://[-a-zA-Z0-9%.~:_/]+)'
                                     '((\?|\&amp;amp;|\&amp;|\&)'
                                     '([-a-zA-Z0-9%.~:_]+)=([-a-zA-Z0-9%.~:_])+)*'
                                     '(#([-a-zA-Z0-9%.~:_]+)?)?)')

def markup_escaped_urls(s):
  # Return a copy of S with all URL references -- which are expected
  # to be already HTML-escaped -- wrapped in <a href=""></a>.
  def _url_repl(match_obj):
    url = match_obj.group(0)
    unescaped_url = string.replace(url, "&amp;amp;", "&amp;")
    return "<a href=\"%s\">%s</a>" % (unescaped_url, url)
  return re.sub(_re_rewrite_escaped_url, _url_repl, s)

def markup_stream_pygments(request, cfg, blame_data, fp, filename,
                           mime_type, encoding):
  # Determine if we should use Pygments to highlight our output.
  # Reasons not to include a) being told not to by the configuration,
  # b) not being able to import the Pygments modules, and c) Pygments
  # not having a lexer for our file's format.
  blame_source = []
  if blame_data:
    for i in blame_data:
      i.text = sapi.escape(i.text)
      i.diff_href = None
      if i.prev_rev:
        i.diff_href = request.get_url(view_func=view_diff,
                                      params={'r1': i.prev_rev,
                                              'r2': i.rev},
                                      escape=1, partial=1)
      blame_source.append(i)
    blame_data = blame_source
  lexer = None
  use_pygments = cfg.options.enable_syntax_coloration
  try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import ClassNotFound, \
                                get_lexer_by_name, \
                                get_lexer_for_mimetype, \
                                get_lexer_for_filename
    if not encoding:
      encoding = 'guess'
      if cfg.options.detect_encoding:
        try:
          import chardet
          encoding = 'chardet'
        except (SyntaxError, ImportError):
          pass
    try:
      lexer = get_lexer_for_mimetype(mime_type,
                                     encoding=encoding,
                                     tabsize=cfg.options.tabsize,
                                     stripnl=False)
    except ClassNotFound:
      try:
        lexer = get_lexer_for_filename(filename,
                                       encoding=encoding,
                                       tabsize=cfg.options.tabsize,
                                       stripnl=False)
      except ClassNotFound:
        use_pygments = 0
  except ImportError:
    use_pygments = 0

  # If we aren't going to be highlighting anything, just return the
  # BLAME_SOURCE.  If there's no blame_source, we'll generate a fake
  # one from the file contents we fetch with PATH and REV.
  if not use_pygments:
    if blame_source:
      class BlameSourceTabsizeWrapper:
        def __init__(self, blame_source, tabsize):
          self.blame_source = blame_source
          self.tabsize = cfg.options.tabsize
        def __getitem__(self, idx):
          item = self.blame_source.__getitem__(idx)
          item.text = string.expandtabs(item.text, self.tabsize)
          item.text = markup_escaped_urls(item.text)
          return item
      return BlameSourceTabsizeWrapper(blame_source, cfg.options.tabsize)
    else:
      lines = []
      line_no = 0
      while 1:
        line = fp.readline()
        if not line:
          break
        line_no = line_no + 1
        line = sapi.escape(string.expandtabs(line, cfg.options.tabsize))
        line = markup_escaped_urls(line)
        item = vclib.Annotation(line, line_no, None, None, None, None)
        item.diff_href = None
        lines.append(item)
    return lines

  # If we get here, we're highlighting something.
  class PygmentsSink:
    def __init__(self, blame_data):
      if blame_data:
        self.has_blame_data = 1
        self.blame_data = blame_data
      else:
        self.has_blame_data = 0
        self.blame_data = []
      self.line_no = 0
    def write(self, buf):
      ### FIXME:  Don't bank on write() being called once per line
      buf = markup_escaped_urls(buf)
      if self.has_blame_data:
        self.blame_data[self.line_no].text = buf
      else:
        item = vclib.Annotation(buf, self.line_no + 1,
                                None, None, None, None)
        item.diff_href = None
        self.blame_data.append(item)
      self.line_no = self.line_no + 1
  ps = PygmentsSink(blame_source)
  highlight(fp.read(), lexer,
            HtmlFormatter(nowrap=True,
                          classprefix="pygments-",
                          encoding='utf-8'), ps)
  return ps.blame_data

def make_time_string(date, cfg):
  """Returns formatted date string in either local time or UTC.

  The passed in 'date' variable is seconds since epoch.

  """
  if date is None:
    return None
  if cfg.options.use_localtime:
    localtime = time.localtime(date)
    return time.asctime(localtime) + ' ' + time.tzname[localtime[8]]
  else:
    return time.asctime(time.gmtime(date)) + ' UTC'

def make_rss_time_string(date, cfg):
  """Returns formatted date string in UTC, formatted for RSS.

  The passed in 'date' variable is seconds since epoch.

  """
  if date is None:
    return None
  return time.strftime("%a, %d %b %Y %H:%M:%S", time.gmtime(date)) + ' UTC'

def make_comma_sep_list_string(items):
  return string.join(map(lambda x: x.name, items), ', ')

def get_itemprops(request, path_parts, rev):
  itemprops = request.repos.itemprops(path_parts, rev)
  propnames = itemprops.keys()
  propnames.sort()
  props = []
  for name in propnames:
    value = format_log(request, itemprops[name])
    undisplayable = ezt.boolean(0)
    # skip non-utf8 property names
    try:
      unicode(name, 'utf8')
    except:
      continue
    # note non-utf8 property values
    try:
      unicode(value, 'utf8')
    except:
      value = None
      undisplayable = ezt.boolean(1)
    props.append(_item(name=name, value=value, undisplayable=undisplayable))
  return props

def parse_mime_type(mime_type):
  mime_parts = map(lambda x: x.strip(), string.split(mime_type, ';'))
  type_subtype = mime_parts[0].lower()
  parameters = {}
  for part in mime_parts[1:]:
    name, value = string.split(part, '=', 1)
    parameters[name] = value
  return type_subtype, parameters
  
def calculate_mime_type(request, path_parts, rev):
  """Return a 2-tuple carrying the MIME content type and character
  encoding for the file represented by PATH_PARTS in REV.  Use REQUEST
  for repository access as necessary."""
  if not path_parts:
    return None, None
  mime_type = encoding = None
  if request.roottype == 'svn' \
     and (not request.cfg.options.svn_ignore_mimetype):
    try:
      itemprops = request.repos.itemprops(path_parts, rev)
      mime_type = itemprops.get('svn:mime-type')
      if mime_type:
        mime_type, parameters = parse_mime_type(mime_type)
        return mime_type, parameters.get('charset')
    except:
      pass
  return guess_mime(path_parts[-1]), None

def markup_or_annotate(request, is_annotate):
  cfg = request.cfg
  path, rev = _orig_path(request, is_annotate and 'annotate' or 'revision')
  lines = fp = image_src_href = None
  annotation = 'none'
  revision = None
  mime_type, encoding = calculate_mime_type(request, path, rev)

  # Is this a viewable image type?
  if is_viewable_image(mime_type) \
     and 'co' in cfg.options.allowed_views:
    fp, revision = request.repos.openfile(path, rev, {})
    fp.close()
    if check_freshness(request, None, revision, weak=1):
      return
    annotation = 'binary'
    image_src_href = request.get_url(view_func=view_checkout,
                                     params={'revision': rev}, escape=1)

  # Not a viewable image.
  else:
    blame_source = None
    if is_annotate:
      # Try to annotate this file, but don't croak if we fail.
      try:
        blame_source, revision = request.repos.annotate(path, rev)
        annotation = 'annotated'
        if check_freshness(request, None, revision, weak=1):
          return
      except vclib.NonTextualFileContents:
        annotation = 'binary'
      except:
        annotation = 'error'

    fp, revision = request.repos.openfile(path, rev, {'cvs_oldkeywords' : 1})
    if check_freshness(request, None, revision, weak=1):
      fp.close()
      return
    lines = markup_stream_pygments(request, cfg, blame_source, fp,
                                   path[-1], mime_type, encoding)
    fp.close()

  data = common_template_data(request, revision)
  data.merge(ezt.TemplateData({
    'mime_type' : mime_type,
    'log' : None,
    'date' : None,
    'ago' : None,
    'author' : None,
    'branches' : None,
    'tags' : None,
    'branch_points' : None,
    'changed' : None,
    'size' : None,
    'state' : None,
    'vendor_branch' : None,
    'prev' : None,
    'orig_path' : None,
    'orig_href' : None,
    'image_src_href' : image_src_href,
    'lines' : lines,
    'properties' : get_itemprops(request, path, rev),
    'annotation' : annotation,
    }))

  if cfg.options.show_log_in_markup:
    options = {'svn_latest_log': 1}  ### FIXME: No longer needed?
    revs = request.repos.itemlog(path, revision, vclib.SORTBY_REV,
                                 0, 1, options)
    entry = revs[-1]
    data['date'] = make_time_string(entry.date, cfg)
    data['author'] = entry.author
    data['changed'] = entry.changed
    data['log'] = format_log(request, entry.log)
    data['size'] = entry.size

    if entry.date is not None:
      data['ago'] = html_time(request, entry.date, 1)

    if request.roottype == 'cvs':
      branch = entry.branch_number
      prev = entry.prev or entry.parent
      data['state'] = entry.dead and 'dead'
      data['prev'] = prev and prev.string
      data['vendor_branch'] = ezt.boolean(branch and branch[2] % 2 == 1)

      ### TODO:  Should this be using prep_tags() instead?
      data['branches'] = make_comma_sep_list_string(entry.branches)
      data['tags'] = make_comma_sep_list_string(entry.tags)
      data['branch_points']= make_comma_sep_list_string(entry.branch_points)

  if path != request.path_parts:
    orig_path = _path_join(path)
    data['orig_path'] = orig_path
    data['orig_href'] = request.get_url(view_func=view_log,
                                        where=orig_path,
                                        pathtype=vclib.FILE,
                                        params={'pathrev': revision},
                                        escape=1)
    
  generate_page(request, "file", data)
  
def view_markup(request):
  if 'markup' not in request.cfg.options.allowed_views:
    raise debug.ViewVCException('Markup view is disabled',
                                '403 Forbidden')
  if request.pathtype != vclib.FILE:
    raise debug.ViewVCException('Unsupported feature: markup view on '
                                'directory', '400 Bad Request')
  markup_or_annotate(request, 0)

def view_annotate(request):
  if 'annotate' not in request.cfg.options.allowed_views:
    raise debug.ViewVCException('Annotation view is disabled',
                                 '403 Forbidden')
  if request.pathtype != vclib.FILE:
    raise debug.ViewVCException('Unsupported feature: annotate view on '
                                'directory', '400 Bad Request')
  markup_or_annotate(request, 1)

def revcmp(rev1, rev2):
  rev1 = map(int, string.split(rev1, '.'))
  rev2 = map(int, string.split(rev2, '.'))
  return cmp(rev1, rev2)

def sort_file_data(file_data, roottype, sortdir, sortby, group_dirs):
  # convert sortdir into a sign bit
  s = sortdir == "down" and -1 or 1

  # in cvs, revision numbers can't be compared meaningfully between
  # files, so try to do the right thing and compare dates instead
  if roottype == "cvs" and sortby == "rev":
    sortby = "date"

  def file_sort_cmp(file1, file2, sortby=sortby, group_dirs=group_dirs, s=s):
    # if we're grouping directories together, sorting is pretty
    # simple.  a directory sorts "higher" than a non-directory, and
    # two directories are sorted as normal.
    if group_dirs:
      if file1.kind == vclib.DIR:
        if file2.kind == vclib.DIR:
          # two directories, no special handling.
          pass
        else:
          # file1 is a directory, it sorts first.
          return -1
      elif file2.kind == vclib.DIR:
        # file2 is a directory, it sorts first.
        return 1

    # we should have data on these. if not, then it is because we requested
    # a specific tag and that tag is not present on the file.
    if file1.rev is not None and file2.rev is not None:
      # sort according to sortby
      if sortby == 'rev':
        return s * revcmp(file1.rev, file2.rev)
      elif sortby == 'date':
        return s * cmp(file2.date, file1.date)        # latest date is first
      elif sortby == 'log':
        return s * cmp(file1.log, file2.log)
      elif sortby == 'author':
        return s * cmp(file1.author, file2.author)
    elif file1.rev is not None:
      return -1
    elif file2.rev is not None:
      return 1

    # sort by file name
    return s * cmp(file1.name, file2.name)

  file_data.sort(file_sort_cmp)

def icmp(x, y):
  """case insensitive comparison"""
  return cmp(string.lower(x), string.lower(y))

def view_roots(request):
  if 'roots' not in request.cfg.options.allowed_views:
    raise debug.ViewVCException('Root listing view is disabled',
                                '403 Forbidden')
  
  # add in the roots for the selection
  roots = []
  expand_root_parents(request.cfg)
  allroots = list_roots(request)
  if len(allroots):
    rootnames = allroots.keys()
    rootnames.sort(icmp)
    for rootname in rootnames:
      href = request.get_url(view_func=view_directory,
                             where='', pathtype=vclib.DIR,
                             params={'root': rootname}, escape=1)
      lastmod = allroots[rootname][2]
      roots.append(_item(name=request.server.escape(rootname),
                         type=allroots[rootname][1],
                         path=allroots[rootname][0],
                         author=lastmod and lastmod.author or None,
                         ago=lastmod and lastmod.ago or None,
                         date=lastmod and lastmod.date or None,
                         log=lastmod and lastmod.log or None,
                         short_log=lastmod and lastmod.short_log or None,
                         rev=lastmod and lastmod.rev or None,
                         href=href))

  data = common_template_data(request)
  data.merge(ezt.TemplateData({
    'roots' : roots,
    }))
  generate_page(request, "roots", data)

def view_directory(request):
  cfg = request.cfg

  # For Subversion repositories, the revision acts as a weak validator for
  # the directory listing (to take into account template changes or
  # revision property changes).
  if request.roottype == 'svn':
    try:
      rev = request.repos._getrev(request.pathrev)
    except vclib.InvalidRevision:
      raise debug.ViewVCException('Invalid revision', '404 Not Found')
    tree_rev = request.repos.created_rev(request.where, rev)
    if check_freshness(request, None, str(tree_rev), weak=1):
      return

  # List current directory
  options = {}
  if request.roottype == 'cvs':
    hideattic = int(request.query_dict.get('hideattic', 
                                           cfg.options.hide_attic))
    options["cvs_subdirs"] = (cfg.options.show_subdir_lastmod and
                              cfg.options.show_logs)
  file_data = request.repos.listdir(request.path_parts, request.pathrev,
                                    options)

  # sort with directories first, and using the "sortby" criteria
  sortby = request.query_dict.get('sortby', cfg.options.sort_by) or 'file'
  sortdir = request.query_dict.get('sortdir', 'up')

  # when paging and sorting by filename, we can greatly improve
  # performance by "cheating" -- first, we sort (we already have the
  # names), then we just fetch dirlogs for the needed entries.
  # however, when sorting by other properties or not paging, we've no
  # choice but to fetch dirlogs for everything.
  debug.t_start("dirlogs")
  if cfg.options.dir_pagesize and sortby == 'file':
    dirlogs_first = int(request.query_dict.get('dir_pagestart', 0))
    if dirlogs_first > len(file_data):
      dirlogs_first = 0
    dirlogs_last = dirlogs_first + cfg.options.dir_pagesize
    for file in file_data:
      file.rev = None
      file.date = None
      file.log = None
      file.author = None
      file.size = None
      file.lockinfo = None
      file.dead = None
    sort_file_data(file_data, request.roottype, sortdir, sortby,
                   cfg.options.sort_group_dirs)
    # request dirlogs only for the slice of files in "this page"
    request.repos.dirlogs(request.path_parts, request.pathrev,
                          file_data[dirlogs_first:dirlogs_last], options)
  else:
    request.repos.dirlogs(request.path_parts, request.pathrev,
                          file_data, options)
    sort_file_data(file_data, request.roottype, sortdir, sortby,
                   cfg.options.sort_group_dirs)
  debug.t_end("dirlogs")

  # If a regex is specified, build a compiled form thereof for filtering
  searchstr = None
  search_re = request.query_dict.get('search', '')
  if cfg.options.use_re_search and search_re:
    searchstr = re.compile(search_re)

  # loop through entries creating rows and changing these values
  rows = [ ]
  num_displayed = 0
  num_dead = 0
  
  # set some values to be used inside loop
  where = request.where
  where_prefix = where and where + '/'

  for file in file_data:
    row = _item(author=None, log=None, short_log=None, state=None, size=None,
                log_file=None, log_rev=None, graph_href=None, mime_type=None,
                date=None, ago=None, view_href=None, log_href=None,
                revision_href=None, annotate_href=None, download_href=None,
                download_text_href=None, prefer_markup=ezt.boolean(0))
    if request.roottype == 'cvs' and file.absent:
      continue
    if cfg.options.hide_errorful_entries and file.errors:
      continue
    row.rev = file.rev
    row.author = file.author
    row.state = (request.roottype == 'cvs' and file.dead) and 'dead' or ''
    if file.date is not None:
      row.date = make_time_string(file.date, cfg)
      row.ago = html_time(request, file.date)
    if cfg.options.show_logs:
      row.log = format_log(request, file.log)
      row.short_log = format_log(request, file.log,
                                 maxlen=cfg.options.short_log_len)
    row.lockinfo = file.lockinfo
    row.anchor = request.server.escape(file.name)
    row.name = request.server.escape(file.name)
    row.pathtype = (file.kind == vclib.FILE and 'file') or \
                   (file.kind == vclib.DIR and 'dir')
    row.errors = file.errors

    if file.kind == vclib.DIR:
      if cfg.options.hide_cvsroot \
         and is_cvsroot_path(request.roottype,
                             request.path_parts + [file.name]):
        continue
    
      row.view_href = request.get_url(view_func=view_directory,
                                      where=where_prefix+file.name,
                                      pathtype=vclib.DIR,
                                      params={},
                                      escape=1)

      if request.roottype == 'svn':
        row.revision_href = request.get_url(view_func=view_revision,
                                            params={'revision': file.rev},
                                            escape=1)

      if request.roottype == 'cvs' and file.rev is not None:
        row.rev = None
        if cfg.options.show_logs:
          row.log_file = file.newest_file
          row.log_rev = file.rev

      if request.roottype == 'svn':
        row.log_href = request.get_url(view_func=view_log,
                                       where=where_prefix + file.name,
                                       pathtype=vclib.DIR,
                                       params={},
                                       escape=1)
      
    elif file.kind == vclib.FILE:
      if searchstr is not None:
        if request.roottype == 'cvs' and (file.errors or file.dead):
          continue
        if not search_file(request.repos, request.path_parts + [file.name],
                           request.pathrev, searchstr):
          continue
      if request.roottype == 'cvs' and file.dead:
        num_dead = num_dead + 1
        if hideattic:
          continue
        
      num_displayed = num_displayed + 1

      file_where = where_prefix + file.name
      if request.roottype == 'svn': 
        row.size = file.size

      row.mime_type, encoding = calculate_mime_type(request,
                                                    _path_parts(file_where),
                                                    file.rev)
      fvi = get_file_view_info(request, file_where, file.rev, row.mime_type)
      row.view_href = fvi.view_href
      row.download_href = fvi.download_href
      row.download_text_href = fvi.download_text_href
      row.annotate_href = fvi.annotate_href
      row.revision_href = fvi.revision_href
      row.prefer_markup = fvi.prefer_markup
      row.log_href = request.get_url(view_func=view_log,
                                     where=file_where,
                                     pathtype=vclib.FILE,
                                     params={},
                                     escape=1)
      if cfg.options.use_cvsgraph and request.roottype == 'cvs':
         row.graph_href = request.get_url(view_func=view_cvsgraph,
                                          where=file_where,
                                          pathtype=vclib.FILE,
                                          params={},
                                          escape=1)

    rows.append(row)

  # Prepare the data that will be passed to the template, based on the
  # common template data.
  data = common_template_data(request)
  data.merge(ezt.TemplateData({
    'entries' : rows,
    'sortby' : sortby,
    'sortdir' : sortdir,
    'search_re' : request.server.escape(search_re),
    'dir_pagestart' : None,
    'sortby_file_href' :   request.get_url(params={'sortby': 'file',
                                                   'sortdir': None},
                                           escape=1),
    'sortby_rev_href' :    request.get_url(params={'sortby': 'rev',
                                                   'sortdir': None},
                                           escape=1),
    'sortby_date_href' :   request.get_url(params={'sortby': 'date',
                                                   'sortdir': None},
                                           escape=1),
    'sortby_author_href' : request.get_url(params={'sortby': 'author',
                                                   'sortdir': None},
                                           escape=1),
    'sortby_log_href' :    request.get_url(params={'sortby': 'log',
                                                   'sortdir': None},
                                           escape=1),
    'files_shown' : num_displayed,
    'num_dead' : num_dead,
    'youngest_rev' : None,
    'youngest_rev_href' : None,
    'selection_form' : None,
    'attic_showing' : None,
    'show_attic_href' : None,
    'hide_attic_href' : None,
    'branch_tags': None,
    'plain_tags': None,
    'properties': get_itemprops(request, request.path_parts, request.pathrev),
    'tree_rev' : None,
    'tree_rev_href' : None,
    'dir_paging_action' : None,
    'dir_paging_hidden_values' : [],
    'search_re_action' : None,
    'search_re_hidden_values' : [],

    # Populated by paging()/paging_sws()
    'picklist' : [],
    'picklist_len' : 0,

    # Populated by pathrev_form()
    'pathrev_action' : None,
    'pathrev_hidden_values' : [],
    'pathrev_clear_action' : None,
    'pathrev_clear_hidden_values' : [],
    'pathrev' : None,
    'lastrev' : None,
  }))

  # clicking on sort column reverses sort order
  if sortdir == 'down':
    revsortdir = None # 'up'
  else:
    revsortdir = 'down'
  if sortby in ['file', 'rev', 'date', 'log', 'author']:
    data['sortby_%s_href' % sortby] = request.get_url(params={'sortdir':
                                                              revsortdir},
                                                      escape=1)
  # CVS doesn't support sorting by rev
  if request.roottype == "cvs":
    data['sortby_rev_href'] = None

  # set cvs-specific fields
  if request.roottype == 'cvs':
    plain_tags = options['cvs_tags']
    plain_tags.sort(icmp)
    plain_tags.reverse()
    data['plain_tags']= plain_tags

    branch_tags = options['cvs_branches']
    branch_tags.sort(icmp)
    branch_tags.reverse()
    data['branch_tags']= branch_tags
    
    data['attic_showing'] = ezt.boolean(not hideattic)
    data['show_attic_href'] = request.get_url(params={'hideattic': 0},
                                              escape=1)
    data['hide_attic_href'] = request.get_url(params={'hideattic': 1},
                                              escape=1)

  # set svn-specific fields
  elif request.roottype == 'svn':
    data['tree_rev'] = tree_rev
    data['tree_rev_href'] = request.get_url(view_func=view_revision,
                                            params={'revision': tree_rev},
                                            escape=1)
    data['youngest_rev'] = request.repos.get_youngest_revision()
    data['youngest_rev_href'] = request.get_url(view_func=view_revision,
                                                params={},
                                                escape=1)

  if cfg.options.dir_pagesize:
    data['dir_paging_action'], data['dir_paging_hidden_values'] = \
      request.get_form(params={'dir_pagestart': None})

  pathrev_form(request, data)

  if cfg.options.use_re_search:
    data['search_re_action'], data['search_re_hidden_values'] = \
      request.get_form(params={'search': None})

  if cfg.options.dir_pagesize:
    data['dir_pagestart'] = int(request.query_dict.get('dir_pagestart',0))
    data['entries'] = paging(data, 'entries', data['dir_pagestart'], 'name',
                             cfg.options.dir_pagesize)

  generate_page(request, "directory", data)

def paging(data, key, pagestart, local_name, pagesize):
  # Implement paging
  # Create the picklist
  picklist = data['picklist'] = []
  for i in range(0, len(data[key]), pagesize):
    pick = _item(start=None, end=None, count=None, more=ezt.boolean(0))
    pick.start = getattr(data[key][i], local_name)
    pick.count = i
    pick.page = (i / pagesize) + 1
    try:
      pick.end = getattr(data[key][i+pagesize-1], local_name)
    except IndexError:
      pick.end = getattr(data[key][-1], local_name)
    picklist.append(pick)
  data['picklist_len'] = len(picklist)
  # Need to fix
  # pagestart can be greater than the length of data[key] if you
  # select a tag or search while on a page other than the first.
  # Should reset to the first page, this test won't do that every
  # time that it is needed.
  # Problem might go away if we don't hide non-matching files when
  # selecting for tags or searching.
  if pagestart > len(data[key]):
    pagestart = 0
  pageend = pagestart + pagesize
  # Slice
  return data[key][pagestart:pageend]

def paging_sws(data, key, pagestart, local_name, pagesize,
               extra_pages, offset):
  """Implement sliding window-style paging."""
  # Create the picklist
  last_requested = pagestart + (extra_pages * pagesize)
  picklist = data['picklist'] = []
  has_more = ezt.boolean(0)
  for i in range(0, len(data[key]), pagesize):
    pick = _item(start=None, end=None, count=None, more=ezt.boolean(0))
    pick.start = getattr(data[key][i], local_name)
    pick.count = offset + i
    pick.page = (pick.count / pagesize) + 1
    try:
      pick.end = getattr(data[key][i+pagesize-1], local_name)
    except IndexError:
      pick.end = getattr(data[key][-1], local_name)   
    picklist.append(pick)
    if pick.count >= last_requested:
      pick.more = ezt.boolean(1)
      break
  data['picklist_len'] = len(picklist)
  first = pagestart - offset
  # FIXME: first can be greater than the length of data[key] if
  # you select a tag or search while on a page other than the first.
  # Should reset to the first page, but this test won't do that every
  # time that it is needed.  Problem might go away if we don't hide
  # non-matching files when selecting for tags or searching.
  if first > len(data[key]):
    pagestart = 0
  pageend = first + pagesize
  # Slice
  return data[key][first:pageend]

def pathrev_form(request, data):
  lastrev = None

  if request.roottype == 'svn':
    data['pathrev_action'], data['pathrev_hidden_values'] = \
      request.get_form(view_func=redirect_pathrev,
                       params={'pathrev': None,
                               'orig_path': request.where,
                               'orig_pathtype': request.pathtype,
                               'orig_pathrev': request.pathrev,
                               'orig_view': _view_codes.get(request.view_func)})

    if request.pathrev:
      youngest = request.repos.get_youngest_revision()
      lastrev = request.repos.last_rev(request.where, request.pathrev,
                                       youngest)[0]

      if lastrev == youngest:
        lastrev = None

  data['pathrev'] = request.pathrev
  data['lastrev'] = lastrev

  action, hidden_values = request.get_form(params={'pathrev': lastrev})
  if request.roottype != 'svn':
    data['pathrev_action'] = action
    data['pathrev_hidden_values'] = hidden_values
  data['pathrev_clear_action'] = action
  data['pathrev_clear_hidden_values'] = hidden_values

  return lastrev

def redirect_pathrev(request):
  assert request.roottype == 'svn'
  new_pathrev = request.query_dict.get('pathrev') or None
  path = request.query_dict.get('orig_path', '')
  pathtype = request.query_dict.get('orig_pathtype')
  pathrev = request.query_dict.get('orig_pathrev') 
  view = _views.get(request.query_dict.get('orig_view'))
  
  youngest = request.repos.get_youngest_revision()

  # go out of the way to allow revision numbers higher than youngest
  try:
    new_pathrev = int(new_pathrev)
  except ValueError:
    new_pathrev = youngest
  except TypeError:
    pass
  else:
    if new_pathrev > youngest:
      new_pathrev = youngest

  if _repos_pathtype(request.repos, _path_parts(path), new_pathrev):
    pathrev = new_pathrev
  else:
    pathrev, path = request.repos.last_rev(path, pathrev, new_pathrev)
    # allow clearing sticky revision by submitting empty string
    if new_pathrev is None and pathrev == youngest:
      pathrev = None

  request.server.redirect(request.get_url(view_func=view, 
                                          where=path,
                                          pathtype=pathtype,
                                          params={'pathrev': pathrev}))

def view_log(request):
  cfg = request.cfg
  diff_format = request.query_dict.get('diff_format', cfg.options.diff_format)
  pathtype = request.pathtype

  if pathtype is vclib.DIR:
    if request.roottype == 'cvs':
      raise debug.ViewVCException('Unsupported feature: log view on CVS '
                                  'directory', '400 Bad Request')
    mime_type = encoding = None
  else:
    mime_type, encoding = calculate_mime_type(request,
                                              request.path_parts,
                                              request.pathrev)

  options = {}
  options['svn_show_all_dir_logs'] = 1 ### someday make this optional?
  options['svn_cross_copies'] = cfg.options.cross_copies

  logsort = request.query_dict.get('logsort', cfg.options.log_sort)
  if request.roottype == "svn":
    sortby = vclib.SORTBY_DEFAULT
    logsort = None
  else:
    if logsort == 'date':
      sortby = vclib.SORTBY_DATE
    elif logsort == 'rev':
      sortby = vclib.SORTBY_REV
    else:
      sortby = vclib.SORTBY_DEFAULT

  first = last = 0
  if cfg.options.log_pagesize:
    log_pagestart = int(request.query_dict.get('log_pagestart', 0))
    total = cfg.options.log_pagesextra * cfg.options.log_pagesize
    first = log_pagestart - min(log_pagestart, total)
    last = log_pagestart + (total + cfg.options.log_pagesize) + 1
  show_revs = request.repos.itemlog(request.path_parts, request.pathrev,
                                    sortby, first, last - first, options)

  # selected revision
  selected_rev = request.query_dict.get('r1')

  entries = [ ]
  name_printed = { }
  cvs = request.roottype == 'cvs'
  for rev in show_revs:
    entry = _item()
    entry.rev = rev.string
    entry.state = (cvs and rev.dead and 'dead')
    entry.author = rev.author
    entry.changed = rev.changed
    entry.date = make_time_string(rev.date, cfg)
    entry.ago = None
    if rev.date is not None:
      entry.ago = html_time(request, rev.date, 1)
    entry.log = format_log(request, rev.log or '')
    entry.size = rev.size
    entry.lockinfo = rev.lockinfo
    entry.branch_point = None
    entry.next_main = None
    entry.orig_path = None
    entry.copy_path = None

    entry.view_href = None
    entry.download_href = None
    entry.download_text_href = None
    entry.annotate_href = None
    entry.revision_href = None
    entry.sel_for_diff_href = None
    entry.diff_to_sel_href = None
    entry.diff_to_prev_href = None
    entry.diff_to_branch_href = None
    entry.diff_to_main_href = None
        
    if request.roottype == 'cvs':
      prev = rev.prev or rev.parent
      entry.prev = prev and prev.string

      branch = rev.branch_number
      entry.vendor_branch = ezt.boolean(branch and branch[2] % 2 == 1)

      entry.branches = prep_tags(request, rev.branches)
      entry.tags = prep_tags(request, rev.tags)
      entry.branch_points = prep_tags(request, rev.branch_points)

      entry.tag_names = map(lambda x: x.name, rev.tags)
      if branch and not name_printed.has_key(branch):
        entry.branch_names = map(lambda x: x.name, rev.branches)
        name_printed[branch] = 1
      else:
        entry.branch_names = [ ]

      if rev.parent and rev.parent is not prev and not entry.vendor_branch:
        entry.branch_point = rev.parent.string

      # if it's the last revision on a branch then diff against the
      # last revision on the higher branch (e.g. change is committed and
      # brought over to -stable)
      if not rev.next and rev.parent and rev.parent.next:
        r = rev.parent.next
        while r.next:
          r = r.next
        entry.next_main = r.string

    elif request.roottype == 'svn':
      entry.prev = rev.prev and rev.prev.string
      entry.branches = entry.tags = entry.branch_points = [ ]
      entry.tag_names = entry.branch_names = [ ]
      entry.vendor_branch = None
      if rev.filename != request.where:
        entry.orig_path = rev.filename
      entry.copy_path = rev.copy_path
      entry.copy_rev = rev.copy_rev

      if entry.orig_path:
        entry.orig_href = request.get_url(view_func=view_log,
                                          where=entry.orig_path,
                                          pathtype=vclib.FILE,
                                          params={'pathrev': rev.string},
                                          escape=1)

      if rev.copy_path:
        entry.copy_href = request.get_url(view_func=view_log,
                                          where=rev.copy_path,
                                          pathtype=vclib.FILE,
                                          params={'pathrev': rev.copy_rev},
                                          escape=1)


    # view/download links
    if pathtype is vclib.FILE:
      fvi = get_file_view_info(request, request.where, rev.string, mime_type)
      entry.view_href = fvi.view_href
      entry.download_href = fvi.download_href
      entry.download_text_href = fvi.download_text_href
      entry.annotate_href = fvi.annotate_href
      entry.revision_href = fvi.revision_href
      entry.prefer_markup = fvi.prefer_markup
    else:
      entry.revision_href = request.get_url(view_func=view_revision,
                                            params={'revision': rev.string},
                                            escape=1)
      entry.view_href = request.get_url(view_func=view_directory,
                                        where=rev.filename,
                                        pathtype=vclib.DIR,
                                        params={'pathrev': rev.string},
                                        escape=1)

    # calculate diff links
    if selected_rev != entry.rev:
      entry.sel_for_diff_href = \
        request.get_url(view_func=view_log,
                        params={'r1': entry.rev},
                        escape=1)
    if entry.prev is not None:
      entry.diff_to_prev_href = \
        request.get_url(view_func=view_diff,
                        params={'r1': entry.prev,
                                'r2': entry.rev,
                                'diff_format': None},
                        escape=1)
    if selected_rev and \
           selected_rev != str(entry.rev) and \
           selected_rev != str(entry.prev) and \
           selected_rev != str(entry.branch_point) and \
           selected_rev != str(entry.next_main):
      entry.diff_to_sel_href = \
        request.get_url(view_func=view_diff,
                        params={'r1': selected_rev,
                                'r2': entry.rev,
                                'diff_format': None},
                        escape=1)

    if entry.next_main:
      entry.diff_to_main_href = \
        request.get_url(view_func=view_diff,
                        params={'r1': entry.next_main,
                                'r2': entry.rev,
                                'diff_format': None},
                        escape=1)
    if entry.branch_point:
      entry.diff_to_branch_href = \
        request.get_url(view_func=view_diff,
                        params={'r1': entry.branch_point,
                                'r2': entry.rev,
                                'diff_format': None},
                        escape=1)

    # Save our escaping until the end so stuff above works
    if entry.orig_path:
      entry.orig_path = request.server.escape(entry.orig_path)
    if entry.copy_path:
      entry.copy_path = request.server.escape(entry.copy_path)
    entries.append(entry)

  diff_select_action, diff_select_hidden_values = \
    request.get_form(view_func=view_diff,
                     params={'r1': None, 'r2': None, 'tr1': None,
                             'tr2': None, 'diff_format': None})
  logsort_action, logsort_hidden_values = \
    request.get_form(params={'logsort': None})


  data = common_template_data(request)
  data.merge(ezt.TemplateData({
    'default_branch' : None,
    'mime_type' : mime_type,
    'rev_selected' : selected_rev,
    'diff_format' : diff_format,
    'logsort' : logsort,
    'human_readable' : ezt.boolean(diff_format in ('h', 'l')),
    'log_pagestart' : None,
    'log_paging_action' : None,
    'log_paging_hidden_values' : [],
    'entries': entries,
    'head_prefer_markup' : ezt.boolean(0),
    'head_view_href' : None,
    'head_download_href': None,
    'head_download_text_href': None,
    'head_annotate_href': None,
    'tag_prefer_markup' : ezt.boolean(0),
    'tag_view_href' : None,
    'tag_download_href': None,
    'tag_download_text_href': None,
    'tag_annotate_href': None,
    'diff_select_action' : diff_select_action,
    'diff_select_hidden_values' : diff_select_hidden_values,
    'logsort_action' : logsort_action,
    'logsort_hidden_values' : logsort_hidden_values,
    'tags' : [],
    'branch_tags' : [],
    'plain_tags' : [],

    # Populated by paging()/paging_sws()
    'picklist' : [],
    'picklist_len' : 0,

    # Populated by pathrev_form()
    'pathrev_action' : None,
    'pathrev_hidden_values' : [],
    'pathrev_clear_action' : None,
    'pathrev_clear_hidden_values' : [],
    'pathrev' : None,
    'lastrev' : None,
  }))

  lastrev = pathrev_form(request, data)

  if pathtype is vclib.FILE:
    if not request.pathrev or lastrev is None:
      fvi = get_file_view_info(request, request.where, None, mime_type, None)
      data['head_view_href']= fvi.view_href
      data['head_download_href']= fvi.download_href
      data['head_download_text_href']= fvi.download_text_href
      data['head_annotate_href']= fvi.annotate_href
      data['head_prefer_markup']= fvi.prefer_markup

    if request.pathrev and request.roottype == 'cvs':
      fvi = get_file_view_info(request, request.where, None, mime_type)
      data['tag_view_href']= fvi.view_href
      data['tag_download_href']= fvi.download_href
      data['tag_download_text_href']= fvi.download_text_href
      data['tag_annotate_href']= fvi.annotate_href
      data['tag_prefer_markup']= fvi.prefer_markup
  else:
    data['head_view_href'] = request.get_url(view_func=view_directory, 
                                             params={}, escape=1)

  taginfo = options.get('cvs_tags', {})
  tagitems = taginfo.items()
  tagitems.sort()
  tagitems.reverse()

  main = taginfo.get('MAIN')
  if main:
    # Default branch may have multiple names so we list them
    branches = []
    for branch in main.aliases:
      # Don't list MAIN
      if branch is not main:
        branches.append(branch)
    data['default_branch'] = prep_tags(request, branches)

  for tag, rev in tagitems:
    if rev.co_rev:
      data['tags'].append(_item(rev=rev.co_rev.string, name=tag))
    if rev.is_branch:
      data['branch_tags'].append(tag)
    else:
      data['plain_tags'].append(tag)

  if cfg.options.log_pagesize:
    data['log_paging_action'], data['log_paging_hidden_values'] = \
      request.get_form(params={'log_pagestart': None})
    data['log_pagestart'] = int(request.query_dict.get('log_pagestart',0))
    data['entries'] = paging_sws(data, 'entries', data['log_pagestart'],
                                 'rev', cfg.options.log_pagesize,
                                 cfg.options.log_pagesextra, first)

  generate_page(request, "log", data)

def view_checkout(request):

  cfg = request.cfg
  
  if 'co' not in cfg.options.allowed_views:
    raise debug.ViewVCException('Checkout view is disabled',
                                 '403 Forbidden')
  if request.pathtype != vclib.FILE:
    raise debug.ViewVCException('Unsupported feature: checkout view on '
                                'directory', '400 Bad Request')

  path, rev = _orig_path(request)
  fp, revision = request.repos.openfile(path, rev, {})

  # The revision number acts as a strong validator.
  if not check_freshness(request, None, revision):
    mime_type, encoding = calculate_mime_type(request, path, rev)
    mime_type = request.query_dict.get('content-type') \
                or mime_type \
                or 'text/plain'
    server_fp = get_writeready_server_file(request, mime_type, encoding)
    copy_stream(fp, server_fp)
  fp.close()

def view_cvsgraph_image(request):
  "output the image rendered by cvsgraph"
  # this function is derived from cgi/cvsgraphmkimg.cgi

  cfg = request.cfg

  if not cfg.options.use_cvsgraph:
    raise debug.ViewVCException('Graph view is disabled', '403 Forbidden')

  # If cvsgraph can't find its supporting libraries, uncomment and set
  # accordingly.  Do the same in view_cvsgraph().
  #os.environ['LD_LIBRARY_PATH'] = '/usr/lib:/usr/local/lib:/path/to/cvsgraph'

  rcsfile = request.repos.rcsfile(request.path_parts)
  fp = popen.popen(cfg.utilities.cvsgraph or 'cvsgraph',
                   ("-c", cfg.path(cfg.options.cvsgraph_conf),
                    "-r", request.repos.rootpath,
                    rcsfile), 'rb', 0)
  
  copy_stream(fp, get_writeready_server_file(request, 'image/png'))
  fp.close()

def view_cvsgraph(request):
  "output a page containing an image rendered by cvsgraph"

  cfg = request.cfg

  if not cfg.options.use_cvsgraph:
    raise debug.ViewVCException('Graph view is disabled', '403 Forbidden')

  # If cvsgraph can't find its supporting libraries, uncomment and set
  # accordingly.  Do the same in view_cvsgraph_image().
  #os.environ['LD_LIBRARY_PATH'] = '/usr/lib:/usr/local/lib:/path/to/cvsgraph'

  imagesrc = request.get_url(view_func=view_cvsgraph_image, escape=1)
  mime_type = guess_mime(request.where)
  view = default_view(mime_type, cfg)
  up_where = _path_join(request.path_parts[:-1])

  # Create an image map
  rcsfile = request.repos.rcsfile(request.path_parts)
  fp = popen.popen(cfg.utilities.cvsgraph or 'cvsgraph',
                   ("-i",
                    "-c", cfg.path(cfg.options.cvsgraph_conf),
                    "-r", request.repos.rootpath,
                    "-x", "x",
                    "-3", request.get_url(view_func=view_log, params={},
                                          escape=1),
                    "-4", request.get_url(view_func=view, 
                                          params={'revision': None},
                                          escape=1, partial=1),
                    "-5", request.get_url(view_func=view_diff,
                                          params={'r1': None, 'r2': None},
                                          escape=1, partial=1),
                    "-6", request.get_url(view_func=view_directory,
                                          where=up_where,
                                          pathtype=vclib.DIR,
                                          params={'pathrev': None},
                                          escape=1, partial=1),
                    rcsfile), 'rb', 0)

  data = common_template_data(request)
  data.merge(ezt.TemplateData({
    'imagemap' : fp,
    'imagesrc' : imagesrc,
    }))
  generate_page(request, "graph", data)

def search_file(repos, path_parts, rev, search_re):
  """Return 1 iff the contents of the file at PATH_PARTS in REPOS as
  of revision REV matches regular expression SEARCH_RE."""

  # Read in each line of a checked-out file, and then use re.search to
  # search line.
  fp = repos.openfile(path_parts, rev, {})[0]
  matches = 0
  while 1:
    line = fp.readline()
    if not line:
      break
    if search_re.search(line):
      matches = 1
      fp.close()
      break
  return matches

def view_doc(request):
  """Serve ViewVC static content locally.

  Using this avoids the need for modifying the setup of the web server.
  """
  cfg = request.cfg
  document = request.where
  filename = cfg.path(os.path.join(cfg.options.template_dir,
                                   "docroot", document))

  # Stat the file to get content length and last-modified date.
  try:
    info = os.stat(filename)
  except OSError, v:
    raise debug.ViewVCException('Static file "%s" not available (%s)'
                                 % (document, str(v)), '404 Not Found')
  content_length = str(info[stat.ST_SIZE])
  last_modified = info[stat.ST_MTIME]

  # content_length + mtime makes a pretty good etag.
  if check_freshness(request, last_modified,
                     "%s-%s" % (content_length, last_modified)):
    return

  try:
    fp = open(filename, "rb")
  except IOError, v:
    raise debug.ViewVCException('Static file "%s" not available (%s)'
                                 % (document, str(v)), '404 Not Found')

  if document[-3:] == 'png':
    mime_type = 'image/png'
  elif document[-3:] == 'jpg':
    mime_type = 'image/jpeg'
  elif document[-3:] == 'gif':
    mime_type = 'image/gif'
  elif document[-3:] == 'css':
    mime_type = 'text/css'
  else: # assume HTML:
    mime_type = None
  copy_stream(fp, get_writeready_server_file(request, mime_type,
                                             content_length=content_length))
  fp.close()

def rcsdiff_date_reformat(date_str, cfg):
  if date_str is None:
    return None
  try:
    date = compat.cvs_strptime(date_str)
  except ValueError:
    return date_str
  return make_time_string(compat.timegm(date), cfg)

_re_extract_rev = re.compile(r'^[-+*]{3} [^\t]+\t([^\t]+)\t((\d+\.)*\d+)$')
_re_extract_info = re.compile(r'@@ \-([0-9]+).*\+([0-9]+).*@@(.*)')

class DiffSource:
  def __init__(self, fp, cfg):
    self.fp = fp
    self.cfg = cfg
    self.save_line = None
    self.line_number = None
    self.prev_line_number = None
    
    # keep track of where we are during an iteration
    self.idx = -1
    self.last = None

    # these will be set once we start reading
    self.state = 'no-changes'
    self.left_col = [ ]
    self.right_col = [ ]

  def __getitem__(self, idx):
    if idx == self.idx:
      return self.last
    if idx != self.idx + 1:
      raise DiffSequencingError()

    # keep calling _get_row until it gives us something. sometimes, it
    # doesn't return a row immediately because it is accumulating changes.
    # when it is out of data, _get_row will raise IndexError.
    while 1:
      item = self._get_row()
      if item:
        self.idx = idx
        self.last = item
        return item

  def _format_text(self, text):
    text = string.expandtabs(string.rstrip(text), self.cfg.options.tabsize)
    hr_breakable = self.cfg.options.hr_breakable
    
    # in the code below, "\x01" will be our stand-in for "&". We don't want
    # to insert "&" because it would get escaped by sapi.escape().  Similarly,
    # we use "\x02" as a stand-in for "<br>"
  
    if hr_breakable > 1 and len(text) > hr_breakable:
      text = re.sub('(' + ('.' * hr_breakable) + ')', '\\1\x02', text)
    if hr_breakable:
      # make every other space "breakable"
      text = string.replace(text, '  ', ' \x01nbsp;')
    else:
      text = string.replace(text, ' ', '\x01nbsp;')
    text = sapi.escape(text)
    text = string.replace(text, '\x01', '&')
    text = string.replace(text, '\x02',
                          '<span style="color:red">\</span><br />')
    return text
    
  def _get_row(self):
    if self.state[:5] == 'flush':
      item = self._flush_row()
      if item:
        return item
      self.state = 'dump'

    if self.save_line:
      line = self.save_line
      self.save_line = None
    else:
      line = self.fp.readline()

    if not line:
      if self.state == 'no-changes':
        self.state = 'done'
        return _item(type='no-changes')

      # see if there are lines to flush
      if self.left_col or self.right_col:
        # move into the flushing state
        self.state = 'flush-' + self.state
        return None

      # nothing more to return
      raise IndexError

    if line[:2] == '@@':
      self.state = 'dump'
      self.left_col = [ ]
      self.right_col = [ ]

      match = _re_extract_info.match(line)
      self.line_number = int(match.group(2)) - 1
      self.prev_line_number = int(match.group(1)) - 1
      return _item(type='header',
                   line_info_left=match.group(1),
                   line_info_right=match.group(2),
                   line_info_extra=match.group(3))
    
    if line[0] == '\\':
      # \ No newline at end of file

      # move into the flushing state. note: it doesn't matter if we really
      # have data to flush or not; that will be figured out later
      self.state = 'flush-' + self.state
      return None

    diff_code = line[0]
    output = self._format_text(line[1:])
    
    if diff_code == '+':
      if self.state == 'dump':
        self.line_number = self.line_number + 1
        return _item(type='add', right=output, line_number=self.line_number)

      self.state = 'pre-change-add'
      self.right_col.append(output)
      return None

    if diff_code == '-':
      self.state = 'pre-change-remove'
      self.left_col.append(output)
      return None  # early exit to avoid line in

    if self.left_col or self.right_col:
      # save the line for processing again later, and move into the
      # flushing state
      self.save_line = line
      self.state = 'flush-' + self.state
      return None

    self.line_number = self.line_number + 1
    self.prev_line_number = self.prev_line_number + 1
    return _item(type='context', left=output, right=output,
                 line_number=self.line_number)

  def _flush_row(self):
    if not self.left_col and not self.right_col:
      # nothing more to flush
      return None

    if self.state == 'flush-pre-change-remove':
      self.prev_line_number = self.prev_line_number + 1
      return _item(type='remove', left=self.left_col.pop(0),
                   line_number=self.prev_line_number)

    # state == flush-pre-change-add
    item = _item(type='change',
                 have_left=ezt.boolean(0),
                 have_right=ezt.boolean(0))
    if self.left_col:
      self.prev_line_number = self.prev_line_number + 1
      item.have_left = ezt.boolean(1)
      item.left = self.left_col.pop(0)
      item.line_number = self.prev_line_number
    if self.right_col:
      self.line_number = self.line_number + 1
      item.have_right = ezt.boolean(1)
      item.right = self.right_col.pop(0)
      item.line_number = self.line_number
    return item

class DiffSequencingError(Exception):
  pass

def diff_parse_headers(fp, diff_type, rev1, rev2, sym1=None, sym2=None):
  date1 = date2 = log_rev1 = log_rev2 = flag = None
  header_lines = []

  if diff_type == vclib.UNIFIED:
    f1 = '--- '
    f2 = '+++ '
  elif diff_type == vclib.CONTEXT:
    f1 = '*** '
    f2 = '--- '
  else:
    f1 = f2 = None

  # If we're parsing headers, then parse and tweak the diff headers,
  # collecting them in an array until we've read and handled them all.
  if f1 and f2:
    parsing = 1
    len_f1 = len(f1)
    len_f2 = len(f2)
    while parsing:
      line = fp.readline()
      if not line:
        break

      if line[:len(f1)] == f1:
        match = _re_extract_rev.match(line)
        if match:
          date1 = match.group(1)
          log_rev1 = match.group(2)
        if sym1:
          line = line[:-1] + ' %s\n' % sym1
      elif line[:len(f2)] == f2:
        match = _re_extract_rev.match(line)
        if match:
          date2 = match.group(1)
          log_rev2 = match.group(2)
        if sym2:
          line = line[:-1] + ' %s\n' % sym2
        parsing = 0
      elif line[:3] == 'Bin':
        flag = _RCSDIFF_IS_BINARY
        parsing = 0
      elif (string.find(line, 'not found') != -1 or 
            string.find(line, 'illegal option') != -1):
        flag = _RCSDIFF_ERROR
        parsing = 0
      header_lines.append(line)

  if (log_rev1 and log_rev1 != rev1):
    raise debug.ViewVCException('rcsdiff found revision %s, but expected '
                                 'revision %s' % (log_rev1, rev1),
                                 '500 Internal Server Error')
  if (log_rev2 and log_rev2 != rev2):
    raise debug.ViewVCException('rcsdiff found revision %s, but expected '
                                 'revision %s' % (log_rev2, rev2),
                                 '500 Internal Server Error')

  return date1, date2, flag, string.join(header_lines, '')


def _get_diff_path_parts(request, query_key, rev, base_rev):
  repos = request.repos
  if request.query_dict.has_key(query_key):
    parts = _path_parts(request.query_dict[query_key])
  elif request.roottype == 'svn':
    try:
      parts = _path_parts(repos.get_location(request.where,
                                             repos._getrev(base_rev),
                                             repos._getrev(rev)))
    except vclib.InvalidRevision:
      raise debug.ViewVCException('Invalid path(s) or revision(s) passed '
                                   'to diff', '400 Bad Request')
    except vclib.ItemNotFound:
      raise debug.ViewVCException('Invalid path(s) or revision(s) passed '
                                   'to diff', '400 Bad Request')
  else:
    parts = request.path_parts
  return parts


def setup_diff(request):
  query_dict = request.query_dict

  rev1 = r1 = query_dict['r1']
  rev2 = r2 = query_dict['r2']
  sym1 = sym2 = None

  # hack on the diff revisions
  if r1 == 'text':
    rev1 = query_dict.get('tr1', None)
    if not rev1:
      raise debug.ViewVCException('Missing revision from the diff '
                                   'form text field', '400 Bad Request')
  else:
    idx = string.find(r1, ':')
    if idx == -1:
      rev1 = r1
    else:
      rev1 = r1[:idx]
      sym1 = r1[idx+1:]
      
  if r2 == 'text':
    rev2 = query_dict.get('tr2', None)
    if not rev2:
      raise debug.ViewVCException('Missing revision from the diff '
                                   'form text field', '400 Bad Request')
    sym2 = ''
  else:
    idx = string.find(r2, ':')
    if idx == -1:
      rev2 = r2
    else:
      rev2 = r2[:idx]
      sym2 = r2[idx+1:]

  if request.roottype == 'svn':
    try:
      rev1 = str(request.repos._getrev(rev1))
      rev2 = str(request.repos._getrev(rev2))
    except vclib.InvalidRevision:
      raise debug.ViewVCException('Invalid revision(s) passed to diff',
                                  '400 Bad Request')
    
  p1 = _get_diff_path_parts(request, 'p1', rev1, request.pathrev)
  p2 = _get_diff_path_parts(request, 'p2', rev2, request.pathrev)

  try:
    if revcmp(rev1, rev2) > 0:
      rev1, rev2 = rev2, rev1
      sym1, sym2 = sym2, sym1
      p1, p2 = p2, p1
  except ValueError:
    raise debug.ViewVCException('Invalid revision(s) passed to diff',
                                 '400 Bad Request')
  return p1, p2, rev1, rev2, sym1, sym2


def view_patch(request):
  if 'diff' not in request.cfg.options.allowed_views:
    raise debug.ViewVCException('Diff generation is disabled',
                                 '403 Forbidden')

  cfg = request.cfg
  query_dict = request.query_dict
  p1, p2, rev1, rev2, sym1, sym2 = setup_diff(request)

  # In the absence of a format dictation in the CGI params, we'll let
  # use the configured diff format, allowing 'c' to mean 'c' and
  # anything else to mean 'u'.
  format = query_dict.get('diff_format',
                          cfg.options.diff_format == 'c' and 'c' or 'u')
  if format == 'c':
    diff_type = vclib.CONTEXT
  elif format == 'u':
    diff_type = vclib.UNIFIED
  else:
    raise debug.ViewVCException('Diff format %s not understood'
                                 % format, '400 Bad Request')
  
  try:
    fp = request.repos.rawdiff(p1, rev1, p2, rev2, diff_type)
  except vclib.InvalidRevision:
    raise debug.ViewVCException('Invalid path(s) or revision(s) passed '
                                 'to diff', '400 Bad Request')

  date1, date2, flag, headers = diff_parse_headers(fp, diff_type, rev1, rev2,
                                                   sym1, sym2)

  server_fp = get_writeready_server_file(request, 'text/plain')
  server_fp.write(headers)
  copy_stream(fp, server_fp)
  fp.close()


def view_diff(request):
  if 'diff' not in request.cfg.options.allowed_views:
    raise debug.ViewVCException('Diff generation is disabled',
                                 '403 Forbidden')

  cfg = request.cfg
  query_dict = request.query_dict
  p1, p2, rev1, rev2, sym1, sym2 = setup_diff(request)
  
  # since templates are in use and subversion allows changes to the dates,
  # we can't provide a strong etag
  if check_freshness(request, None, '%s-%s' % (rev1, rev2), weak=1):
    return

  # TODO: Is the slice necessary, or is limit enough?
  log_entry1 = request.repos.itemlog(p1, rev1, vclib.SORTBY_REV, 0, 1, {})[-1]
  log_entry2 = request.repos.itemlog(p2, rev2, vclib.SORTBY_REV, 0, 1, {})[-1]

  ago1 = log_entry1.date is not None \
         and html_time(request, log_entry1.date, 1) or None
  ago2 = log_entry2.date is not None \
         and html_time(request, log_entry2.date, 2) or None
  
  diff_type = None
  diff_options = {}
  human_readable = 0

  format = query_dict.get('diff_format', cfg.options.diff_format)
  if format == 'c':
    diff_type = vclib.CONTEXT
  elif format == 's':
    diff_type = vclib.SIDE_BY_SIDE
  elif format == 'l':
    diff_type = vclib.UNIFIED
    diff_options['context'] = 15
    human_readable = 1
  elif format == 'f':
    diff_type = vclib.UNIFIED
    diff_options['context'] = None
    human_readable = 1
  elif format == 'h':
    diff_type = vclib.UNIFIED
    human_readable = 1
  elif format == 'u':
    diff_type = vclib.UNIFIED
  else:
    raise debug.ViewVCException('Diff format %s not understood'
                                 % format, '400 Bad Request')

  if human_readable:
    diff_options['funout'] = cfg.options.hr_funout
    diff_options['ignore_white'] = cfg.options.hr_ignore_white
    diff_options['ignore_keyword_subst'] = cfg.options.hr_ignore_keyword_subst
  try:
    fp = sidebyside = unified = None
    if (cfg.options.hr_intraline and idiff
        and ((human_readable and idiff.sidebyside)
             or (not human_readable and diff_type == vclib.UNIFIED))):
      f1 = request.repos.openfile(p1, rev1, {})[0]
      try:
        lines_left = f1.readlines()
      finally:
        f1.close()

      f2 = request.repos.openfile(p2, rev2, {})[0]
      try:
        lines_right = f2.readlines()
      finally:
        f2.close()

      if human_readable:
        sidebyside = idiff.sidebyside(lines_left, lines_right,
                                      diff_options.get("context", 5))
      else:
        unified = idiff.unified(lines_left, lines_right,
                                diff_options.get("context", 2))
    else: 
      fp = request.repos.rawdiff(p1, rev1, p2, rev2, diff_type, diff_options)
  except vclib.InvalidRevision:
    raise debug.ViewVCException('Invalid path(s) or revision(s) passed '
                                 'to diff', '400 Bad Request')
  path_left = _path_join(p1)
  path_right = _path_join(p2)

  date1 = date2 = raw_diff_fp = None
  changes = []
  if fp:
    date1, date2, flag, headers = diff_parse_headers(fp, diff_type,
                                                     rev1, rev2, sym1, sym2)
    if human_readable:
      if flag is not None:
        changes = [ _item(type=flag) ]
      else:
        changes = DiffSource(fp, cfg)
    else:
      raw_diff_fp = MarkupPipeWrapper(fp, request.server.escape(headers), None, 1)

  no_format_params = request.query_dict.copy()
  no_format_params['diff_format'] = None
  diff_format_action, diff_format_hidden_values = \
    request.get_form(params=no_format_params)

  fvi = get_file_view_info(request, path_left, rev1)
  left = _item(date=make_time_string(log_entry1.date, cfg),
               author=log_entry1.author,
               log=format_log(request, log_entry1.log),
               size=log_entry1.size,
               ago=ago1,
               path=path_left,
               rev=rev1,
               tag=sym1,
               view_href=fvi.view_href,
               download_href=fvi.download_href,
               download_text_href=fvi.download_text_href,
               annotate_href=fvi.annotate_href,
               revision_href=fvi.revision_href,
               prefer_markup=fvi.prefer_markup)
    
  fvi = get_file_view_info(request, path_right, rev2)
  right = _item(date=make_time_string(log_entry2.date, cfg),
                author=log_entry2.author,
                log=format_log(request, log_entry2.log),
                size=log_entry2.size,
                ago=ago2,
                path=path_right,
                rev=rev2,
                tag=sym2,
                view_href=fvi.view_href,
                download_href=fvi.download_href,
                download_text_href=fvi.download_text_href,
                annotate_href=fvi.annotate_href,
                revision_href=fvi.revision_href,
                prefer_markup=fvi.prefer_markup)

  data = common_template_data(request)
  data.merge(ezt.TemplateData({
    'left' : left,
    'right' : right,
    'raw_diff' : raw_diff_fp,
    'changes' : changes,
    'sidebyside': sidebyside,
    'unified': unified,
    'diff_format' : request.query_dict.get('diff_format',
                                           cfg.options.diff_format),
    'patch_href' : request.get_url(view_func=view_patch,
                                   params=no_format_params,
                                   escape=1),
    'diff_format_action' : diff_format_action,
    'diff_format_hidden_values' : diff_format_hidden_values,
    }))
  generate_page(request, "diff", data)


def generate_tarball_header(out, name, size=0, mode=None, mtime=0,
                            uid=0, gid=0, typefrag=None, linkname='',
                            uname='viewvc', gname='viewvc',
                            devmajor=1, devminor=0, prefix=None,
                            magic='ustar', version='00', chksum=None):
  if not mode:
    if name[-1:] == '/':
      mode = 0755
    else:
      mode = 0644

  if not typefrag:
    if name[-1:] == '/':
      typefrag = '5' # directory
    else:
      typefrag = '0' # regular file

  if not prefix:
    prefix = ''

  # generate a GNU tar extension header for long names.
  if len(name) >= 100:
    generate_tarball_header(out, '././@LongLink', len(name),
                            0644, 0, 0, 0, 'L')
    out.write(name)
    out.write('\0' * (511 - ((len(name) + 511) % 512)))

  block1 = struct.pack('100s 8s 8s 8s 12s 12s',
    name,
    '%07o' % mode,
    '%07o' % uid,
    '%07o' % gid,
    '%011o' % size,
    '%011o' % mtime)

  block2 = struct.pack('c 100s 6s 2s 32s 32s 8s 8s 155s',
    typefrag,
    linkname,
    magic,
    version,
    uname,
    gname,
    '%07o' % devmajor,
    '%07o' % devminor,
    prefix)

  if not chksum:
    dummy_chksum = '        '
    block = block1 + dummy_chksum + block2
    chksum = 0
    for i in range(len(block)):
      chksum = chksum + ord(block[i])

  block = block1 + struct.pack('8s', '%07o' % chksum) + block2
  block = block + '\0' * (512 - len(block))

  out.write(block)

def generate_tarball(out, request, reldir, stack, dir_mtime=None):
  # get directory info from repository
  rep_path = request.path_parts + reldir
  entries = request.repos.listdir(rep_path, request.pathrev, {})
  request.repos.dirlogs(rep_path, request.pathrev, entries, {})
  entries.sort(lambda a, b: cmp(a.name, b.name))

  # figure out corresponding path in tar file. everything gets put underneath
  # a single top level directory named after the repository directory being
  # tarred
  if request.path_parts:
    tar_dir = request.path_parts[-1] + '/'
  else:
    tar_dir = request.rootname + '/'
  if reldir:
    tar_dir = tar_dir + _path_join(reldir) + '/'

  cvs = request.roottype == 'cvs'
  
  # If our caller doesn't dictate a datestamp to use for the current
  # directory, its datestamps will be the youngest of the datestamps
  # of versioned items in that subdirectory.  We'll be ignoring dead
  # or busted items and, in CVS, subdirs.
  if dir_mtime is None:
    dir_mtime = 0
    for file in entries:
      if cvs and (file.kind != vclib.FILE or file.rev is None or file.dead):
        continue
      if (file.date is not None) and (file.date > dir_mtime):
        dir_mtime = file.date

  # Push current directory onto the stack.
  stack.append(tar_dir)

  # If this is Subversion, we generate a header for this directory
  # regardless of its contents.  For CVS it will only get into the
  # tarball if it has files underneath it, which we determine later.
  if not cvs:
    generate_tarball_header(out, tar_dir, mtime=dir_mtime)

  # Run through the files in this directory, skipping busted and
  # unauthorized ones.
  for file in entries:
    if file.kind != vclib.FILE:
      continue
    if cvs and (file.rev is None or file.dead):
      continue

    # If we get here, we've seen at least one valid file in the
    # current directory.  For CVS, we need to make sure there are
    # directory parents to contain it, so we flush the stack.
    if cvs:
      for dir in stack:
        generate_tarball_header(out, dir, mtime=dir_mtime)
      del stack[:]

    # Calculate the mode for the file.  Sure, we could look directly
    # at the ,v file in CVS, but that's a layering violation we'd like
    # to avoid as much as possible.
    if request.repos.isexecutable(rep_path + [file.name], request.pathrev):
      mode = 0755
    else:
      mode = 0644

    ### FIXME: Read the whole file into memory?  Bad... better to do
    ### 2 passes.
    fp = request.repos.openfile(rep_path + [file.name], request.pathrev, {})[0]
    contents = fp.read()
    fp.close()

    generate_tarball_header(out, tar_dir + file.name,
                            len(contents), mode,
                            file.date is not None and file.date or 0)
    out.write(contents)
    out.write('\0' * (511 - ((len(contents) + 511) % 512)))

  # Recurse into subdirectories, skipping busted and unauthorized (or
  # configured-to-be-hidden) ones.
  for file in entries:
    if file.errors or file.kind != vclib.DIR:
      continue
    if request.cfg.options.hide_cvsroot \
       and is_cvsroot_path(request.roottype, rep_path + [file.name]):
      continue

    mtime = request.roottype == 'svn' and file.date or None
    generate_tarball(out, request, reldir + [file.name], stack, mtime)

  # Pop the current directory from the stack.
  del stack[-1:]

def download_tarball(request):
  cfg = request.cfg
  
  if 'tar' not in request.cfg.options.allowed_views:
    raise debug.ViewVCException('Tarball generation is disabled',
                                 '403 Forbidden')

  if debug.TARFILE_PATH:
    fp = open(debug.TARFILE_PATH, 'w')
  else:    
    tarfile = request.rootname
    if request.path_parts:
      tarfile = "%s-%s" % (tarfile, request.path_parts[-1])
    request.server.addheader('Content-Disposition',
                             'attachment; filename="%s.tar.gz"' % (tarfile))
    server_fp = get_writeready_server_file(request, 'application/x-gzip')
    request.server.flush()
    
    # Try to use the Python gzip module, if available; otherwise,
    # we'll use the configured 'gzip' binary.
    fp = gzip.GzipFile('', 'wb', 9, server_fp)

  ### FIXME: For Subversion repositories, we can get the real mtime of the
  ### top-level directory here.
  generate_tarball(fp, request, [], [])

  fp.write('\0' * 1024)
  fp.close()

  if debug.TARFILE_PATH:
    request.server.header('')
    print """
<html>
<body>
<p>Tarball '%s' successfully generated!</p>
</body>
</html>""" % (debug.TARFILE_PATH)


def view_revision(request):
  if request.roottype != "svn":
    raise debug.ViewVCException("Revision view not supported for CVS "
                                "repositories at this time.",
                                "400 Bad Request")

  cfg = request.cfg
  query_dict = request.query_dict
  try:
    rev = request.repos._getrev(query_dict.get('revision'))
  except vclib.InvalidRevision:
    raise debug.ViewVCException('Invalid revision', '404 Not Found')
  youngest_rev = request.repos.get_youngest_revision()
  
  # The revision number acts as a weak validator (but we tell browsers
  # not to cache the youngest revision).
  if rev != youngest_rev and check_freshness(request, None, str(rev), weak=1):
    return

  # Fetch the revision information.
  date, author, msg, revprops, changes = request.repos.revinfo(rev)
  date_str = make_time_string(date, cfg)

  # Fix up the revprops list (rather like get_itemprops()).
  propnames = revprops.keys()
  propnames.sort()
  props = []
  for name in propnames:
    value = format_log(request, revprops[name])
    undisplayable = ezt.boolean(0)
    # skip non-utf8 property names
    try:
      unicode(name, 'utf8')
    except:
      continue
    # note non-utf8 property values
    try:
      unicode(value, 'utf8')
    except:
      value = None
      undisplayable = ezt.boolean(1)
    props.append(_item(name=name, value=value, undisplayable=undisplayable))
  
  # Sort the changes list by path.
  def changes_sort_by_path(a, b):
    return cmp(a.path_parts, b.path_parts)
  changes.sort(changes_sort_by_path)

  # Handle limit_changes parameter
  cfg_limit_changes = cfg.options.limit_changes
  limit_changes = int(query_dict.get('limit_changes', cfg_limit_changes))
  more_changes = None
  more_changes_href = None
  first_changes = None
  first_changes_href = None
  num_changes = len(changes)
  if limit_changes and len(changes) > limit_changes:
    more_changes = len(changes) - limit_changes
    params = query_dict.copy()
    params['limit_changes'] = 0
    more_changes_href = request.get_url(params=params, escape=1)
    changes = changes[:limit_changes]
  elif cfg_limit_changes and len(changes) > cfg_limit_changes:
    first_changes = cfg_limit_changes
    params = query_dict.copy()
    params['limit_changes'] = None
    first_changes_href = request.get_url(params=params, escape=1)

  # Add the hrefs, types, and prev info
  for change in changes:
    change.view_href = change.diff_href = change.type = change.log_href = None

    # If the path is newly added, don't claim text or property
    # modifications.
    if (change.action == vclib.ADDED or change.action == vclib.REPLACED) \
       and not change.copied:
      change.text_changed = 0
      change.props_changed = 0

    # Calculate the view link URLs (for which we must have a pathtype).
    if change.pathtype:
      view_func = None
      if change.pathtype is vclib.FILE \
         and 'markup' in cfg.options.allowed_views:
        view_func = view_markup
      elif change.pathtype is vclib.DIR:
        view_func = view_directory

      path = _path_join(change.path_parts)
      base_path = _path_join(change.base_path_parts)
      if change.action == vclib.DELETED:
        link_rev = str(change.base_rev)
        link_where = base_path
      else:
        link_rev = str(rev)
        link_where = path

      change.view_href = request.get_url(view_func=view_func,
                                         where=link_where,
                                         pathtype=change.pathtype,
                                         params={'pathrev' : link_rev},
                                         escape=1)
      change.log_href = request.get_url(view_func=view_log,
                                        where=link_where,
                                        pathtype=change.pathtype,
                                        params={'pathrev' : link_rev},
                                        escape=1)

      if change.pathtype is vclib.FILE and change.text_changed:
        change.diff_href = request.get_url(view_func=view_diff,
                                           where=path, 
                                           pathtype=change.pathtype,
                                           params={'pathrev' : str(rev),
                                                   'r1' : str(rev),
                                                   'r2' : str(change.base_rev),
                                                   },
                                           escape=1)
    

    # use same variable names as the log template
    change.path = _path_join(change.path_parts)
    change.copy_path = _path_join(change.base_path_parts)
    change.copy_rev = change.base_rev
    change.text_mods = ezt.boolean(change.text_changed)
    change.prop_mods = ezt.boolean(change.props_changed)
    change.is_copy = ezt.boolean(change.copied)
    change.pathtype = (change.pathtype == vclib.FILE and 'file') \
                      or (change.pathtype == vclib.DIR and 'dir') \
                      or None
    del change.path_parts
    del change.base_path_parts
    del change.base_rev
    del change.text_changed
    del change.props_changed
    del change.copied

  prev_rev_href = next_rev_href = None
  if rev > 0:
    prev_rev_href = request.get_url(view_func=view_revision,
                                    where=None,
                                    pathtype=None,
                                    params={'revision': str(rev - 1)},
                                    escape=1)
  if rev < request.repos.get_youngest_revision():
    next_rev_href = request.get_url(view_func=view_revision,
                                    where=None,
                                    pathtype=None,
                                    params={'revision': str(rev + 1)},
                                    escape=1)
  jump_rev_action, jump_rev_hidden_values = \
    request.get_form(params={'revision': None})
    
  data = common_template_data(request)
  data.merge(ezt.TemplateData({
    'rev' : str(rev),
    'author' : author,
    'date' : date_str,
    'log' : format_log(request, msg),
    'properties' : props,
    'ago' : date is not None and html_time(request, date, 1) or None,
    'changes' : changes,
    'prev_href' : prev_rev_href,
    'next_href' : next_rev_href,
    'num_changes' : num_changes,
    'limit_changes': limit_changes,
    'more_changes': more_changes,
    'more_changes_href': more_changes_href,
    'first_changes': first_changes,
    'first_changes_href': first_changes_href,
    'jump_rev_action' : jump_rev_action,
    'jump_rev_hidden_values' : jump_rev_hidden_values,
    'revision_href' : request.get_url(view_func=view_revision,
                                      where=None,
                                      pathtype=None,
                                      params={'revision': str(rev)},
                                      escape=1),
  }))
  if rev == youngest_rev:
    request.server.addheader("Cache-control", "no-store")
  generate_page(request, "revision", data)

def is_query_supported(request):
  """Returns true if querying is supported for the given path."""
  return request.cfg.cvsdb.enabled \
         and request.pathtype == vclib.DIR \
         and request.roottype in ['cvs', 'svn']

def is_querydb_nonempty_for_root(request):
  """Return 1 iff commits database integration is supported *and* the
  current root is found in that database.  Only does this check if
  check_database is set to 1."""
  if request.cfg.cvsdb.enabled and request.roottype in ['cvs', 'svn']:
    if request.cfg.cvsdb.check_database_for_root:
      global cvsdb
      import cvsdb
      db = cvsdb.ConnectDatabaseReadOnly(request.cfg)
      repos_root, repos_dir = cvsdb.FindRepository(db, request.rootpath)
      if repos_root:
        return 1
    else:
      return 1
  return 0

def validate_query_args(request):
  # Do some additional input validation of query form arguments beyond
  # what is offered by the CGI param validation loop in Request.run_viewvc().
  
  for arg_base in ['branch', 'file', 'comment', 'who']:
    # First, make sure the the XXX_match args have valid values:
    arg_match = arg_base + '_match'
    arg_match_value = request.query_dict.get(arg_match, 'exact')
    if not arg_match_value in ('exact', 'like', 'glob', 'regex', 'notregex'):
      raise debug.ViewVCException(
        'An illegal value was provided for the "%s" parameter.'
        % (arg_match),
        '400 Bad Request')

    # Now, for those args which are supposed to be regular expressions (per
    # their corresponding XXX_match values), make sure they are.
    if arg_match_value == 'regex' or arg_match_value == 'notregex':
      arg_base_value = request.query_dict.get(arg_base)
      if arg_base_value:
        try:
          re.compile(arg_base_value)
        except:
          raise debug.ViewVCException(
            'An illegal value was provided for the "%s" parameter.'
            % (arg_base),
            '400 Bad Request')
  
def view_queryform(request):
  if not is_query_supported(request):
    raise debug.ViewVCException('Can not query project root "%s" at "%s".'
                                 % (request.rootname, request.where),
                                 '403 Forbidden')

  # Do some more precise input validation.
  validate_query_args(request)
  
  query_action, query_hidden_values = \
    request.get_form(view_func=view_query, params={'limit_changes': None})
  limit_changes = \
    int(request.query_dict.get('limit_changes',
                               request.cfg.options.limit_changes))

  def escaped_query_dict_get(itemname, itemdefault=''):
    return request.server.escape(request.query_dict.get(itemname, itemdefault))
    
  data = common_template_data(request)
  data.merge(ezt.TemplateData({
    'branch' : escaped_query_dict_get('branch', ''),
    'branch_match' : escaped_query_dict_get('branch_match', 'exact'),
    'dir' : escaped_query_dict_get('dir', ''),
    'file' : escaped_query_dict_get('file', ''),
    'file_match' : escaped_query_dict_get('file_match', 'exact'),
    'who' : escaped_query_dict_get('who', ''),
    'who_match' : escaped_query_dict_get('who_match', 'exact'),
    'comment' : escaped_query_dict_get('comment', ''),
    'comment_match' : escaped_query_dict_get('comment_match', 'exact'),
    'querysort' : escaped_query_dict_get('querysort', 'date'),
    'date' : escaped_query_dict_get('date', 'hours'),
    'hours' : escaped_query_dict_get('hours', '2'),
    'mindate' : escaped_query_dict_get('mindate', ''),
    'maxdate' : escaped_query_dict_get('maxdate', ''),
    'query_action' : query_action,
    'query_hidden_values' : query_hidden_values,
    'limit_changes' : limit_changes,
    'dir_href' : request.get_url(view_func=view_directory, params={},
                                 escape=1),
    }))
  generate_page(request, "query_form", data)

def parse_date(datestr):
  """Parse a date string from the query form."""
  
  match = re.match(r'^(\d\d\d\d)-(\d\d)-(\d\d)(?:\ +'
                   '(\d\d):(\d\d)(?::(\d\d))?)?$', datestr)
  if match:
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    hour = match.group(4)
    if hour is not None:
      hour = int(hour)
    else:
      hour = 0
    minute = match.group(5)
    if minute is not None:
      minute = int(minute)
    else:
      minute = 0
    second = match.group(6)
    if second is not None:
      second = int(second)
    else:
      second = 0
    # return a "seconds since epoch" value assuming date given in UTC
    tm = (year, month, day, hour, minute, second, 0, 0, 0)
    return compat.timegm(tm)
  else:
    return None

def english_query(request):
  """Generate a sentance describing the query."""
  cfg = request.cfg
  ret = [ 'Checkins ' ]
  dir = request.query_dict.get('dir', '')
  if dir:
    ret.append('to ')
    if ',' in dir:
      ret.append('subdirectories')
    else:
      ret.append('subdirectory')
    ret.append(' <em>%s</em> ' % request.server.escape(dir))
  file = request.query_dict.get('file', '')
  if file:
    if len(ret) != 1:
      ret.append('and ')
    ret.append('to file <em>%s</em> ' % request.server.escape(file))
  who = request.query_dict.get('who', '')
  branch = request.query_dict.get('branch', '')
  if branch:
    ret.append('on branch <em>%s</em> ' % request.server.escape(branch))
  else:
    ret.append('on all branches ')
  comment = request.query_dict.get('comment', '')
  if comment:
    ret.append('with comment <i>%s</i> ' % request.server.escape(comment))
  if who:
    ret.append('by <em>%s</em> ' % request.server.escape(who))
  date = request.query_dict.get('date', 'hours')
  if date == 'hours':
    ret.append('in the last %s hours' \
               % request.server.escape(request.query_dict.get('hours', '2')))
  elif date == 'day':
    ret.append('in the last day')
  elif date == 'week':
    ret.append('in the last week')
  elif date == 'month':
    ret.append('in the last month')
  elif date == 'all':
    ret.append('since the beginning of time')
  elif date == 'explicit':
    mindate = request.query_dict.get('mindate', '')
    maxdate = request.query_dict.get('maxdate', '')
    if mindate and maxdate:
      w1, w2 = 'between', 'and'
    else:
      w1, w2 = 'since', 'before'
    if mindate:
      mindate = make_time_string(parse_date(mindate), cfg)
      ret.append('%s <em>%s</em> ' % (w1, mindate))
    if maxdate:
      maxdate = make_time_string(parse_date(maxdate), cfg)
      ret.append('%s <em>%s</em> ' % (w2, maxdate))
  return string.join(ret, '')

def prev_rev(rev):
  """Returns a string representing the previous revision of the argument."""
  r = string.split(rev, '.')
  # decrement final revision component
  r[-1] = str(int(r[-1]) - 1)
  # prune if we pass the beginning of the branch
  if len(r) > 2 and r[-1] == '0':
    r = r[:-2]
  return string.join(r, '.')

def build_commit(request, files, max_files, dir_strip, format):
  """Return a commit object build from the information in FILES, or
  None if no allowed files are present in the set.  DIR_STRIP is the
  path prefix to remove from the commit object's set of files.  If
  MAX_FILES is non-zero, it is used to limit the number of files
  returned in the commit object.  FORMAT is the requested output
  format of the query request."""

  cfg = request.cfg
  author = files[0].GetAuthor()
  date = files[0].GetTime()
  desc = files[0].GetDescription()
  commit_rev = files[0].GetRevision()
  len_strip = len(dir_strip)
  commit_files = []
  num_allowed = 0
  plus_count = 0
  minus_count = 0
  found_unreadable = 0
  
  for f in files:
    dirname = f.GetDirectory()
    filename = f.GetFile()
    if dir_strip:
      assert dirname[:len_strip] == dir_strip
      assert len(dirname) == len_strip or dirname[len(dir_strip)] == '/'
      dirname = dirname[len_strip+1:]
    where = dirname and ("%s/%s" % (dirname, filename)) or filename
    rev = f.GetRevision()
    rev_prev = prev_rev(rev)
    commit_time = f.GetTime()
    if commit_time:
      commit_time = make_time_string(commit_time, cfg)
    change_type = f.GetTypeString()

    # In CVS, we can actually look at deleted revisions; in Subversion
    # we can't -- we'll look at the previous revision instead.
    exam_rev = rev
    if request.roottype == 'svn' and change_type == 'Remove':
      exam_rev = rev_prev

    # Check path access (since the commits database logic bypasses the
    # vclib layer and, thus, the vcauth stuff that layer uses).
    path_parts = _path_parts(where)
    if path_parts:
      # Skip files in CVSROOT if asked to hide such.
      if cfg.options.hide_cvsroot \
         and is_cvsroot_path(request.roottype, path_parts):
        found_unreadable = 1
        continue
      
      # We have to do a rare authz check here because this data comes
      # from the CVSdb, not from the vclib providers.
      #
      # WARNING: The Subversion CVSdb integration logic is weak, weak,
      # weak.  It has no ability to track copies, so complex
      # situations like a copied directory with a deleted subfile (all
      # in the same revision) are very ... difficult.  We've no choice
      # but to omit as unauthorized paths the authorization logic
      # can't find.
      try:
        readable = vclib.check_path_access(request.repos, path_parts,
                                           None, exam_rev)
      except vclib.ItemNotFound:
        readable = 0
      if not readable:
        found_unreadable = 1
        continue
         
    if request.roottype == 'svn':
      params = { 'pathrev': exam_rev }
    else:
      params = { 'revision': exam_rev, 'pathrev': f.GetBranch() or None }  
    
    dir_href = request.get_url(view_func=view_directory,
                               where=dirname, pathtype=vclib.DIR,
                               params=params, escape=1)
    log_href = request.get_url(view_func=view_log,
                               where=where, pathtype=vclib.FILE,
                               params=params, escape=1)
    diff_href = view_href = download_href = None
    if 'markup' in cfg.options.allowed_views:
      view_href = request.get_url(view_func=view_markup,
                                  where=where, pathtype=vclib.FILE,
                                  params=params, escape=1)
    if 'co' in cfg.options.allowed_views:
      download_href = request.get_url(view_func=view_checkout,
                                      where=where, pathtype=vclib.FILE,
                                      params=params, escape=1)
    if change_type == 'Change':
      diff_href_params = params.copy()
      diff_href_params.update({
        'r1': rev_prev,
        'r2': rev,
        'diff_format': None
        })
      diff_href = request.get_url(view_func=view_diff,
                                  where=where, pathtype=vclib.FILE,
                                  params=diff_href_params, escape=1)
    mime_type, encoding = calculate_mime_type(request, path_parts, exam_rev)
    prefer_markup = ezt.boolean(default_view(mime_type, cfg) == view_markup)

    # Update plus/minus line change count.
    plus = int(f.GetPlusCount())
    minus = int(f.GetMinusCount())
    plus_count = plus_count + plus
    minus_count = minus_count + minus
    
    num_allowed = num_allowed + 1
    if max_files and num_allowed > max_files:
      continue

    commit_files.append(_item(date=commit_time,
                              dir=request.server.escape(dirname),
                              file=request.server.escape(filename),
                              author=request.server.escape(f.GetAuthor()),
                              rev=rev,
                              branch=f.GetBranch(),
                              plus=plus,
                              minus=minus,
                              type=change_type,
                              dir_href=dir_href,
                              log_href=log_href,
                              view_href=view_href,
                              download_href=download_href,
                              prefer_markup=prefer_markup,
                              diff_href=diff_href))

  # No files survived authz checks?  Let's just pretend this
  # little commit didn't happen, shall we?
  if not len(commit_files):
    return None

  commit = _item(num_files=len(commit_files), files=commit_files,
                 plus=plus_count, minus=minus_count)
  commit.limited_files = ezt.boolean(num_allowed > len(commit_files))

  # We'll mask log messages in commits which contain unreadable paths,
  # but even that is kinda iffy.  If a person searches for
  # '/some/hidden/path' across log messages, then gets a response set
  # that shows commits lacking log message, said person can reasonably
  # assume that the log messages contained the hidden path, and that
  # this is likely because they are referencing a real path in the
  # repository -- a path the user isn't supposed to even know about.
  if found_unreadable:
    commit.log = None
    commit.short_log = None
  else:
    commit.log = format_log(request, desc, 0, format != 'rss')
    commit.short_log = format_log(request, desc, cfg.options.short_log_len,
                                  format != 'rss')
  commit.author = request.server.escape(author)
  commit.rss_date = make_rss_time_string(date, request.cfg)
  if request.roottype == 'svn':
    commit.rev = commit_rev
    commit.rss_url = '%s://%s%s' % \
      (request.server.getenv("HTTPS") == "on" and "https" or "http",
       request.server.getenv("HTTP_HOST"),
       request.get_url(view_func=view_revision,
                       params={'revision': commit.rev},
                       escape=1))
  else:
    commit.rev = None
    commit.rss_url = None
  return commit

def query_backout(request, commits):
  server_fp = get_writeready_server_file(request, 'text/plain')
  if not commits:
    server_fp.write("""\
# No changes were selected by the query.
# There is nothing to back out.
""")
    return
  server_fp.write("""\
# This page can be saved as a shell script and executed.
# It should be run at the top of your work area.  It will update
# your working copy to back out the changes selected by the
# query.
""")
  for commit in commits:
    for fileinfo in commit.files:
      if request.roottype == 'cvs':
        server_fp.write('cvs update -j %s -j %s %s/%s\n'
                        % (fileinfo.rev, prev_rev(fileinfo.rev),
                           fileinfo.dir, fileinfo.file))
      elif request.roottype == 'svn':
        server_fp.write('svn merge -r %s:%s %s/%s\n'
                        % (fileinfo.rev, prev_rev(fileinfo.rev),
                           fileinfo.dir, fileinfo.file))

def view_query(request):
  if not is_query_supported(request):
    raise debug.ViewVCException('Can not query project root "%s" at "%s".'
                                 % (request.rootname, request.where),
                                 '403 Forbidden')

  cfg = request.cfg

  # Do some more precise input validation.
  validate_query_args(request)

  # get form data
  branch = request.query_dict.get('branch', '')
  branch_match = request.query_dict.get('branch_match', 'exact')
  dir = request.query_dict.get('dir', '')
  file = request.query_dict.get('file', '')
  file_match = request.query_dict.get('file_match', 'exact')
  who = request.query_dict.get('who', '')
  who_match = request.query_dict.get('who_match', 'exact')
  comment = request.query_dict.get('comment', '')
  comment_match = request.query_dict.get('comment_match', 'exact')
  querysort = request.query_dict.get('querysort', 'date')
  date = request.query_dict.get('date', 'hours')
  hours = request.query_dict.get('hours', '2')
  mindate = request.query_dict.get('mindate', '')
  maxdate = request.query_dict.get('maxdate', '')
  format = request.query_dict.get('format')
  limit_changes = int(request.query_dict.get('limit_changes',
                                             cfg.options.limit_changes))

  match_types = { 'exact':1, 'like':1, 'glob':1, 'regex':1, 'notregex':1 }
  sort_types = { 'date':1, 'author':1, 'file':1 }
  date_types = { 'hours':1, 'day':1, 'week':1, 'month':1,
                 'all':1, 'explicit':1 }

  # parse various fields, validating or converting them
  if not match_types.has_key(branch_match): branch_match = 'exact'
  if not match_types.has_key(file_match): file_match = 'exact'
  if not match_types.has_key(who_match): who_match = 'exact'
  if not match_types.has_key(comment_match): comment_match = 'exact'
  if not sort_types.has_key(querysort): querysort = 'date'
  if not date_types.has_key(date): date = 'hours'
  mindate = parse_date(mindate)
  maxdate = parse_date(maxdate)

  global cvsdb
  import cvsdb

  db = cvsdb.ConnectDatabaseReadOnly(cfg)
  repos_root, repos_dir = cvsdb.FindRepository(db, request.rootpath)
  if not repos_root:
    raise debug.ViewVCException(
      "The root '%s' was not found in the commit database "
      % request.rootname)

  # create the database query from the form data
  query = cvsdb.CreateCheckinQuery()
  query.SetRepository(repos_root)
  # treat "HEAD" specially ...
  if branch_match == 'exact' and branch == 'HEAD':
    query.SetBranch('')
  elif branch:
    query.SetBranch(branch, branch_match)
  if dir:
    for subdir in string.split(dir, ','):
      path = (_path_join(repos_dir + request.path_parts
                         + _path_parts(string.strip(subdir))))
      query.SetDirectory(path, 'exact')
      query.SetDirectory('%s/%%' % cvsdb.EscapeLike(path), 'like')
  else:
    where = _path_join(repos_dir + request.path_parts)
    if where: # if we are in a subdirectory ...
      query.SetDirectory(where, 'exact')
      query.SetDirectory('%s/%%' % cvsdb.EscapeLike(where), 'like')
  if file:
    query.SetFile(file, file_match)
  if who:
    query.SetAuthor(who, who_match)
  if comment:
    query.SetComment(comment, comment_match)
  query.SetSortMethod(querysort)
  if date == 'hours':
    query.SetFromDateHoursAgo(int(hours))
  elif date == 'day':
    query.SetFromDateDaysAgo(1)
  elif date == 'week':
    query.SetFromDateDaysAgo(7)
  elif date == 'month':
    query.SetFromDateDaysAgo(31)
  elif date == 'all':
    pass
  elif date == 'explicit':
    if mindate is not None:
      query.SetFromDateObject(mindate)
    if maxdate is not None:
      query.SetToDateObject(maxdate)

  # Set the admin-defined (via configuration) row limits.  This is to avoid
  # slamming the database server with a monster query.
  if format == 'rss':
    query.SetLimit(cfg.cvsdb.rss_row_limit)
  else:
    query.SetLimit(cfg.cvsdb.row_limit)

  # run the query
  db.RunQuery(query)
  commit_list = query.GetCommitList()
  row_limit_reached = query.GetLimitReached()
  
  # gather commits
  commits = []
  plus_count = 0
  minus_count = 0
  mod_time = -1
  if commit_list:
    files = []
    limited_files = 0
    current_desc = commit_list[0].GetDescriptionID()
    current_rev = commit_list[0].GetRevision()
    dir_strip = _path_join(repos_dir)

    for commit in commit_list:
      commit_desc = commit.GetDescriptionID()
      commit_rev = commit.GetRevision()

      # base modification time on the newest commit
      if commit.GetTime() > mod_time:
        mod_time = commit.GetTime()
        
      # For CVS, group commits with the same commit message.
      # For Subversion, group them only if they have the same revision number
      if request.roottype == 'cvs':
        if current_desc == commit_desc:
          files.append(commit)
          continue
      else:
        if current_rev == commit_rev:
          files.append(commit)
          continue

      # append this grouping
      commit_item = build_commit(request, files, limit_changes,
                                 dir_strip, format)
      if commit_item:
        # update running plus/minus totals
        plus_count = plus_count + commit_item.plus
        minus_count = minus_count + commit_item.minus
        commits.append(commit_item)

      files = [ commit ]
      limited_files = 0
      current_desc = commit_desc
      current_rev = commit_rev
      
    # we need to tack on our last commit grouping, if any
    commit_item = build_commit(request, files, limit_changes,
                               dir_strip, format)
    if commit_item:
      # update running plus/minus totals
      plus_count = plus_count + commit_item.plus
      minus_count = minus_count + commit_item.minus
      commits.append(commit_item)
  
  # only show the branch column if we are querying all branches
  # or doing a non-exact branch match on a CVS repository.
  show_branch = ezt.boolean(request.roottype == 'cvs' and
                            (branch == '' or branch_match != 'exact'))

  # backout link
  params = request.query_dict.copy()
  params['format'] = 'backout'
  backout_href = request.get_url(params=params,
                                 escape=1)

  # link to zero limit_changes value
  params = request.query_dict.copy()
  params['limit_changes'] = 0
  limit_changes_href = request.get_url(params=params, escape=1)

  # if we got any results, use the newest commit as the modification time
  if mod_time >= 0:
    if check_freshness(request, mod_time):
      return

  if format == 'backout':
    query_backout(request, commits)
    return

  data = common_template_data(request)
  data.merge(ezt.TemplateData({
    'sql': request.server.escape(db.CreateSQLQueryString(query)),
    'english_query': english_query(request),
    'queryform_href': request.get_url(view_func=view_queryform, escape=1),
    'backout_href': backout_href,
    'plus_count': plus_count,
    'minus_count': minus_count,
    'show_branch': show_branch,
    'querysort': querysort,
    'commits': commits,
    'row_limit_reached' : ezt.boolean(row_limit_reached),
    'limit_changes': limit_changes,
    'limit_changes_href': limit_changes_href,
    'rss_link_href': request.get_url(view_func=view_query,
                                     params={'date': 'month'},
                                     escape=1,
                                     prefix=1),
    }))
  if format == 'rss':
    generate_page(request, "rss", data, "application/rss+xml")
  else:
    generate_page(request, "query_results", data)

_views = {
  'annotate':  view_annotate,
  'co':        view_checkout,
  'diff':      view_diff,
  'dir':       view_directory,
  'graph':     view_cvsgraph,
  'graphimg':  view_cvsgraph_image,
  'log':       view_log,
  'markup':    view_markup,
  'patch':     view_patch,
  'query':     view_query,
  'queryform': view_queryform,
  'revision':  view_revision,
  'roots':     view_roots,
  'tar':       download_tarball,
  'redirect_pathrev': redirect_pathrev,
}

_view_codes = {}
for code, view in _views.items():
  _view_codes[view] = code

def list_roots(request):
  cfg = request.cfg
  allroots = { }
  
  # Add the viewable Subversion roots
  for root in cfg.general.svn_roots.keys():
    auth = setup_authorizer(cfg, request.username, root)
    try:
      repos = vclib.svn.SubversionRepository(root, cfg.general.svn_roots[root],
                                             auth, cfg.utilities,
                                             cfg.options.svn_config_dir)
      lastmod = None
      if cfg.options.show_roots_lastmod:
        try:
          repos.open()
          youngest_rev = repos.youngest
          date, author, msg, revprops, changes = repos.revinfo(youngest_rev)
          date_str = make_time_string(date, cfg)
          ago = html_time(request, date)
          log = format_log(request, msg)
          short_log = format_log(request, msg, maxlen=cfg.options.short_log_len)
          lastmod = _item(ago=ago, author=author, date=date_str, log=log,
                          short_log=short_log, rev=str(youngest_rev))
        except:
          lastmod = None
    except vclib.ReposNotFound:
      continue
    allroots[root] = [cfg.general.svn_roots[root], 'svn', lastmod]

  # Add the viewable CVS roots
  for root in cfg.general.cvs_roots.keys():
    auth = setup_authorizer(cfg, request.username, root)
    try:
      vclib.ccvs.CVSRepository(root, cfg.general.cvs_roots[root], auth,
                               cfg.utilities, cfg.options.use_rcsparse)
    except vclib.ReposNotFound:
      continue
    allroots[root] = [cfg.general.cvs_roots[root], 'cvs', None]
    
  return allroots

def expand_root_parents(cfg):
  """Expand the configured root parents into individual roots."""
  
  # Each item in root_parents is a "directory : repo_type" string.
  for pp in cfg.general.root_parents:
    pos = string.rfind(pp, ':')
    if pos < 0:
      raise debug.ViewVCException(
        'The path "%s" in "root_parents" does not include a '
        'repository type.  Expected "cvs" or "svn".' % (pp))

    repo_type = string.strip(pp[pos+1:])
    pp = os.path.normpath(string.strip(pp[:pos]))

    if repo_type == 'cvs':
      roots = vclib.ccvs.expand_root_parent(pp)
      if cfg.options.hide_cvsroot and roots.has_key('CVSROOT'):
        del roots['CVSROOT']
      cfg.general.cvs_roots.update(roots)
    elif repo_type == 'svn':
      roots = vclib.svn.expand_root_parent(pp)
      cfg.general.svn_roots.update(roots)
    else:
      raise debug.ViewVCException(
        'The path "%s" in "root_parents" has an unrecognized '
        'repository type ("%s").  Expected "cvs" or "svn".'
        % (pp, repo_type))

def find_root_in_parents(cfg, rootname, roottype):
  """Return the rootpath for configured ROOTNAME of ROOTTYPE."""

  # Easy out:  caller wants rootname "CVSROOT", and we're hiding those.
  if rootname == 'CVSROOT' and cfg.options.hide_cvsroot:
    return None
  
  for pp in cfg.general.root_parents:
    pos = string.rfind(pp, ':')
    if pos < 0:
      continue
    repo_type = string.strip(pp[pos+1:])
    if repo_type != roottype:
      continue
    pp = os.path.normpath(string.strip(pp[:pos]))
    
    if roottype == 'cvs':
      roots = vclib.ccvs.expand_root_parent(pp)
    elif roottype == 'svn':
      roots = vclib.svn.expand_root_parent(pp)
    else:
      roots = {}
    if roots.has_key(rootname):
      return roots[rootname]
  return None

def locate_root(cfg, rootname):
  """Return a 2-tuple ROOTTYPE, ROOTPATH for configured ROOTNAME."""
  if cfg.general.cvs_roots.has_key(rootname):
    return 'cvs', cfg.general.cvs_roots[rootname]
  path_in_parent = find_root_in_parents(cfg, rootname, 'cvs')
  if path_in_parent:
    cfg.general.cvs_roots[rootname] = path_in_parent
    return 'cvs', path_in_parent
  if cfg.general.svn_roots.has_key(rootname):
    return 'svn', cfg.general.svn_roots[rootname]
  path_in_parent = find_root_in_parents(cfg, rootname, 'svn')
  if path_in_parent:
    cfg.general.svn_roots[rootname] = path_in_parent
    return 'svn', path_in_parent
  return None, None
  
def load_config(pathname=None, server=None):
  debug.t_start('load-config')

  if pathname is None:
    pathname = (os.environ.get("VIEWVC_CONF_PATHNAME")
                or os.environ.get("VIEWCVS_CONF_PATHNAME")
                or os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "viewvc.conf"))

  cfg = config.Config()
  cfg.set_defaults()
  cfg.load_config(pathname, server and server.getenv("HTTP_HOST"))

  # Load mime types file(s), but reverse the order -- our
  # configuration uses a most-to-least preferred approach, but the
  # 'mimetypes' package wants things the other way around.
  if cfg.general.mime_types_files:
    files = cfg.general.mime_types_files[:]
    files.reverse()
    files = map(lambda x, y=pathname: os.path.join(os.path.dirname(y), x), files)
    mimetypes.init(files)
  
  debug.t_end('load-config')
  return cfg


def view_error(server, cfg):
  exc_dict = debug.GetExceptionData()
  status = exc_dict['status']
  if exc_dict['msg']:
    exc_dict['msg'] = server.escape(exc_dict['msg'])
  if exc_dict['stacktrace']:
    exc_dict['stacktrace'] = server.escape(exc_dict['stacktrace'])
  handled = 0
  
  # use the configured error template if possible
  try:
    if cfg and not server.headerSent:
      server.header(status=status)
      template = get_view_template(cfg, "error")
      template.generate(server.file(), exc_dict)
      handled = 1
  except:
    pass

  # but fallback to the old exception printer if no configuration is
  # available, or if something went wrong
  if not handled:
    debug.PrintException(server, exc_dict)

def main(server, cfg):
  try:
    debug.t_start('main')
    try:
      # build a Request object, which contains info about the HTTP request
      request = Request(server, cfg)
      request.run_viewvc()
    except SystemExit, e:
      return
    except:
      view_error(server, cfg)

  finally:
    debug.t_end('main')
    debug.t_dump(server.file())
    debug.DumpChildren(server)


class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
