# -*-python-*-
#
# Copyright (C) 1999-2002 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://viewcvs.sourceforge.net/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewcvs.sourceforge.net/
#
# -----------------------------------------------------------------------
#
# viewcvs: View CVS repositories via a web browser
#
# -----------------------------------------------------------------------
#
# This software is based on "cvsweb" by Henner Zeller (which is, in turn,
# derived from software by Bill Fenner, with additional modifications by
# Henrik Nordstrom and Ken Coar). The cvsweb distribution can be found
# on Zeller's site:
#   http://stud.fh-heilbronn.de/~zeller/cgi/cvsweb.cgi/
#
# -----------------------------------------------------------------------
#

__version__ = '1.0-dev'

#########################################################################
#
# INSTALL-TIME CONFIGURATION
#
# These values will be set during the installation process. During
# development, they will remain None.
#

CONF_PATHNAME = None

#########################################################################

# this comes from our library; measure the startup time
import debug
debug.t_start('startup')
debug.t_start('imports')

# standard modules that we know are in the path or builtin
import sys
import os
import sapi
import cgi
import string
import urllib
import mimetypes
import time
import re
import rfc822
import stat
import struct
import types
import tempfile

# these modules come from our library (the stub has set up the path)
import compat
import config
import popen
import ezt
import accept
import vclib

debug.t_end('imports')

#########################################################################

checkout_magic_path = '*checkout*'
# According to RFC 1738 the '~' character is unsafe in URLs.
# But for compatibility with URLs bookmarked with older releases of ViewCVS:
oldstyle_checkout_magic_path = '~checkout~'
docroot_magic_path = '*docroot*'
viewcvs_mime_type = 'text/vnd.viewcvs-markup'
alt_mime_type = 'text/x-cvsweb-markup'

# put here the variables we need in order to hold our state - they will be
# added (with their current value) to any link/query string you construct
_sticky_vars = (
  'root',
  'hideattic',
  'sortby',
  'sortdir',
  'logsort',
  'diff_format',
  'only_with_tag',
  'search',
  'dir_pagestart',
  'log_pagestart',
  )

# for reading/writing between a couple descriptors
CHUNK_SIZE = 8192

# for rcsdiff processing of header
_RCSDIFF_IS_BINARY = 'binary'
_RCSDIFF_ERROR = 'error'

# global configuration:
cfg = None # see below

# special characters that don't need to be URL encoded
_URL_SAFE_CHARS = "/*~"

if CONF_PATHNAME:
  # installed
  g_install_dir = os.path.dirname(CONF_PATHNAME)
else:
  # development directories
  g_install_dir = os.path.join(os.pardir, os.pardir) # typically, "../.."


class Request:
  def __init__(self, server):
    self.server = server
    self.script_name = server.getenv('SCRIPT_NAME', '')
    self.browser = server.getenv('HTTP_USER_AGENT', 'unknown')

    # in lynx, it it very annoying to have two links per file, so
    # disable the link at the icon in this case:
    self.no_file_links = string.find(self.browser, 'Lynx') != -1

    # newer browsers accept gzip content encoding and state this in a
    # header (netscape did always but didn't state it) It has been
    # reported that these braindamaged MS-Internet Explorers claim
    # that they accept gzip .. but don't in fact and display garbage
    # then :-/
    self.may_compress = (
      ( string.find(server.getenv('HTTP_ACCEPT_ENCODING', ''), 'gzip') != -1
        or string.find(self.browser, 'Mozilla/3') != -1)
      and string.find(self.browser, 'MSIE') == -1
      )

    # process the Accept-Language: header
    hal = server.getenv('HTTP_ACCEPT_LANGUAGE','')
    self.lang_selector = accept.language(hal)
    self.language = self.lang_selector.select_from(cfg.general.languages)

    # load the key/value files, given the selected language
    self.kv = cfg.load_kv_files(self.language)

  def run_viewcvs(self):
    
    # global needed because "import vclib.svn" causes the
    # interpreter to make vclib a local variable
    global vclib

    # This function first parses the query string and sets the following
    # variables. Then it executes the request.
    self.view_func = None  # function to call to process the request
    self.repos = None      # object representing current repository
    self.rootname = None   # name of current root (as used in viewcvs.conf)
    self.roottype = None   # current root type ('svn' or 'cvs')
    self.rootpath = None   # physical path to current root
    self.pathtype = None   # type of path, either vclib.FILE or vclib.DIR
    self.where = None      # path to file or directory in current root
    self.query_dict = None # validated and cleaned up query options
    self.path_parts = None # for convenience, equals where.split('/')

    # Process PATH_INFO component of query string
    path_info = self.server.getenv('PATH_INFO', '')

    # clean it up. this removes duplicate '/' characters and any that may
    # exist at the front or end of the path.
    path_parts = filter(None, string.split(path_info, '/'))

    if path_parts:
      # handle magic path prefixes
      if path_parts[0] == docroot_magic_path:
        # if this is just a simple hunk of doc, then serve it up
        self.where = string.join(path_parts[1:], '/')
        return view_doc(self)
      elif path_parts[0] in (checkout_magic_path, oldstyle_checkout_magic_path):
        path_parts.pop(0)
        self.view_func = view_checkout

      # see if we are treating the first path component (after any
      # magic) as the repository root.  if there are parts, and the
      # first component is a named root, use it as such.  else, we'll be
      # falling back to the default root a little later.
      if cfg.options.root_as_url_component and path_parts \
         and list_roots(cfg).has_key(path_parts[0]):
        self.rootname = path_parts.pop(0)

    self.where = string.join(path_parts, '/')
    self.path_parts = path_parts

    # Done with PATH_INFO, now parse the query params
    self.query_dict = {}

    for name, values in self.server.params().items():
      # patch up old queries that use 'cvsroot' to look like they used 'root'
      if name == 'cvsroot':
        name = 'root'

      # validate the parameter
      _validate_param(name, values[0])

      # if we're here, then the parameter is okay
      self.query_dict[name] = values[0]
    
    # Special handling for root parameter
    root_param = self.query_dict.get('root', None)
    if root_param:
      self.rootname = root_param
      
      # in root_as_url_component mode, if we see a root in the query
      # data, we'll redirect to the new url schema.  it may fail, but
      # at least we tried.
      if cfg.options.root_as_url_component:
        del self.query_dict['root']
        self.server.redirect(self.get_url())

    elif self.rootname is None:
      self.rootname = cfg.general.default_root
                                         
    # If this is a forbidden path, stop now
    if path_parts and cfg.is_forbidden(path_parts[0]):
      raise debug.ViewCVSException('Access to "%s" is forbidden.'
                                   % path_parts[0], '403 Forbidden')

    # Create the repository object
    if cfg.general.cvs_roots.has_key(self.rootname):
      self.rootpath = cfg.general.cvs_roots[self.rootname]
      try:
        if cfg.general.use_rcsparse:
          import vclib.ccvs
          self.repos = vclib.ccvs.CCVSRepository(self.rootname, self.rootpath)
        else:
          import vclib.bincvs
          self.repos = vclib.bincvs.BinCVSRepository(self.rootname, 
                                                     self.rootpath,
                                                     cfg.general)
        self.roottype = 'cvs'
      except vclib.ReposNotFound:
        raise debug.ViewCVSException(
          '%s not found!\nThe wrong path for this repository was '
          'configured, or the server on which the CVS tree lives may be '
          'down. Please try again in a few minutes.'
          % self.server.escape(self.rootname))
      # required so that spawned rcs programs correctly expand $CVSHeader$
      os.environ['CVSROOT'] = self.rootpath
    elif cfg.general.svn_roots.has_key(self.rootname):
      self.rootpath = cfg.general.svn_roots[self.rootname]
      try:
        if re.match(_re_rewrite_url, self.rootpath):
          # If the rootpath is a URL, we'll use the svn_ra module, but
          # lie about its name.
          import vclib.svn_ra
          vclib.svn = vclib.svn_ra
        else:
          import vclib.svn
        rev = None
        if self.query_dict.has_key('rev') \
          and self.query_dict['rev'] != 'HEAD':
          rev = int(self.query_dict['rev'])
        self.repos = vclib.svn.SubversionRepository(self.rootname,
                                                    self.rootpath, rev)
        self.roottype = 'svn'
      except vclib.ReposNotFound:
        raise debug.ViewCVSException(
          '%s not found!\nThe wrong path for this repository was '
          'configured, or the server on which the Subversion tree lives may'
          'be down. Please try again in a few minutes.'
          % self.server.escape(self.rootname))
      except vclib.InvalidRevision, ex:
        raise debug.ViewCVSException(str(ex))
    else:
      raise debug.ViewCVSException(
        'The root "%s" is unknown. If you believe the value is '
        'correct, then please double-check your configuration.'
        % self.server.escape(self.rootname), "404 Repository not found")

    # Make sure path exists
    self.pathtype = _repos_pathtype(self.repos, self.path_parts)

    # If the path doesn't exist, but we have CVS repository, and the
    # path doesn't already include an 'Attic' component, see if maybe
    # the thing lives in the Attic.
    if self.pathtype is None \
           and self.roottype == 'cvs' \
           and len(self.path_parts) > 1 \
           and not self.path_parts[-2] == 'Attic':
      attic_parts = self.path_parts[0:-1] + ['Attic'] + [self.path_parts[-1]]
      if _repos_pathtype(self.repos, attic_parts) == vclib.FILE:
        self.server.redirect(self.get_url(where=string.join(attic_parts, '/'),
                                          pathtype=vclib.FILE))
      
    if self.pathtype is None:
      # path doesn't exist, try stripping known fake suffixes
      result = _strip_suffix('.diff', self.where, self.path_parts,        \
                             vclib.FILE, self.repos, view_diff) or        \
               _strip_suffix('.tar.gz', self.where, self.path_parts,      \
                             vclib.DIR, self.repos, download_tarball) or  \
               _strip_suffix('root.tar.gz', self.where, self.path_parts,  \
                             vclib.DIR, self.repos, download_tarball)
      if result:
        self.where, self.path_parts, self.pathtype, self.view_func = result
      else:
        raise debug.ViewcvsException('%s: unknown location'
                                     % self.where, '404 Not Found')

    # Try to figure out what to do based on view parameter
    self.view_func = _views.get(self.query_dict.get('view', None), 
                                self.view_func)

    if self.view_func is None:
      # view parameter is not set, try looking at pathtype and the 
      # other parameters
      if self.pathtype == vclib.DIR:
        self.view_func = view_directory
      elif self.pathtype == vclib.FILE:
        if self.query_dict.has_key('r1') and self.query_dict.has_key('r2'):
          self.view_func = view_diff
        elif self.query_dict.has_key('r1') and self.query_dict.has_key('rev'):
          self.view_func = view_log
        elif self.query_dict.has_key('rev'):
          if self.query_dict.get('content-type', None) in (viewcvs_mime_type,
                                                           alt_mime_type):
            self.view_func = view_markup
          else:
            self.view_func = view_checkout
        elif self.query_dict.has_key('annotate'):
          self.view_func = view_annotate
        elif self.query_dict.has_key('tarball'):
          self.view_func = download_tarball
        elif self.query_dict.has_key('graph'):
          if not self.query_dict.has_key('makeimage'):
            self.view_func = view_cvsgraph
          else: 
            self.view_func = view_cvsgraph_image
        else:
          self.view_func = view_log
        
    # Finally done parsing query string, set some extra variables 
    # and call view_func
    self.full_name = self.rootpath + (self.where and '/' + self.where)
    if self.pathtype == vclib.FILE:
      self.setup_mime_type_info()

    # startup is done now.
    debug.t_end('startup')
    
    self.view_func(self)

  def get_url(self, **args):
    """Constructs a link to another ViewCVS page just like the get_link
    function except that it returns a single URL instead of a URL
    split into components"""

    url, params = apply(self.get_link, (), args)
    qs = compat.urlencode(params)
    if qs:
      return urllib.quote(url, _URL_SAFE_CHARS) + '?' + qs
    else:
      return urllib.quote(url, _URL_SAFE_CHARS)

  def get_link(self, view_func = None, rootname = None, where = None,
    params = None, pathtype = None):
    """Constructs a link pointing to another ViewCVS page. All arguments
    correspond to members of the Request object. If they are set to 
    None they take values from the current page. Return value is a base
    URL and a dictionary of parameters"""

    if view_func is None:
      view_func = self.view_func

    if rootname is None:
      rootname = self.rootname

    if params is None:
      params = self.query_dict.copy()

    # must specify both where and pathtype or neither
    assert (where is None) == (pathtype is None)

    # if we are asking for the revision info view, we don't need any
    # path information
    if view_func is view_revision:
      where = pathtype = None
    elif where is None:
      where = self.where
      pathtype = self.pathtype

    last_link = view_func is view_checkout or view_func is download_tarball

    # The logic used to construct the URL is an inverse of the
    # logic used to interpret URLs in Request.run_viewcvs

    url = self.script_name

    # add checkout magic if possible
    if view_func is view_checkout and cfg.options.checkout_magic: 
      url = url + '/' + checkout_magic_path
      view_func = None

    # add root name
    if cfg.options.root_as_url_component:
      url = url + '/' + rootname
    elif not (params.has_key('root') and params['root'] is None):
      if rootname != cfg.general.default_root:
        params['root'] = rootname
      else:
        params['root'] = None

    # add path
    if where and where != '':
      url = url + '/' + where

    # add suffix for tarball
    if view_func is download_tarball:
      if not where: url = url + '/root'
      url = url + '.tar.gz'
      if not params.has_key('only_with_tag'):
        params['only_with_tag'] = self.query_dict.get('only_with_tag')

    # add trailing slash for a directory      
    elif pathtype == vclib.DIR:
      url = url + '/'

    # no need to explicitly specify log view for a file, unless we
    # want the logs on a specific revision
    if view_func is view_log and pathtype == vclib.FILE and \
          not params.has_key('rev'):
      view_func = None

    # no need to explicitly specify directory view for a directory
    if view_func is view_directory and pathtype == vclib.DIR:
      view_func = None

    # no need to explicitly specify annotate view when
    # there's an annotate parameter
    if view_func is view_annotate and params.has_key('annotate'):
      view_func = None

    # For diffs on Subversion repositories, set rev to the value of r2
    # otherwise, we get 404's on moved files
    if view_func is view_diff and self.roottype == 'svn' \
       and not params.has_key('rev'):
      params['rev'] = params.get('r2')

    # no need to explicitly specify diff view when
    # there's r1 and r2 parameters
    if view_func is view_diff and params.has_key('r1') \
      and params.has_key('r2'):
      view_func = None

    # no need to explicitly specify checkout view when
    # there's a rev parameter
    if view_func is view_checkout and params.has_key('rev'):
      view_func = None

    view_code = _view_codes.get(view_func)
    if view_code and not (params.has_key('view') and params['view'] is None):
      params['view'] = view_code

    return url, self.get_options(params, not last_link)

  def get_options(self, params = {}, sticky_vars=1):
    """Combine params with current sticky values"""
    ret = { }
    if sticky_vars:
      for name in _sticky_vars:
        value = self.query_dict.get(name)
        if value is not None and not params.has_key(name):
          ret[name] = self.query_dict[name]
    for name, val in params.items():
      if val is not None:
        ret[name] = val
    return ret

  def setup_mime_type_info(self):
    if cfg.general.mime_types_file:
      mimetypes.init([cfg.general.mime_types_file])
    self.mime_type, self.encoding = mimetypes.guess_type(self.where)
    if not self.mime_type:
      self.mime_type = 'text/plain'
    self.default_viewable = cfg.options.allow_markup and \
                            (is_viewable_image(self.mime_type)
                             or is_text(self.mime_type))

def _validate_param(name, value):
  """Validate whether the given value is acceptable for the param name.

  If the value is not allowed, then an error response is generated, and
  this function throws an exception. Otherwise, it simply returns None.
  """

  try:
    validator = _legal_params[name]
  except KeyError:
    raise debug.ViewcvsException(
      'An illegal parameter name ("%s") was passed.' % cgi.escape(name),
      '400 Bad Request')

  if validator is None:
    return

  # is the validator a regex?
  if hasattr(validator, 'match'):
    if not validator.match(value):
      raise debug.ViewcvsException(
        'An illegal value ("%s") was passed as a parameter.' %
        cgi.escape(value), '400 Bad Request')
    return

  # the validator must be a function
  validator(value)

def _validate_regex(value):
  # hmm. there isn't anything that we can do here.

  ### we need to watch the flow of these parameters through the system
  ### to ensure they don't hit the page unescaped. otherwise, these
  ### parameters could constitute a CSS attack.
  pass

# obvious things here. note that we don't need uppercase for alpha.
_re_validate_alpha = re.compile('^[a-z]+$')
_re_validate_number = re.compile('^[0-9]+$')

# when comparing two revs, we sometimes construct REV:SYMBOL, so ':' is needed
_re_validate_revnum = re.compile('^[-_.a-zA-Z0-9:~]*$')

# it appears that RFC 2045 also says these chars are legal: !#$%&'*+^{|}~`
# but woah... I'll just leave them out for now
_re_validate_mimetype = re.compile('^[-_.a-zA-Z0-9/]+$')

# date time values
_re_validate_datetime = re.compile(r'^(\d\d\d\d-\d\d-\d\d(\s+\d\d:\d\d(:\d\d)?)?)?$')

# the legal query parameters and their validation functions
_legal_params = {
  'root'          : None,
  'view'          : None,
  'search'        : _validate_regex,
  'p1'            : None,
  'p2'            : None,
  
  'hideattic'     : _re_validate_number,
  'sortby'        : _re_validate_alpha,
  'sortdir'       : _re_validate_alpha,
  'logsort'       : _re_validate_alpha,
  'diff_format'   : _re_validate_alpha,
  'only_with_tag' : _re_validate_revnum,
  'dir_pagestart' : _re_validate_number,
  'log_pagestart' : _re_validate_number,
  'hidecvsroot'   : _re_validate_number,
  'makepatch'    : _re_validate_number,
  'annotate'      : _re_validate_revnum,
  'graph'         : _re_validate_revnum,
  'makeimage'     : _re_validate_number,
  'tarball'       : _re_validate_number,
  'r1'            : _re_validate_revnum,
  'tr1'           : _re_validate_revnum,
  'r2'            : _re_validate_revnum,
  'tr2'           : _re_validate_revnum,
  'rev'           : _re_validate_revnum,
  'content-type'  : _re_validate_mimetype,

  # for query
  'branch'        : _validate_regex,
  'branch_match'  : _re_validate_alpha,
  'dir'           : None,
  'file'          : _validate_regex,
  'file_match'    : _re_validate_alpha,
  'who'           : _validate_regex,
  'who_match'     : _re_validate_alpha,
  'querysort'     : _re_validate_alpha,
  'date'          : _re_validate_alpha,
  'hours'         : _re_validate_number,
  'mindate'       : _re_validate_datetime,
  'maxdate'       : _re_validate_datetime,
  'format'        : _re_validate_alpha,
  }

# regex used to move from a file to a directory
_re_up_path       = re.compile('(^|/)[^/]+$')
_re_up_attic_path = re.compile('(^|/)(Attic/)?[^/]+$')
def get_up_path(request, path, hideattic=0):
  if request.roottype == 'svn' or hideattic:
    return re.sub(_re_up_path, '', path)
  else:
    return re.sub(_re_up_attic_path, '', path)

def _strip_suffix(suffix, where, path_parts, pathtype, repos, view_func):
  """strip the suffix from a repository path if the resulting path
  is of the specified type, otherwise return None"""
  l = len(suffix)
  if where[-l:] == suffix:
    path_parts = path_parts[:]
    if len(path_parts[-1]) == l:
      del path_parts[-1]
    else:
      path_parts[-1] = path_parts[-1][:-l]
    t = _repos_pathtype(repos, path_parts)
    if pathtype == t:
      return where[:-l], path_parts, t, view_func
  return None

def _repos_pathtype(repos, path_parts):
  """return the type of a repository path, or None if the path
  does not exist"""
  type = None
  try:
    type = repos.itemtype(path_parts)
  except vclib.ItemNotFound:
    pass
  return type

def check_freshness(request, mtime=None, etag=None, weak=0):
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

  ## require revalidation after 15 minutes ...
  if cfg and cfg.options.http_expiration_time >= 0:
    expiration = rfc822.formatdate(time.time() +
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
      request.server.addheader('Last-Modified', rfc822.formatdate(mtime))
  return isfresh

def generate_page(request, tname, data):
  # allow per-language template selection
  if request:
    tname = string.replace(tname, '%lang%', request.language)
  else:
    tname = string.replace(tname, '%lang%', 'en')

  debug.t_start('ezt-parse')
  template = ezt.Template(os.path.join(g_install_dir, tname))
  debug.t_end('ezt-parse')

  template.generate(sys.stdout, data)

def clickable_path(request, leaf_is_link, drop_leaf):
  where = ''
  s = '<a href="%s#dirlist">[%s]</a>' % (_dir_url(request, where),
                                         request.repos.name)

  for part in request.path_parts[:-1]:
    if where: where = where + '/'
    where = where + part
    s = s + ' / <a href="%s#dirlist">%s</a>' % (_dir_url(request, where), part)

  if not drop_leaf and request.path_parts:
    if leaf_is_link:
      s = s + ' / %s' % (request.path_parts[-1])
    else:
      if request.pathtype == vclib.DIR:
        url = request.get_url(view_func=view_directory, params={}) + '#dirlist'
      else:
        url = request.get_url(view_func=view_log, params={})
      s = s + ' / <a href="%s">%s</a>' % (url, request.path_parts[-1])

  return s

def _dir_url(request, where):
  """convenient wrapper for get_url used by clickable_path()"""
  rev = None
  if request.roottype == "svn":
    rev = request.repos.rev
  return request.get_url(view_func=view_directory, where=where, 
                         pathtype=vclib.DIR, params={'rev' : rev})


def prep_tags(request, tags):
  url, params = request.get_link(params={'only_with_tag': None})
  params = compat.urlencode(params)
  if params:
    url = urllib.quote(url, _URL_SAFE_CHARS) + '?' + params + '&only_with_tag='
  else:
    url = urllib.quote(url, _URL_SAFE_CHARS) + '?only_with_tag='

  links = [ ]
  for tag in tags:
    links.append(_item(name=tag.name, href=url+tag.name))
  links.sort(lambda a, b: cmp(a.name, b.name))
  return links

def is_viewable_image(mime_type):
  return mime_type in ('image/gif', 'image/jpeg', 'image/png')

def is_text(mime_type):
  return mime_type[:5] == 'text/'

_re_rewrite_url = re.compile('((http|https|ftp|file|svn|svn\+ssh)(://[-a-zA-Z0-9%.~:_/]+)([?&]([-a-zA-Z0-9%.~:_]+)=([-a-zA-Z0-9%.~:_])+)*(#([-a-zA-Z0-9%.~:_]+)?)?)')
_re_rewrite_email = re.compile('([-a-zA-Z0-9_.]+@([-a-zA-Z0-9]+\.)+[A-Za-z]{2,4})')
def htmlify(html):
  html = cgi.escape(html)
  html = re.sub(_re_rewrite_url, r'<a href="\1">\1</a>', html)
  html = re.sub(_re_rewrite_email, r'<a href="mailto:\1">\1</a>', html)
  return html

def format_log(log):
  s = htmlify(log[:cfg.options.short_log_len])
  if len(log) > cfg.options.short_log_len:
    s = s + '...'
  return s

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

def common_template_data(request):
  data = {
    'cfg' : cfg,
    'vsn' : __version__,
    'kv'  : request.kv,
    'icons' : cfg.options.icons,
    'docroot' : cfg.options.docroot is None                        \
                and request.script_name + '/' + docroot_magic_path \
                or cfg.options.docroot,
    'where' : request.where,
    'roottype' : request.roottype,
    'rootname' : request.rootname,
    'pathtype' : request.pathtype == vclib.DIR and 'dir' or 'file',
    'nav_path' : clickable_path(request, 1, 0),
  }
  url, params = request.get_link(view_func=view_directory,
                                 where='',
                                 pathtype=vclib.DIR,
                                 params={'root': None})
  data['change_root_action'] = urllib.quote(url, _URL_SAFE_CHARS)
  data['change_root_hidden_values'] = prepare_hidden_values(params)
  # add in the roots for the selection
  roots = []
  allroots = list_roots(cfg)
  if len(allroots) >= 2:
    rootnames = allroots.keys()
    rootnames.sort(icmp)
    for rootname in rootnames:
      roots.append(_item(name=rootname, type=allroots[rootname][1]))
  data['roots'] = roots
  return data

def nav_header_data(request, rev):
  path, filename = os.path.split(request.where)
  if request.roottype == 'cvs' and path[-6:] == '/Attic':
    path = path[:-6]

  data = common_template_data(request)
  data.update({
    'path' : path,
    'filename' : filename,
    'file_url' : request.get_url(view_func=view_log, params={}),
    'rev' : rev
  })
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
  
def copy_stream(src, dst=None):
  if dst is None:
    dst = sys.stdout
  while 1:
    chunk = retry_read(src)
    if not chunk:
      break
    dst.write(chunk)

class MarkupBuffer:
  """A file-pointer-ish object from a string buffer"""
  
  def __init__(self, buffer):
    self.buffer = buffer
    self.size = len(buffer)
    
  def read(self, reqlen=None):
    if not self.size > 0:
      return None
    if not reqlen:
      reqlen = self.size
    if not reqlen > 0:
      return ''
    if reqlen > self.size:
      reqlen = self.size
    chunk = self.buffer[0:reqlen]
    self.buffer = self.buffer[reqlen:]
    self.size = self.size - reqlen
    return chunk
  def close(self):
    self.buffer = ''
    self.size = 0

class MarkupPipeWrapper:
  """A file-pointer-ish object from another filepointer, plus some optional
  pre- and post- text.  Closes and closes FP."""
  
  def __init__(self, fp, pretext=None, posttext=None, htmlize=1):
    # Setup a list of fps to read from (actually, a list of tuples
    # tracking the fp and whether or not to htmlize() the stuff read
    # from that fp).  We read from a given fp only after exhausting
    # all the ones prior to it in the list.
    self.fps = []
    if pretext:
      self.fps.append([MarkupBuffer(pretext), 0])
    if fp:
      self.fps.append([fp, htmlize])
    if posttext:
      self.fps.append([MarkupBuffer(posttext), 0])
    self.which_fp = 0

  def read(self, reqlen):
    if not self.which_fp < len(self.fps):
      return None
    if not reqlen > 0:
      return ''
    
    chunk = None
    while reqlen > 0 and self.which_fp < len(self.fps):
      fp, htmlize = self.fps[self.which_fp]
      readchunk = retry_read(fp, reqlen)
      if readchunk:
        if htmlize:
          readchunk = htmlify(readchunk)
        readlen = len(readchunk)
        reqlen = reqlen - readlen
        chunk = (chunk or '') + readchunk
      else:
        self.which_fp = self.which_fp + 1
    return chunk

  def close(self):
    for pair in self.fps:
      pair[0].close()
    del self.fps[:]

  def __del__(self):
    self.close()

class MarkupEnscript:
  """A file-pointer-ish object for reading file contents slammed
  through the 'enscript' tool.  Consumes and closes FP."""
  
  def __init__(self, enscript_path, lang, fp):
    ### Man, oh, man, had I any idea how to deal with bi-directional
    ### pipes, I would.  But I don't.

    self._closed = 0
    self.temp_file = tempfile.mktemp()
    self.fp = None
    
    # I've tried to pass option '-C' to enscript to generate line numbers
    # Unfortunately this option doesn't work with HTML output in enscript
    # version 1.6.2.
    enscript_cmd = [os.path.normpath(os.path.join(cfg.options.enscript_path,
                                                  'enscript')),
                    '--color', '--language=html', '--pretty-print=' + lang,
                    '-o', self.temp_file, '-']
    try:
      copy_stream(fp, popen.pipe_cmds([enscript_cmd]))
      fp.close()
    except IOError:
      raise debug.ViewcvsException('Error running external program. ' +
                                   'Command line was: %s'
                                   % string.join(enscript_cmd, ' '))

    ### I started to use '1,/^<PRE>$/d;/<\\/PRE>/,$d;p' here to
    ### actually strip out the <PRE> and </PRE> tags, too, but I
    ### couldn't think of any good reason to do that.
    self.fp = popen.popen('sed',
                          ['-n', '/^<PRE>$/,/<\\/PRE>$/p', self.temp_file],
                          'rb', 0)

  def __del__(self):
    self.close()

  def close(self):
    if not self._closed:
      # Cleanup the tempfile we made, and close the pipe.
      os.remove(self.temp_file)
      if self.fp:
        self.fp.close()
    self._closed = 1

  def read(self, len):
    if self.fp is None:
      return None
    return retry_read(self.fp, len)

class MarkupPHP:
  """A file-pointer-ish object for reading file contents slammed
  through the 'php' tool.  Consumes and closes FP."""
  
  def __init__(self, php_exe_path, fp):
    ### Man, oh, man, had I any idea how to deal with bi-directional
    ### pipes, I would.  But I don't.

    self.temp_file = tempfile.mktemp()
    self.fp = None

    # Dump the version resource contents to our tempfile
    copy_stream(fp, open(self.temp_file, 'wb'))
    fp.close()
    
    self.fp = popen.popen(php_exe_path,
                          ['-q', '-s', '-n', '-f', self.temp_file],
                          'rb', 0)

  def __del__(self):
    # Cleanup the tempfile we made, and close the pipe.
    os.remove(self.temp_file)
    if self.fp:
      self.fp.close()
    
  def read(self, len):
    if self.fp is None:
      return None
    return retry_read(self.fp, len)

def markup_stream_python(fp):
  ### Convert this code to use the recipe at:
  ###     http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52298
  ### Note that the cookbook states all the code is licensed according to
  ### the Python license.
  try:
    # See if Marc-Andre Lemburg's py2html stuff is around.
    # http://www.egenix.com/files/python/SoftwareDescriptions.html#py2html.py
    ### maybe restrict the import to *only* this directory?
    sys.path.insert(0, cfg.options.py2html_path)
    import py2html
    import PyFontify
  except ImportError:
    return None

  ### It doesn't escape stuff quite right, nor does it munge URLs and
  ### mailtos as well as we do.
  html = cgi.escape(fp.read())
  pp = py2html.PrettyPrint(PyFontify.fontify, "rawhtml", "color")
  html = pp.fontify(html)
  html = re.sub(_re_rewrite_url, r'<a href="\1">\1</a>', html)
  html = re.sub(_re_rewrite_email, r'<a href="mailto:\1">\1</a>', html)
  return MarkupBuffer(html)

def markup_stream_php(fp):
  if not cfg.options.use_php:
    return None

  sys.stdout.flush()

  # clearing the following environment variables prevents a 
  # "No input file specified" error from the php cgi executable
  # when ViewCVS is running under a cgi environment. when the
  # php cli executable is used they can be left alone
  #
  #os.putenv("GATEWAY_INTERFACE", "")
  #os.putenv("PATH_TRANSLATED", "")
  #os.putenv("REQUEST_METHOD", "")
  #os.putenv("SERVER_NAME", "")
  #os.putenv("SERVER_SOFTWARE", "")

  return MarkupPHP(cfg.options.php_exe_path, fp)

markup_streamers = {
# '.py' : markup_stream_python,
  '.php' : markup_stream_php,
  '.inc' : markup_stream_php,
  }

### this sucks... we have to duplicate the extensions defined by enscript
enscript_extensions = {
  '.C' : 'cpp',
  '.EPS' : 'postscript',
  '.DEF' : 'modula_2',  # requires a patch for enscript 1.6.2, see INSTALL
  '.F' : 'fortran',
  '.H' : 'cpp',
  '.MOD' : 'modula_2',  # requires a patch for enscript 1.6.2, see INSTALL
  '.PS' : 'postscript',
  '.S' : 'asm',
  '.SH' : 'sh',
  '.ada' : 'ada',
  '.adb' : 'ada',
  '.ads' : 'ada',
  '.awk' : 'awk',
  '.c' : 'c',
  '.c++' : 'cpp',
  '.cc' : 'cpp',
  '.cpp' : 'cpp',
  '.csh' : 'csh',
  '.cxx' : 'cpp',
  '.diff' : 'diffu',
  '.dpr' : 'delphi',
  '.el' : 'elisp',
  '.eps' : 'postscript',
  '.f' : 'fortran',
  '.for': 'fortran',
  '.gs' : 'haskell',
  '.h' : 'c',
  '.hpp' : 'cpp',
  '.hs' : 'haskell',
  '.htm' : 'html',
  '.html' : 'html',
  '.idl' : 'idl',
  '.java' : 'java',
  '.js' : 'javascript',
  '.lgs' : 'haskell',
  '.lhs' : 'haskell',
  '.m' : 'objc',
  '.m4' : 'm4',
  '.man' : 'nroff',
  '.nr' : 'nroff',
  '.p' : 'pascal',
  '.pas' : 'delphi', ### Might instead be 'pascal'.
  '.patch' : 'diffu',
  '.pkg' : 'sql', ### Oracle SQL, but might be something else.
  '.pl' : 'perl',
  '.pm' : 'perl',
  '.pp' : 'pascal',
  '.ps' : 'postscript',
  '.py' : 'python',
  '.s' : 'asm',
  '.scheme' : 'scheme',
  '.scm' : 'scheme',
  '.scr' : 'synopsys',
  '.sh' : 'sh',
  '.shtml' : 'html',
  '.sql' : 'sql',
  '.st' : 'states',
  '.syn' : 'synopsys',
  '.synth' : 'synopsys',
  '.tcl' : 'tcl',
  '.tex' : 'tex',
  '.texi' : 'tex',
  '.texinfo' : 'tex',
  '.v' : 'verilog',
  '.vba' : 'vba',
  '.vh' : 'verilog',
  '.vhd' : 'vhdl',
  '.vhdl' : 'vhdl',
  }
enscript_filenames = {
  '.emacs' : 'elisp',
  'GNUmakefile' : 'makefile',
  'Makefile' : 'makefile',
  'makefile' : 'makefile',
  'ChangeLog' : 'changelog',
  }


def make_time_string(date):
  """Returns formatted date string in either local time or UTC.

  The passed in 'date' variable is seconds since epoch.

  """
  if date is None:
    return 'Unknown date'
  if (cfg.options.use_localtime):
    localtime = time.localtime(date)
    return time.asctime(localtime) + ' ' + time.tzname[localtime[8]]
  else:
    return time.asctime(time.gmtime(date)) + ' UTC'

def view_auto(request):
  if request.default_viewable:
    view_markup(request)
  else:
    view_checkout(request)

def view_markup(request):
  full_name = request.full_name
  where = request.where
  query_dict = request.query_dict
  rev = request.query_dict.get('rev')

  fp, revision = request.repos.openfile(request.path_parts, rev)

  # Since the templates could be changed by the user, we can't provide
  # a strong validator for this page, so we mark the etag as weak.
  if check_freshness(request, None, revision, weak=1):
    fp.close()
    return

  data = nav_header_data(request, revision)
  data.update({
    'nav_file' : clickable_path(request, 1, 0),
    'mime_type' : request.mime_type,
    'log' : None,
    'tag' : None,
    })

  data['download_href'] = request.get_url(view_func=view_checkout,
                                          params={'rev': rev})
  if request.mime_type != 'text/plain':
    data['download_text_href'] = \
      request.get_url(view_func=view_checkout,
                      params={'content-type': 'text/plain', 'rev': rev})
  else:
    data['download_text_href'] = None


  if cfg.options.show_log_in_markup:
    options = {}
    revs = request.repos.filelog(request.path_parts, revision, options)
    entry = revs[-1]

    data.update({
        'date_str' : make_time_string(entry.date),
        'ago' : None,
        'author' : entry.author,
        'branches' : None,
        'tags' : None,
        'branch_points' : None,
        'changed' : entry.changed,
        'log' : htmlify(entry.log),
        'size' : entry.size,
        'state' : None,
        'vendor_branch' : None,
        'prev' : None,
        })

    if entry.date is not None:
      data['ago'] = html_time(request, entry.date, 1)
      
    if request.roottype == 'cvs':
      branch = entry.branch_number
      prev = entry.prev or entry.parent
      data.update({
        'state' : entry.dead and 'dead',
        'prev' : prev and prev.string,
        'vendor_branch' : ezt.boolean(branch and branch[2] % 2 == 1),
        'branches' : string.join(map(lambda x: x.name, entry.branches), ', '),
        'tags' : string.join(map(lambda x: x.name, entry.tags), ', '),
        'branch_points': string.join(map(lambda x: x.name,
                                         entry.branch_points), ', ')
        })

  else:
    data['tag'] = query_dict.get('only_with_tag')

  markup_fp = None
  if is_viewable_image(request.mime_type):
    fp.close()
    url = request.get_url(view_func=view_checkout, params={'rev': rev})
    markup_fp = MarkupBuffer('<img src="%s"><br>' % url)
  else:
    basename, ext = os.path.splitext(data['filename'])
    streamer = markup_streamers.get(ext)
    if streamer:
      markup_fp = streamer(fp)
    elif cfg.options.use_enscript:
      lang = enscript_extensions.get(ext)
      if not lang:
        lang = enscript_filenames.get(basename)
      if lang and lang not in cfg.options.disable_enscript_lang:
        markup_fp = MarkupEnscript(cfg.options.enscript_path, lang, fp)

  # If no one has a suitable markup handler, we'll use the default.
  if not markup_fp:
    markup_fp = MarkupPipeWrapper(fp, '<pre>', '</pre>')
    
  data['markup'] = markup_fp
  
  request.server.header()
  generate_page(request, cfg.templates.markup, data)

def revcmp(rev1, rev2):
  rev1 = map(int, string.split(rev1, '.'))
  rev2 = map(int, string.split(rev2, '.'))
  return cmp(rev1, rev2)

def prepare_hidden_values(params):
  """returns variables from params encoded as a invisible HTML snippet.
  """
  hidden_values = []
  for name, value in params.items():
    hidden_values.append('<input type="hidden" name="%s" value="%s" />' %
                         (name, value))
  return string.join(hidden_values, '')

def sort_file_data(file_data, sortdir, sortby):
  def file_sort_cmp(file1, file2, sortby=sortby):
    if file1.kind == vclib.DIR:        # is_directory
      if file2.kind == vclib.DIR:
        # both are directories. sort on name.
        return cmp(file1.name, file2.name)
      # file1 is a directory, it sorts first.
      return -1
    if file2.kind == vclib.DIR:
      # file2 is a directory, it sorts first.
      return 1

    # we should have data on these. if not, then it is because we requested
    # a specific tag and that tag is not present on the file.
    if file1.rev is not None and file2.rev is not None:
      # both are files, sort according to sortby
      if sortby == 'rev':
        return revcmp(file1.rev, file2.rev)
      elif sortby == 'date':
        return cmp(file2.date, file1.date)        # latest date is first
      elif sortby == 'log':
        return cmp(file1.log, file2.log)
      elif sortby == 'author':
        return cmp(file1.author, file2.author)
    elif file1.rev is not None:
      return -1
    elif file2.rev is not None:
      return 1

    # sort by file name
    return cmp(file1.name, file2.name)

  file_data.sort(file_sort_cmp)

  if sortdir == "down":
    file_data.reverse()

def icmp(x, y):
  """case insensitive comparison"""
  return cmp(string.lower(x), string.lower(y))

def view_directory(request):
  # if we have a directory and the request didn't end in "/", then redirect
  # so that it does.
  if request.server.getenv('PATH_INFO', '')[-1:] != '/':
    request.server.redirect(request.get_url())

  # List current directory
  options = {}
  if request.roottype == 'cvs':
    view_tag = request.query_dict.get('only_with_tag')
    hideattic = int(request.query_dict.get('hideattic', 
                                           cfg.options.hide_attic))
    options["cvs_list_attic"] = not hideattic or view_tag
    options["cvs_subdirs"] = (cfg.options.show_subdir_lastmod and
                              cfg.options.show_logs)
    options["cvs_dir_tag"] = view_tag

  file_data = request.repos.listdir(request.path_parts, options)

  # Filter file list if a regex is specified
  search_re = request.query_dict.get('search', '')
  if cfg.options.use_re_search and search_re:
    file_data = search_files(request.repos, request.path_parts,
                             file_data, search_re)

  # Retrieve log messages, authors, revision numbers, timestamps
  request.repos.dirlogs(request.path_parts, file_data, options)

  # sort with directories first, and using the "sortby" criteria
  sortby = request.query_dict.get('sortby', cfg.options.sort_by) or 'file'
  sortdir = request.query_dict.get('sortdir', 'up')
  sort_file_data(file_data, sortdir, sortby)

  # loop through entries creating rows and changing these values
  rows = [ ]
  num_files = 0
  num_displayed = 0
  unreadable = 0

  # set some values to be used inside loop
  where = request.where
  where_prefix = where and where + '/'
  if request.roottype == 'svn':
    dir_params = {'rev': request.query_dict.get('rev')}    
  else:
    dir_params = {}

  ### display a row for ".." ?
  for file in file_data:
    row = _item(href=None, graph_href=None,
                author=None, log=None, log_file=None, log_rev=None,
                show_log=None, state=None, size=None, mime_type=None)

    if file.log_error:
      row.state = 'error'
      unreadable = 1
    elif file.rev is None:
      row.state = 'none'
    else:
      row.rev = file.rev
      row.author = file.author or "&nbsp;"
      if request.roottype == 'cvs' and file.dead:
        row.state = 'dead'
      else:
        row.state = ''
      row.time = None
      if file.date is not None:
        row.time = html_time(request, file.date)
      if cfg.options.show_logs and file.log is not None:
        row.show_log = 'yes'
        row.log = format_log(file.log)

    row.anchor = file.name
    row.name = file.name

    row.type = (file.kind == vclib.FILE and 'file') or \
               (file.kind == vclib.DIR and 'dir')

    if file.verboten or not row.type:
      row.type = 'unreadable'
      unreadable = 1

    if (where == '') and (cfg.is_forbidden(file.name)):
      continue
                             
    if file.kind == vclib.DIR:
      if (request.roottype == 'cvs' and
          ((file.name == 'CVS') or # CVS directory is for fileattr
           (not hideattic and file.name == 'Attic') or
           (where == '' and (file.name == 'CVSROOT' and 
                             cfg.options.hide_cvsroot)))):
        continue
    
      row.href = request.get_url(view_func=view_directory,
                                 where=where_prefix+file.name,
                                 pathtype=vclib.DIR,
                                 params=dir_params)

      if request.roottype == 'cvs' and file.rev is not None:
        if cfg.options.use_cvsgraph:
          row.graph_href = '&nbsp;' 
        if cfg.options.show_logs:
          row.log_file = file.newest_file
          row.log_rev = file.rev

      if request.roottype == 'svn':
        row.rev_href = request.get_url(view_func=view_log,
                                       where=where_prefix + file.name,
                                       pathtype=vclib.DIR,
                                       params={'rev': str(file.rev)})
      
    elif file.kind == vclib.FILE:
      num_files = num_files + 1
      if (request.roottype == 'cvs' and 
          ((file.rev is None and not file.log_error and not file.verboten) or 
           (file.rev is not None and file.dead and hideattic and view_tag))):
        continue
      num_displayed = num_displayed + 1

      if request.roottype == 'cvs': 
        file_where = where_prefix + (file.in_attic and 'Attic/' or '') \
                     + file.name
      else:
        row.size = file.size
        file_where = where_prefix + file.name

      ### for Subversion, we should first try to get this from the properties
      mime_type, encoding = mimetypes.guess_type(file.name)
      if not mime_type:
        mime_type = 'text/plain'
      row.mime_type = mime_type
      
      row.href = request.get_url(view_func=view_log,
                                 where=file_where,
                                 pathtype=vclib.FILE,
                                 params={'rev': str(file.rev)})

      row.rev_href = request.get_url(view_func=view_auto,
                                     where=file_where,
                                     pathtype=vclib.FILE,
                                     params={'rev': str(file.rev)})

      if cfg.options.use_cvsgraph and request.roottype == 'cvs':
         row.graph_href = request.get_url(view_func=view_cvsgraph,
                                          where=file_where,
                                          pathtype=vclib.FILE,
                                          params={})

    rows.append(row)

  # prepare the data that will be passed to the template
  data = common_template_data(request)
  data.update({
    'rows' : rows,
    'sortby' : sortby,
    'sortdir' : sortdir,
    'tarball_href' : None,
    'search_re' : search_re and htmlify(search_re) or None,
    'dir_pagestart' : None,
    'sortby_file_href' :   request.get_url(params={'sortby': 'file',
                                                   'sortdir': None}),
    'sortby_rev_href' :    request.get_url(params={'sortby': 'rev',
                                                   'sortdir': None}),
    'sortby_date_href' :   request.get_url(params={'sortby': 'date',
                                                   'sortdir': None}),
    'sortby_author_href' : request.get_url(params={'sortby': 'author',
                                                   'sortdir': None}),
    'sortby_log_href' :    request.get_url(params={'sortby': 'log',
                                                   'sortdir': None}),
    'num_files' :  num_files,
    'files_shown' : num_displayed,
    'no_match' : ezt.boolean(num_files and not num_displayed),
    'unreadable' : ezt.boolean(unreadable),

    ### in the future, it might be nice to break this path up into
    ### a list of elements, allowing the template to display it in
    ### a variety of schemes.
    'nav_path' : clickable_path(request, 0, 0),
  })

  # clicking on sort column reverses sort order
  if sortdir == 'down':
    revsortdir = None # 'up'
  else:
    revsortdir = 'down'
  if sortby in ['file', 'rev', 'date', 'log', 'author']:
    data['sortby_%s_href' % sortby] = request.get_url(params={'sortdir':
                                                              revsortdir})

  # set cvs-specific fields
  if request.roottype == 'cvs':
    plain_tags = options['cvs_tags']
    plain_tags.sort(icmp)
    plain_tags.reverse()

    branch_tags = options['cvs_branches']
    branch_tags.sort(icmp)
    branch_tags.reverse()

    has_tags = view_tag or branch_tags or plain_tags

    data.update({
      'view_tag' : view_tag,    
      'attic_showing' : ezt.boolean(not hideattic),
      'show_attic_href' : request.get_url(params={'hideattic': 0}),
      'hide_attic_href' : request.get_url(params={'hideattic': 1}),
      'has_tags' : ezt.boolean(has_tags),
      ### one day, if EZT has "or" capability, we can lose this
      'selection_form' : ezt.boolean(has_tags or cfg.options.use_re_search),
      'branch_tags': branch_tags,
      'plain_tags': plain_tags,
    })
  else:
    data.update({
      'view_tag' : None,
      'has_tags' : None,
      'selection_form' : None,
    })

  # should we show the query link?
  if is_query_supported(request):
    params = {}
    if options.has_key('cvs_dir_tag'):
      params['branch'] = options['cvs_dir_tag']
    data['queryform_href'] = request.get_url(view_func=view_queryform,
                                             params=params)
  else:
    data['queryform_href'] = None

  if cfg.options.use_pagesize:
    url, params = request.get_link(params={'dir_pagestart': None})
    data['dir_paging_action'] = urllib.quote(url, _URL_SAFE_CHARS)
    data['dir_paging_hidden_values'] = prepare_hidden_values(params)

  if cfg.options.allow_tar:
    data['tarball_href'] = request.get_url(view_func=download_tarball, 
                                           params={})
  if request.roottype == 'svn':
    data['tree_rev'] = vclib.svn.created_rev(request.repos, where)
    data['tree_rev_href'] = request.get_url(view_func=view_revision,
                                            params={'rev': data['tree_rev']})
    if request.query_dict.has_key('rev'):
      data['jump_rev'] = request.query_dict['rev']
    else:
      data['jump_rev'] = str(request.repos.rev)

    url, params = request.get_link(params={'rev': None})
    data['jump_rev_action'] = urllib.quote(url, _URL_SAFE_CHARS)
    data['jump_rev_hidden_values'] = prepare_hidden_values(params)

  if data['selection_form']:
    url, params = request.get_link(params={'only_with_tag': None, 
                                           'search': None})
    data['search_tag_action'] = urllib.quote(url, _URL_SAFE_CHARS)
    data['search_tag_hidden_values'] = prepare_hidden_values(params)

  if cfg.options.use_pagesize:
    data['dir_pagestart'] = int(request.query_dict.get('dir_pagestart',0))
    data['rows'] = paging(data, 'rows', data['dir_pagestart'], 'name')

  request.server.header()
  generate_page(request, cfg.templates.directory, data)

def paging(data, key, pagestart, local_name):
  # Implement paging
  # Create the picklist
  picklist = data['picklist'] = []
  for i in range(0, len(data[key]), cfg.options.use_pagesize):
    pick = _item(start=None, end=None, count=None)
    pick.start = getattr(data[key][i], local_name)
    pick.count = i
    pick.page = (i / cfg.options.use_pagesize) + 1
    try:
      pick.end = getattr(data[key][i+cfg.options.use_pagesize-1], local_name)
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
  pageend = pagestart + cfg.options.use_pagesize
  # Slice
  return data[key][pagestart:pageend]

def logsort_date_cmp(rev1, rev2):
  # sort on date; secondary on revision number
  return -cmp(rev1.date, rev2.date) or -cmp(rev1.number, rev2.number)

def logsort_rev_cmp(rev1, rev2):
  # sort highest revision first
  return -cmp(rev1.number, rev2.number)

def view_log(request):
  diff_format = request.query_dict.get('diff_format', cfg.options.diff_format)
  logsort = request.query_dict.get('logsort', cfg.options.log_sort)
  view_tag = request.query_dict.get('only_with_tag')
  hide_attic = int(request.query_dict.get('hideattic',cfg.options.hide_attic))
  pathtype = request.pathtype

  mime_type = None
  if pathtype is vclib.FILE:
    mime_type = request.mime_type
  elif request.roottype == 'cvs':
    raise debug.ViewcvsException('Unsupported feature: log view on CVS '
                                 'directory', '400 Bad Request')

  options = {}
  options['svn_show_all_dir_logs'] = 0 ### someday make this optional?
  options['svn_cross_copies'] = cfg.options.cross_copies
    
  if request.roottype == 'cvs':
    up_where = get_up_path(request, request.where, hide_attic)
    filename = os.path.basename(request.where)
    rev = view_tag
  else:
    up_where, filename = os.path.split(request.where)
    rev = None

  show_revs = request.repos.filelog(request.path_parts, rev, options)
  if logsort == 'date':
    show_revs.sort(logsort_date_cmp)
  elif logsort == 'rev':
    show_revs.sort(logsort_rev_cmp)
  else:
    # no sorting
    pass

  entries = [ ]
  name_printed = { }
  cvs = request.roottype == 'cvs'
  for rev in show_revs:
    entry = _item()
    entry.rev = rev.string
    entry.state = (cvs and rev.dead and 'dead')
    entry.author = rev.author
    entry.changed = rev.changed
    entry.date_str = make_time_string(rev.date)
    entry.ago = None
    if rev.date is not None:
      entry.ago = html_time(request, rev.date, 1)
    entry.html_log = htmlify(rev.log or "")
    entry.size = rev.size
    entry.branch_point = None
    entry.next_main = None

    entry.view_href = None
    entry.download_href = None
    entry.download_text_href = None
    if pathtype is vclib.FILE:
      entry.view_href = request.get_url(view_func=view_markup,
                                        params={'rev': rev.string})
      entry.download_href = request.get_url(view_func=view_checkout,
                                            params={'rev': rev.string})
      if mime_type != 'text/plain':
        entry.download_text_href = \
            request.get_url(view_func=view_checkout,
                            params={'content-type': 'text/plain',
                                    'rev': rev.string})
    else:
      entry.view_href = request.get_url(view_func=view_directory,
                                        params={'rev': entry.rev})

        
    if request.roottype == 'cvs':
      entry.annotate_href = request.get_url(view_func=view_annotate, 
                                            params={'annotate': rev.string})

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

      # if it's on a branch (and not a vendor branch), then diff against the
      # next revision of the higher branch (e.g. change is committed and
      # brought over to -stable)
      if rev.parent and rev.parent.next and not entry.vendor_branch:
        if not rev.next:
          # this is the highest version on the branch; a lower one
          # shouldn't have a diff against the "next main branch"
          entry.next_main = rev.parent.next.string

    elif request.roottype == 'svn':
      entry.revision_href = request.get_url(view_func=view_revision,
                                            params={'rev': rev.string})
      if rev.copy_path:
        entry.copy_href = request.get_url(view_func=view_log,
                                          where=rev.copy_path,
                                          pathtype=vclib.FILE,
                                          params={'rev': rev.copy_rev})

      entry.prev = rev.prev and rev.prev.string
      entry.prev_path = rev.prev and rev.prev.filename
      entry.branches = entry.tags = entry.branch_points = [ ]
      entry.tag_names = entry.branch_names = [ ]
      entry.vendor_branch = None

      entry.copy_path = rev.copy_path
      entry.copy_rev = rev.copy_rev
      entry.filename = rev.filename

    # the template could do all these comparisons itself, but let's help
    # it out.
    r1 = request.query_dict.get('r1')
    if r1 and r1 != entry.rev and r1 != entry.prev \
           and r1 != entry.branch_point and r1 != entry.next_main:
      entry.to_selected = 'yes'
    else:
      entry.to_selected = None

    entries.append(entry)

  data = common_template_data(request)
  data.update({
    'nav_path' : clickable_path(request, 1, 0),
    'branch' : None,
    'mime_type' : mime_type,
    'rev_selected' : request.query_dict.get('r1'), 
    'path_selected' : request.query_dict.get('p1'), 
    'diff_format' : diff_format,
    'logsort' : logsort,
    'human_readable' : ezt.boolean(diff_format in ('h', 'l')),
    'log_pagestart' : None,
    'graph_href' : None,    
    'entries': entries,
  })

  if pathtype is vclib.FILE:
    data['viewable'] = ezt.boolean(request.default_viewable)
    data['is_text'] = ezt.boolean(is_text(mime_type))

  url, params = request.get_link(view_func=view_diff, 
                                 params={'r1': None, 'r2': None, 
                                         'diff_format': None})
  params = compat.urlencode(params)
  data['diff_url'] = urllib.quote(url, _URL_SAFE_CHARS)
  data['diff_params'] = params and '&' + params

  if cfg.options.use_pagesize:
    url, params = request.get_link(params={'log_pagestart': None})
    data['log_paging_action'] = urllib.quote(url, _URL_SAFE_CHARS)
    data['log_paging_hidden_values'] = prepare_hidden_values(params)

  url, params = request.get_link(params={'r1': None, 'r2': None, 'tr1': None,
                                         'tr2': None, 'diff_format': None})
  data['diff_select_action'] = urllib.quote(url, _URL_SAFE_CHARS)
  data['diff_select_hidden_values'] = prepare_hidden_values(params)

  url, params = request.get_link(params={'logsort': None})
  data['logsort_action'] = urllib.quote(url, _URL_SAFE_CHARS)
  data['logsort_hidden_values'] = prepare_hidden_values(params)

  data.update({
    'back_url' : request.get_url(view_func=view_directory, pathtype=vclib.DIR,
                                 where=up_where, params={}),
    'filename' : filename,
    'view_tag' : view_tag,
  })

  if request.roottype == 'cvs' and cfg.options.use_cvsgraph:
    data['graph_href'] = request.get_url(view_func=view_cvsgraph, params={})

  taginfo = options.get('cvs_tags', {})
  main = taginfo.get('MAIN')

  if main:
    # Default branch may have multiple names so we list them
    branches = []
    for branch in main.aliases:
      # Don't list MAIN unless there are no other names
      if branch is not main or len(main.aliases) == 1:
        branches.append(branch.name)

    ### this formatting should be moved into the ezt template
    data['branch'] = string.join(branches, ', ')

    data['view_href'] = request.get_url(view_func=view_markup, params={})
    data['download_href'] = request.get_url(view_func=view_checkout, params={})
    if request.mime_type != 'text/plain':
      data['download_text_href'] = \
        request.get_url(view_func=view_checkout,
                        params={'content-type': 'text/plain'})
    else:
      data['download_text_href'] = None

  tagitems = taginfo.items()
  tagitems.sort()
  tagitems.reverse()

  data['tags'] = tags = [ ]
  for tag, rev in tagitems:
    if rev.co_rev:
      tags.append(_item(rev=rev.co_rev.string, name=tag))

  data['tr1'] = request.query_dict.get('r1') or show_revs[-1].string
  data['tr2'] = request.query_dict.get('r2') or show_revs[0].string

  branch_names = []
  for tag in taginfo.values():
    if tag.is_branch:
      branch_names.append(tag.name)
  branch_names.sort()
  branch_names.reverse()
  data['branch_names'] = branch_names

  if branch_names:
    url, params = request.get_link(params={'only_with_tag': None})
    data['branch_select_action'] = urllib.quote(url, _URL_SAFE_CHARS)
    data['branch_select_hidden_values'] = prepare_hidden_values(params)

  if cfg.options.use_pagesize:
    data['log_pagestart'] = int(request.query_dict.get('log_pagestart',0))
    data['entries'] = paging(data, 'entries', data['log_pagestart'], 'rev')

  request.server.header()
  generate_page(request, cfg.templates.log, data)

def view_checkout(request):
  rev = request.query_dict.get('rev')
  fp, revision = request.repos.openfile(request.path_parts, rev)

  # The revision number acts as a strong validator.
  if check_freshness(request, None, revision):
    fp.close()
    return

  mime_type = request.query_dict.get('content-type', request.mime_type)
  request.server.header(mime_type)
  copy_stream(fp)

def view_annotate(request):
  if not cfg.options.allow_annotate:
    raise "annotate no allows"

  rev = request.query_dict.get('annotate')
  data = nav_header_data(request, rev)

  ### be nice to hook this into the template...
  import blame
  data['lines'] = blame.BlameSource(request.repos.rootpath,
                                    request.where + ',v', rev,
                                    compat.urlencode(request.get_options()))

  request.server.header()
  generate_page(request, cfg.templates.annotate, data)

def view_cvsgraph_image(request):
  "output the image rendered by cvsgraph"
  # this function is derived from cgi/cvsgraphmkimg.cgi

  if not cfg.options.use_cvsgraph:
    raise "cvsgraph no allows"
  
  request.server.header('image/png')
  fp = popen.popen(os.path.normpath(os.path.join(cfg.options.cvsgraph_path,
                                                 'cvsgraph')),
                   ("-c", cfg.options.cvsgraph_conf,
                    "-r", request.repos.rootpath,
                    request.where + ',v'), 'rb', 0)
  copy_stream(fp)
  fp.close()

def view_cvsgraph(request):
  "output a page containing an image rendered by cvsgraph"
  # this function is derived from cgi/cvsgraphwrapper.cgi

  if not cfg.options.use_cvsgraph:
    raise "cvsgraph no allows"

  where = request.where

  pathname, filename = os.path.split(where)
  if pathname[-6:] == '/Attic':
    pathname = pathname[:-6]

  data = nav_header_data(request, None)

  # Required only if cvsgraph needs to find it's supporting libraries.
  # Uncomment and set accordingly if required.
  #os.environ['LD_LIBRARY_PATH'] = '/usr/lib:/usr/local/lib'

  query = compat.urlencode(request.get_options({}))
  amp_query = query and '&' + query
  qmark_query = query and '?' + query

  imagesrc = request.get_url(view_func=view_cvsgraph_image)

  # Create an image map
  fp = popen.popen(os.path.join(cfg.options.cvsgraph_path, 'cvsgraph'),
                   ("-i",
                    "-c", cfg.options.cvsgraph_conf,
                    "-r", request.repos.rootpath,
                    "-6", amp_query,
                    "-7", qmark_query,
                    request.where + ',v'), 'rb', 0)

  data.update({
    'imagemap' : fp,
    'imagesrc' : imagesrc,
    })

  request.server.header()
  generate_page(request, cfg.templates.graph, data)

def search_files(repos, path_parts, files, search_re):
  """ Search files in a directory for a regular expression.

  Does a check-out of each file in the directory.  Only checks for
  the first match.  
  """

  # Pass in search regular expression. We check out
  # each file and look for the regular expression. We then return the data
  # for all files that match the regex.

  # Compile to make sure we do this as fast as possible.
  searchstr = re.compile(search_re)

  # Will become list of files that have at least one match.
  # new_file_list also includes directories.
  new_file_list = [ ]

  # Loop on every file (and directory)
  for file in files:
    # Is this a directory?  If so, append name to new_file_list
    # and move to next file.
    if file.kind != vclib.FILE:
      new_file_list.append(file)
      continue

    # Only files at this point
    
    # figure out where we are and its mime type
    mime_type, encoding = mimetypes.guess_type(file.name)
    if not mime_type:
      mime_type = 'text/plain'

    # Shouldn't search binary files, or should we?
    # Should allow all text mime types to pass.
    if mime_type[:4] != 'text':
      continue

    # Only text files at this point

    # process_checkout will checkout the head version out of the repository
    # Assign contents of checked out file to fp.
    fp = repos.openfile(path_parts + [file.name])[0]

    # Read in each line, use re.search to search line.
    # If successful, add file to new_file_list and break.
    while 1:
      line = fp.readline()
      if not line:
        break
      if searchstr.search(line):
        new_file_list.append(file)
        # close down the pipe (and wait for the child to terminate)
        fp.close()
        break

  return new_file_list


def view_doc(request):
  """Serve ViewCVS help pages locally.

  Using this avoids the need for modifying the setup of the web server.
  """
  help_page = request.where
  if CONF_PATHNAME:
    doc_directory = os.path.join(g_install_dir, "doc")
  else:
    # aid testing from CVS working copy:
    doc_directory = os.path.join(g_install_dir, "website")
  filename = os.path.join(doc_directory, help_page)

  try:
    info = os.stat(filename)
  except OSError, v:
    raise debug.ViewcvsException('Help file "%s" not available\n(%s)'
                                 % (help_page, str(v)), '404 Not Found')
  content_length = str(info[stat.ST_SIZE])
  last_modified = info[stat.ST_MTIME]
  # content_length + mtime makes a pretty good etag
  etag = "%s-%s" % (content_length, last_modified)
  if check_freshness(request, last_modified, etag):
    return
  request.server.addheader('Content-Length', content_length)
  
  try:
    fp = open(filename, "rb")
  except IOError, v:
    raise debug.ViewcvsException('Help file "%s" not available\n(%s)'
                                 % (help_page, str(v)), '404 Not Found')
  if help_page[-3:] == 'png':
    request.server.header('image/png')
  elif help_page[-3:] == 'jpg':
    request.server.header('image/jpeg')
  elif help_page[-3:] == 'gif':
    request.server.header('image/gif')
  elif help_page[-3:] == 'css':
    request.server.header('text/css')
  else: # assume HTML:
    request.server.header()
  copy_stream(fp)
  fp.close()

def rcsdiff_date_reformat(date_str):
  try:
    date = compat.cvs_strptime(date_str)
  except ValueError:
    return date_str
  return make_time_string(compat.timegm(date))

_re_extract_rev = re.compile(r'^[-+]+ [^\t]+\t([^\t]+)\t((\d+\.)*\d+)$')
_re_extract_info = re.compile(r'@@ \-([0-9]+).*\+([0-9]+).*@@(.*)')
def human_readable_diff(fp, rev1, rev2):
  log_rev1 = log_rev2 = None
  date1 = date2 = ''
  rcsdiff_eflag = 0
  while 1:
    line = fp.readline()
    if not line:
      break

    # Use regex matching to extract the data and to ensure that we are
    # extracting it from a properly formatted line. There are rcsdiff
    # programs out there that don't supply the correct format; we'll be
    # flexible in case we run into one of those.
    if line[:4] == '--- ':
      match = _re_extract_rev.match(line)
      if match:
        date1 = match.group(1)
        log_rev1 = match.group(2)
    elif line[:4] == '+++ ':
      match = _re_extract_rev.match(line)
      if match:
        date2 = match.group(1)
        log_rev2 = match.group(2)
      break

    # Didn't want to put this here, but had to.  The DiffSource class
    # picks up fp after this loop has processed the header.  Previously
    # error messages and the 'Binary rev ? and ? differ' where thrown out
    # and DiffSource then showed no differences.
    # Need to process the entire header before DiffSource is used.
    if line[:3] == 'Bin':
      rcsdiff_eflag = _RCSDIFF_IS_BINARY
      break

    if (string.find(line, 'not found') != -1 or 
        string.find(line, 'illegal option') != -1):
      rcsdiff_eflag = _RCSDIFF_ERROR
      break

  if (log_rev1 and log_rev1 != rev1) or (log_rev2 and log_rev2 != rev2):
    ### it would be nice to have an error.ezt for things like this
    print '<strong>ERROR:</strong> rcsdiff did not return the correct'
    print 'version number in its output.'
    print '(got "%s" / "%s", expected "%s" / "%s")' % \
          (log_rev1, log_rev2, rev1, rev2)
    print '<p>Aborting operation.'
    sys.exit(0)

  # Process any special lines in the header, or continue to
  # get the differences from DiffSource.
  if rcsdiff_eflag == _RCSDIFF_IS_BINARY:
    changes = [ (_item(type='binary-diff')) ]
  elif rcsdiff_eflag == _RCSDIFF_ERROR:
    changes = [ (_item(type='error')) ]
  else:
    changes = DiffSource(fp)

  return date1, date2, changes

def spaced_html_text(text):
  text = string.expandtabs(string.rstrip(text))
  hr_breakable = cfg.options.hr_breakable
  
  # in the code below, "\x01" will be our stand-in for "&". We don't want
  # to insert "&" because it would get escaped by htmlify().  Similarly,
  # we use "\x02" as a stand-in for "<br>"

  if hr_breakable > 1 and len(text) > hr_breakable:
    text = re.sub('(' + ('.' * hr_breakable) + ')', '\\1\x02', text)
  if hr_breakable:
    # make every other space "breakable"
    text = string.replace(text, '  ', ' \x01nbsp;')
  else:
    text = string.replace(text, ' ', '\x01nbsp;')
  text = htmlify(text)
  text = string.replace(text, '\x01', '&')
  text = string.replace(text, '\x02', '<font color=red>\</font><br>')
  return text

class DiffSource:
  def __init__(self, fp):
    self.fp = fp
    self.save_line = None

    # keep track of where we are during an iteration
    self.idx = -1
    self.last = None

    # these will be set once we start reading
    self.left = None
    self.right = None
    self.state = 'no-changes'
    self.left_col = [ ]
    self.right_col = [ ]

  def __getitem__(self, idx):
    if idx == self.idx:
      return self.last
    if idx != self.idx + 1:
      raise DiffSequencingError()

    # keep calling _get_row until it gives us something. sometimes, it
    # doesn't return a row immediately because it is accumulating changes
    # when it is out of data, _get_row will raise IndexError
    while 1:
      item = self._get_row()
      if item:
        self.idx = idx
        self.last = item
        return item

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
      return _item(type='header', line1=match.group(1), line2=match.group(2),
                   extra=match.group(3))

    if line[0] == '\\':
      # \ No newline at end of file

      # move into the flushing state. note: it doesn't matter if we really
      # have data to flush or not; that will be figured out later
      self.state = 'flush-' + self.state
      return None

    diff_code = line[0]
    output = spaced_html_text(line[1:])

    if diff_code == '+':
      if self.state == 'dump':
        return _item(type='add', right=output)

      self.state = 'pre-change-add'
      self.right_col.append(output)
      return None

    if diff_code == '-':
      self.state = 'pre-change-remove'
      self.left_col.append(output)
      return None

    if self.left_col or self.right_col:
      # save the line for processing again later
      self.save_line = line

      # move into the flushing state
      self.state = 'flush-' + self.state
      return None

    return _item(type='context', left=output, right=output)

  def _flush_row(self):
    if not self.left_col and not self.right_col:
      # nothing more to flush
      return None

    if self.state == 'flush-pre-change-remove':
      return _item(type='remove', left=self.left_col.pop(0))

    # state == flush-pre-change-add
    item = _item(type='change', have_left=None, have_right=None)
    if self.left_col:
      item.have_left = 'yes'
      item.left = self.left_col.pop(0)
    if self.right_col:
      item.have_right = 'yes'
      item.right = self.right_col.pop(0)
    return item

class DiffSequencingError(Exception):
  pass

def raw_diff(rootpath, fp, sym1, sym2, unified, parseheader, htmlize):
  date1 = date2 = None
  header_lines = []

  # If we're parsing headers, then parse and tweak the diff headers,
  # collecting them in an array until we've read and handled them all.
  # Then, use a MarkupPipeWrapper to wrap the collected headers and
  # the filepointer.
  if parseheader:
    if unified:
      f1 = '--- ' + rootpath
      f2 = '+++ ' + rootpath
    else:
      f1 = '*** ' + rootpath
      f2 = '--- ' + rootpath

    parsing = 1
    while parsing:
      line = fp.readline()
      if not line:
        break

      if line[:len(f1)] == f1:
        match = _re_extract_rev.match(line)
        if match:
          date1 = match.group(1)
        line = string.replace(line, rootpath + '/', '')
        if sym1:
          line = line[:-1] + ' %s\n' % sym1
      elif line[:len(f2)] == f2:
        line = string.replace(line, rootpath + '/', '')
        match = _re_extract_rev.match(line)
        if match:
          date2 = match.group(1)
          log_rev2 = match.group(2)
        if sym2:
          line = line[:-1] + ' %s\n' % sym2
        parsing = 0
      header_lines.append(line)

  return date1, date2, MarkupPipeWrapper(fp, string.join(header_lines, ''),
                                         None, htmlize)


def view_diff(request):
  query_dict = request.query_dict

  rev1 = r1 = query_dict['r1']
  rev2 = r2 = query_dict['r2']
  p1 = query_dict.get('p1', request.where)
  p2 = query_dict.get('p2', request.where)
  sym1 = sym2 = None

  if r1 == 'text':
    rev1 = query_dict.get('tr1', None)
    if not rev1:
      raise debug.ViewcvsException('Missing revision from the diff '
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
      raise debug.ViewcvsException('Missing revision from the diff '
                                   'form text field', '400 Bad Request')
    sym2 = ''
  else:
    idx = string.find(r2, ':')
    if idx == -1:
      rev2 = r2
    else:
      rev2 = r2[:idx]
      sym2 = r2[idx+1:]

  try:
    if revcmp(rev1, rev2) > 0:
      rev1, rev2 = rev2, rev1
      sym1, sym2 = sym2, sym1
      p1, p2 = p2, p1
  except ValueError:
    raise debug.ViewcvsException('Invalid revision(s) passed to diff',
                                 '400 Bad Request')

  # since templates are in use and subversion allows changes to the dates,
  # we can't provide a strong etag
  if check_freshness(request, None, '%s-%s' % (rev1, rev2), weak=1):
    return

  human_readable = 0
  unified = 0
  parseheaders = 0
  args = [ ]

  ### Note: these options only really work out where rcsdiff (used by
  ### CVS) and regular diff (used by SVN) overlap.  If for some reason
  ### our use of the options for these starts to deviate too much,
  ### this code may a re-org to just do different things for different
  ### VC types.
  
  format = query_dict.get('diff_format', cfg.options.diff_format)
  makepatch = int(request.query_dict.get('makepatch', 0))

  # If 'makepatch' was specified with a colored diff, just fall back
  # to straight unidiff (though, we could throw an error).
  if makepatch and (format == 'h' or format == 'l'):
    format = 'u'
  
  if format == 'c':
    args.append('-c')
    parseheaders = 1
  elif format == 's':
    args.append('--side-by-side')
    args.append('--width=164')
  elif format == 'l':
    args.append('--unified=15')
    human_readable = 1
    unified = 1
  elif format == 'h':
    args.append('-u')
    human_readable = 1
    unified = 1
  elif format == 'u':
    args.append('-u')
    unified = 1
    parseheaders = 1
  else:
    raise debug.ViewcvsException('Diff format %s not understood'
                                 % format, '400 Bad Request')

  if human_readable:
    if cfg.options.hr_funout:
      args.append('-p')
    if cfg.options.hr_ignore_white:
      args.append('-w')
    if cfg.options.hr_ignore_keyword_subst and request.roottype == 'cvs':
      # -kk isn't a regular diff option.  it exists only for rcsdiff
      # (as in "-ksubst") ,so 'svn' roottypes can't use it.
      args.append('-kk')

  file1 = None
  file2 = None
  if request.roottype == 'cvs':
    args[len(args):] = ['-r' + rev1, '-r' + rev2, request.full_name]
    fp = request.repos.rcs_popen('rcsdiff', args, 'rt')
  else:
    try:
      date1 = vclib.svn.date_from_rev(request.repos, int(rev1))
      date2 = vclib.svn.date_from_rev(request.repos, int(rev2))
    except vclib.InvalidRevision:
      raise debug.ViewcvsException('Invalid revision(s) passed to diff',
                                   '400 Bad Request')

    if date1 is not None:
      date1 = time.strftime('%Y/%m/%d %H:%M:%S', time.gmtime(date1))
    else:
      date1 = ''
    if date2 is not None:
      date2 = time.strftime('%Y/%m/%d %H:%M:%S', time.gmtime(date2))
    else:
      date2 = ''
    args.append("-L")
    args.append(p1 + "\t" + date1 + "\t" + rev1)
    args.append("-L")
    args.append(p2 + "\t" + date2 + "\t" + rev2)

    # Need to keep a reference to the FileDiff object around long
    # enough to use.  It destroys its underlying temporary files when
    # the class is destroyed.
    diffobj = vclib.svn.do_diff(request.repos, p1, int(rev1),
                                p2, int(rev2), args)
    
    try:
      fp = diffobj.get_pipe()
    except vclib.svn.core.SubversionException, e:
      if e.apr_err == vclib.svn.core.SVN_ERR_FS_NOT_FOUND:
        raise debug.ViewcvsException('Invalid path(s) or revision(s) passed '
                                     'to diff', '400 Bad Request')
      raise e

  # If we're bypassing the templates, just print the diff and get outta here.
  if makepatch:
    request.server.header('text/plain')
    date1, date2, raw_diff_fp = raw_diff(request.repos.rootpath, fp,
                                         sym1, sym2, unified, parseheaders, 0)
    copy_stream(raw_diff_fp)
    raw_diff_fp.close()
    return

  request.server.header()
  data = nav_header_data(request, rev2)
  data.update({
    'rev1' : rev1,
    'rev2' : rev2,
    'tag1' : sym1,
    'tag2' : sym2,
    'diff_format' : request.query_dict.get('diff_format',
                                           cfg.options.diff_format),
    })

  params = request.query_dict.copy()
  params['diff_format'] = None
    
  url, params = request.get_link(params=params)
  data['diff_format_action'] = urllib.quote(url, _URL_SAFE_CHARS)
  data['diff_format_hidden_values'] = prepare_hidden_values(params)

  date1 = date2 = raw_diff_fp = changes = None
  if human_readable:
    date1, date2, changes = human_readable_diff(fp, rev1, rev2)
  else:
    date1, date2, raw_diff_fp = raw_diff(request.repos.rootpath, fp,
                                         sym1, sym2, unified, parseheaders, 1)
  data.update({
    'date1' : date1 and rcsdiff_date_reformat(date1),
    'date2' : date2 and rcsdiff_date_reformat(date2),
    'raw_diff' : raw_diff_fp,
    'changes' : changes,
    })

  generate_page(request, cfg.templates.diff, data)


def generate_tarball_header(out, name, size=0, mode=None, mtime=0,
                            uid=0, gid=0, typefrag=None, linkname='',
                            uname='viewcvs', gname='viewcvs',
                            devmajor=1, devminor=0, prefix=None,
                            magic='ustar', version='', chksum=None):
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

def generate_tarball(out, request, tar_top, rep_top,
                     reldir, options, stack=[]):
  cvs = request.roottype == 'cvs'
  if cvs and (rep_top == '' and 0 < len(reldir) and
              reldir[0] == 'CVSROOT' and cfg.options.hide_cvsroot):
    return

  if (rep_top == '' and cfg.is_forbidden(reldir[0])):
    return

  rep_path = rep_top + reldir
  tar_dir = string.join(tar_top + reldir, '/') + '/'

  entries = request.repos.listdir(rep_path, options)

  subdirs = [ ]
  for file in entries:
    if not file.verboten and file.kind == vclib.DIR:
      subdirs.append(file.name)

  stack.append(tar_dir)

  request.repos.dirlogs(rep_path, entries, options)

  entries.sort(lambda a, b: cmp(a.name, b.name))

  # Subdirectory datestamps will be the youngest of the datestamps of
  # version items (files for CVS, files or dirs for Subversion) in
  # that subdirectory.
  latest_date = 0
  for file in entries:
    # Skip dead or busted CVS files, and CVS subdirs.
    if (cvs and (file.kind != vclib.FILE or (file.rev is None or file.dead))):
      continue
    if file.date > latest_date:
      latest_date = file.date
  
  for file in entries:
    if (file.kind != vclib.FILE or
        (cvs and (file.rev is None or file.dead))):
      continue

    for dir in stack:
      generate_tarball_header(out, dir, mtime=latest_date)
    del stack[0:]

    if cvs:
      info = os.stat(file.path)
      mode = (info[stat.ST_MODE] & 0555) | 0200
      rev = file.rev
    else:
      mode = 0644
      rev = None

    fp = request.repos.openfile(rep_top + reldir + [file.name], rev)[0]

    contents = fp.read()
    fp.close()

    generate_tarball_header(out, tar_dir + file.name,
                            len(contents), mode, file.date)
    out.write(contents)
    out.write('\0' * (511 - ((len(contents) + 511) % 512)))

  subdirs.sort()
  for subdir in subdirs:
    if not cvs or subdir != 'Attic':
      generate_tarball(out, request, tar_top, rep_top,
		       reldir + [subdir], options, stack)

  if len(stack):
    del stack[-1:]

def download_tarball(request):
  if not cfg.options.allow_tar:
    raise "tarball no allows"

  # If there is a repository directory name we can use for the
  # top-most directory, use it.  Otherwise, use the configured root
  # name.
  rep_top = request.path_parts
  if len(rep_top):
    tar_top = rep_top[-1]
  else:
    tar_top = request.rootname

  options = {}
  if request.roottype == 'cvs':
    tag = request.query_dict.get('only_with_tag')
    options['cvs_list_attic'] = tag and 1 or 0
    options['cvs_dir_tag'] = tag

  ### look for GZIP binary

  request.server.header('application/octet-stream')
  sys.stdout.flush()
  fp = popen.pipe_cmds([('gzip', '-c', '-n')])

  generate_tarball(fp, request, [tar_top], rep_top, [], options)

  fp.write('\0' * 1024)
  fp.close()

def view_revision(request):
  data = common_template_data(request)

  if request.roottype == "cvs":
    raise ViewcvsException("Revision view not supported for CVS repositories "
                           "at this time.", "400 Bad Request")
  else:
    view_revision_svn(request, data)

def view_revision_svn(request, data):
  query_dict = request.query_dict
  date, author, msg, changes = vclib.svn.get_revision_info(request.repos)
  date_str = make_time_string(date)
  rev = request.repos.rev
  
  # add the hrefs, types, and prev info
  for change in changes:
    change.view_href = change.diff_href = change.type = None
    change.prev_path = change.prev_rev = None
    if change.pathtype is vclib.FILE:
      change.type = 'file'
      change.view_href = request.get_url(view_func=view_markup,
                                         where=change.filename, 
                                         pathtype=change.pathtype,
                                         params={'rev' : str(rev)})
      if change.action == "copied" or change.action == "modified":
        change.prev_path = change.base_path
        change.prev_rev = change.base_rev
        change.diff_href = request.get_url(view_func=view_diff,
                                           where=change.filename, 
                                           pathtype=change.pathtype,
                                           params={'rev' : str(rev)})
    elif change.pathtype is vclib.DIR:
      change.type = 'dir'
      change.view_href = request.get_url(view_func=view_directory,
                                         where=change.filename, 
                                         pathtype=change.pathtype,
                                         params={'rev' : str(rev)})

  prev_rev_href = next_rev_href = None
  if rev > 0:
    prev_rev_href = request.get_url(view_func=view_revision,
                                    where=None,
                                    pathtype=None,
                                    params={'rev': str(rev - 1)})
  if rev < request.repos.youngest:
    next_rev_href = request.get_url(view_func=view_revision,
                                    where=None,
                                    pathtype=None,
                                    params={'rev': str(rev + 1)})
  if msg:
    msg = htmlify(msg)
  data.update({
    'rev' : str(rev),
    'author' : author,
    'date_str' : date_str,
    'log' : msg,
    'ago' : None,
    'changes' : changes,
    'jump_rev' : str(rev),
    'prev_href' : prev_rev_href,
    'next_href' : next_rev_href,
  })

  if date is not None:
    data['ago'] = html_time(request, date, 1)

  url, params = request.get_link(view_func=view_revision,
                                 where=None,
                                 pathtype=None,
                                 params={'rev': None})
  data['jump_rev_action'] = urllib.quote(url, _URL_SAFE_CHARS)
  data['jump_rev_hidden_values'] = prepare_hidden_values(params)

  request.server.header()
  generate_page(request, cfg.templates.revision, data)

def is_query_supported(request):
  """Returns true if querying is supported for the given path."""
  return cfg.cvsdb.enabled \
         and request.pathtype == vclib.DIR \
         and request.roottype in ['cvs', 'svn']

def view_queryform(request):
  if not is_query_supported(request):
    raise debug.ViewCVSException('Can not query project root "%s" at "%s".'
                                 % (request.rootname, request.where),
                                 '403 Forbidden')

  data = common_template_data(request)

  url, params = request.get_link(view_func=view_query, params={})
  data['query_action'] = urllib.quote(url, _URL_SAFE_CHARS)
  data['query_hidden_values'] = prepare_hidden_values(params)

  # default values ...
  data['branch'] = request.query_dict.get('branch', '')
  data['branch_match'] = request.query_dict.get('branch_match', 'exact')
  data['dir'] = request.query_dict.get('dir', '')
  data['file'] = request.query_dict.get('file', '')
  data['file_match'] = request.query_dict.get('file_match', 'exact')
  data['who'] = request.query_dict.get('who', '')
  data['who_match'] = request.query_dict.get('who_match', 'exact')
  data['querysort'] = request.query_dict.get('querysort', 'date')
  data['date'] = request.query_dict.get('date', 'hours')
  data['hours'] = request.query_dict.get('hours', '2')
  data['mindate'] = request.query_dict.get('mindate', '')
  data['maxdate'] = request.query_dict.get('maxdate', '')

  data['nav_path'] = clickable_path(request, 0, 0)

  request.server.header()
  generate_page(request, cfg.templates.query_form, data)

def parse_date(s):
  '''Parse a date string from the query form.'''
  match = re.match(r'^(\d\d\d\d)-(\d\d)-(\d\d)(?:\ +(\d\d):(\d\d)(?::(\d\d))?)?$', s)
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
    return time.mktime(tm) - time.timezone
  else:
    return None

def english_query(request):
  '''Generate a sentance describing the query.'''
  ret = [ 'Checkins ' ]
  dir = request.query_dict.get('dir', '')
  if dir:
    ret.append('to ')
    if ',' in dir:
      ret.append('subdirectories')
    else:
      ret.append('subdirectory')
    ret.append(' <i>%s</i> ' % htmlify(dir))
  file = request.query_dict.get('file', '')
  if file:
    if len(ret) != 1: ret.append('and ')
    ret.append('to file <i>%s</i> ' % htmlify(file))
  who = request.query_dict.get('who', '')
  branch = request.query_dict.get('branch', '')
  if branch:
    ret.append('on branch <i>%s</i> ' % htmlify(branch))
  else:
    ret.append('on all branches ')
  if who:
    ret.append('by <i>%s</i> ' % htmlify(who))
  date = request.query_dict.get('date', 'hours')
  if date == 'hours':
    ret.append('in the last %s hours' % htmlify(request.query_dict.get('hours', '2')))
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
      mindate = make_time_string(parse_date(mindate))
      ret.append('%s <i>%s</i> ' % (w1, mindate))
    if maxdate:
      maxdate = make_time_string(parse_date(maxdate))
      ret.append('%s <i>%s</i> ' % (w2, maxdate))
  return string.join(ret, '')

def prev_rev(rev):
  '''Returns a string representing the previous revision of the argument.'''
  r = string.split(rev, '.')
  # decrement final revision component
  r[-1] = str(int(r[-1]) - 1)
  # prune if we pass the beginning of the branch
  if len(r) > 2 and r[-1] == '0':
    r = r[:-2]
  return string.join(r, '.')

def build_commit(request, desc, files):
  commit = _item(num_files=len(files), files=[])
  commit.desc = htmlify(desc)
  for f in files:
    commit_time = f.GetTime()
    if commit_time:
      commit_time = make_time_string(commit_time)
    else:
      commit_time = '&nbsp;'
    filename = os.path.join(f.GetDirectory(), f.GetFile())
    filename = string.replace(filename, os.sep, '/')
    dirname = string.replace(f.GetDirectory(), os.sep, '/')

    params = { 'rev': f.GetRevision() }
    if f.GetBranch(): params['only_with_tag'] = f.GetBranch()
    dir_href = request.get_url(view_func=view_directory,
                               where=dirname, pathtype=vclib.DIR,
                               params=params)
    log_href = request.get_url(view_func=view_log,
                               where=filename, pathtype=vclib.FILE,
                               params=params)
    rev_href = request.get_url(view_func=view_auto,
                               where=filename, pathtype=vclib.FILE,
                               params={'rev': f.GetRevision() })
    diff_href = request.get_url(view_func=view_diff,
                                where=filename, pathtype=vclib.FILE,
                                params={'r1': prev_rev(f.GetRevision()),
                                        'r2': f.GetRevision(),
                                        'diff_format': None})

    commit.files.append(_item(date=commit_time,
                              dir=htmlify(f.GetDirectory()),
                              file=htmlify(f.GetFile()),
                              author=htmlify(f.GetAuthor()),
                              rev=f.GetRevision(),
                              branch=f.GetBranch(),
                              plus=int(f.GetPlusCount()),
                              minus=int(f.GetMinusCount()),
                              type=f.GetTypeString(),
                              dir_href=dir_href,
                              log_href=log_href,
                              rev_href=rev_href,
                              diff_href=diff_href))
  return commit

def query_backout(request, commits):
  request.server.header('text/plain')
  if commits:
    print '# This page can be saved as a shell script and executed.'
    print '# It should be run at the top of your work area.  It will update'
    print '# your working copy to back out the changes selected by the'
    print '# query.'
    print
  else:
    print '# No changes were selected by the query.'
    print '# There is nothing to back out.'
    return
  for commit in commits:
    for fileinfo in commit.files:
      if request.roottype == 'cvs':
        print 'cvs update -j %s -j %s %s/%s' \
              % (fileinfo.rev, prev_rev(fileinfo.rev),
                 fileinfo.dir, fileinfo.file)
      elif request.roottype == 'svn':
        print 'svn merge -r %s:%s %s/%s' \
              % (fileinfo.rev, prev_rev(fileinfo.rev),
                 fileinfo.dir, fileinfo.file)

def view_query(request):
  if not is_query_supported(request):
    raise debug.ViewCVSException('Can not query project root "%s" at "%s".'
                                 % (request.rootname, request.where),
                                 '403 Forbidden')

  # get form data
  branch = request.query_dict.get('branch', '')
  branch_match = request.query_dict.get('branch_match', 'exact')
  dir = request.query_dict.get('dir', '')
  file = request.query_dict.get('file', '')
  file_match = request.query_dict.get('file_match', 'exact')
  who = request.query_dict.get('who', '')
  who_match = request.query_dict.get('who_match', 'exact')
  querysort = request.query_dict.get('querysort', 'date')
  date = request.query_dict.get('date', 'hours')
  hours = request.query_dict.get('hours', '2')
  mindate = request.query_dict.get('mindate', '')
  maxdate = request.query_dict.get('maxdate', '')
  format = request.query_dict.get('format')

  match_types = { 'exact':1, 'like':1, 'glob':1, 'regex':1, 'notregex':1 }
  sort_types = { 'date':1, 'author':1, 'file':1 }
  date_types = { 'hours':1, 'day':1, 'week':1, 'month':1,
                 'all':1, 'explicit':1 }

  # parse various fields, validating or converting them
  if not match_types.has_key(branch_match): branch_match = 'exact'
  if not match_types.has_key(file_match): file_match = 'exact'
  if not match_types.has_key(who_match): who_match = 'exact'
  if not sort_types.has_key(querysort): querysort = 'date'
  if not date_types.has_key(date): date = 'hours'
  mindate = parse_date(mindate)
  maxdate = parse_date(maxdate)

  import cvsdb
  cvsdb.cfg = cfg

  # create the database query from the form data
  query = cvsdb.CreateCheckinQuery()
  query.SetRepository(request.rootpath)
  # treat "HEAD" specially ...
  if branch_match == 'exact' and branch == 'HEAD':
    query.SetBranch('')
  elif branch:
    query.SetBranch(branch, branch_match)
  if dir:
    for subdir in string.split(dir, ','):
      path = string.join(request.path_parts + [ string.strip(subdir) ], '/')
      query.SetDirectory('%s%%' % path, 'like')
  else:
    if request.path_parts: # if we are in a subdirectory ...
      query.SetDirectory('%s%%' % request.where, 'like')
  if file:
    query.SetFile(file, file_match)
  if who:
    query.SetAuthor(who, who_match)
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

  # run the query
  db = cvsdb.ConnectDatabaseReadOnly()
  db.RunQuery(query)

  sql = htmlify(db.CreateSQLQueryString(query))

  # gather commits
  commits = []
  plus_count = 0
  minus_count = 0
  mod_time = -1
  if query.commit_list:
    files = []
    current_desc = query.commit_list[0].GetDescription()
    for commit in query.commit_list:
      # base modification time on the newest commit ...
      if commit.GetTime() > mod_time: mod_time = commit.GetTime()
      # form plus/minus totals
      plus_count = plus_count + int(commit.GetPlusCount())
      minus_count = minus_count + int(commit.GetMinusCount())
      # group commits with the same commit message ...
      desc = commit.GetDescription()
      if current_desc == desc:
        files.append(commit)
        continue
      commits.append(build_commit(request, current_desc, files))

      files = [ commit ]
      current_desc = desc
    commits.append(build_commit(request, current_desc, files))

  # only show the branch column if we are querying all branches
  # or doing a non-exact branch match on a CVS repository.
  show_branch = ezt.boolean(request.roottype == 'cvs' and
                            (branch == '' or branch_match != 'exact'))

  # a link to modify query
  queryform_href = request.get_url(view_func=view_queryform,
                                   params=request.query_dict.copy())
  # backout link
  params = request.query_dict.copy()
  params['format'] = 'backout'
  backout_href = request.get_url(params=params)

  # if we got any results, use the newest commit as the modification time
  if mod_time >= 0:
    if check_freshness(request, mod_time):
      return

  if format == 'backout':
    query_backout(request, commits)
    return

  data = common_template_data(request)
  data.update({
    'nav_path' : clickable_path(request, 0, 0),
    'sql': sql,
    'english_query': english_query(request),
    'queryform_href': queryform_href,
    'backout_href': backout_href,
    'plus_count': plus_count,
    'minus_count': minus_count,
    'show_branch': show_branch,
    'querysort': querysort,
    'commits': commits,
    })

  request.server.header()
  generate_page(request, cfg.templates.query_results, data)

_views = {
  'annotate': view_annotate,
  'auto':     view_auto,
  'co':       view_checkout,
  'diff':     view_diff,
  'dir':      view_directory,
  'graph':    view_cvsgraph,
  'graphimg': view_cvsgraph_image,
  'log':      view_log,
  'markup':   view_markup,
  'query':    view_query,
  'queryform':view_queryform,
  'rev':      view_revision,
  'tar':      download_tarball,
}

_view_codes = {}
for code, view in _views.items():
  _view_codes[view] = code

def list_roots(cfg):
  allroots = { }
  for root in cfg.general.cvs_roots.keys():
    allroots[root] = [cfg.general.cvs_roots[root], 'cvs']
  for root in cfg.general.svn_roots.keys():
    allroots[root] = [cfg.general.svn_roots[root], 'svn']
  return allroots
  
def handle_config():
  debug.t_start('load-config')
  global cfg
  if cfg is None:
    cfg = config.Config()
    cfg.set_defaults()

    # load in configuration information from the config file
    pathname = CONF_PATHNAME or os.path.join(g_install_dir, 'viewcvs.conf')
    if sapi.server:
      cfg.load_config(pathname, sapi.server.getenv('HTTP_HOST'))
    else:
      cfg.load_config(pathname, None)

    # special handling for root_parents.  Each item in root_parents is
    # a "directory : repo_type" string.  For each item in
    # root_parents, we get a list of the subdirectories.
    #
    # If repo_type is "cvs", and the subdirectory contains a child
    # "CVSROOT/config", then it is added to cvs_roots.
    #
    # If repo_type is "svn", and the subdirectory contains a child
    # "format", then it is added to svn_roots.
    for pp in cfg.general.root_parents:
      pos = string.rfind(pp, ':')
      if pos < 0:
        raise debug.ViewcvsException(
          "The path '%s' in 'root_parents' does not include a "
          "repository type." % pp)
      pp, repo_type = map(string.strip, (pp[:pos], pp[pos+1:]))

      try:
        subpaths = os.listdir(pp)
      except OSError:
        raise debug.ViewcvsException(
          "The path '%s' in 'root_parents' does not refer to "
          "a valid directory." % pp)

      for subpath in subpaths:
        if os.path.exists(os.path.join(pp, subpath)):
          if repo_type == 'cvs' and \
               os.path.exists(os.path.join(pp, subpath, "CVSROOT", "config")):
            cfg.general.cvs_roots[subpath] = os.path.join(pp, subpath)
          elif repo_type == 'svn' and \
               os.path.exists(os.path.join(pp, subpath, "format")):
            cfg.general.svn_roots[subpath] = os.path.join(pp, subpath)

  debug.t_end('load-config')


def view_error(server):
  exc_dict = debug.GetExceptionData()
  status = exc_dict['status']
  handled = 0
  
  # use the configured error template if possible
  try:
    if cfg:
      server.header(status=status)
      generate_page(None, cfg.templates.error, exc_dict)
      handled = 1
  except:
    # get new exception data, more important than the first
    exc_dict = debug.GetExceptionData()

  # but fallback to the old exception printer if no configuration is
  # available, or if something went wrong
  if not handled:
    debug.PrintException(server, exc_dict)

def main(server):
  try:
    debug.t_start('main')
    try:
      # handle the configuration stuff
      handle_config()
    
      # build a Request object, which contains info about the HTTP request
      request = Request(server)    
      request.run_viewcvs()
    except SystemExit, e:
      return
    except:
      view_error(server)

  finally:
    debug.t_end('main')
    debug.dump()
    debug.DumpChildren(server)


class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
