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
import stat
import struct
import types

# these modules come from our library (the stub has set up the path)
import compat
import config
import popen
import ezt
import accept
import vclib
from vclib import bincvs

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

    # if this is a forbidden path, stop now
    if path_parts and cfg.is_forbidden(path_parts[0]):
      raise debug.ViewCVSException('Access to "%s" is forbidden.'
                                   % path_parts[0], '403 Forbidden')

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
                                         
    # Create the repository object
    if cfg.general.cvs_roots.has_key(self.rootname):
      self.rootpath = cfg.general.cvs_roots[self.rootname]
      try:
        self.repos = bincvs.BinCVSRepository(self.rootname, self.rootpath, 
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
        self.repos.cross_copies = cfg.options.cross_copies
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
        if self.query_dict.has_key('rev'):
          if self.query_dict.get('content-type', None) in (viewcvs_mime_type,
                                                           alt_mime_type):
            self.view_func = view_markup
          else:
            self.view_func = view_checkout
        elif self.query_dict.has_key('annotate'):
          self.view_func = view_annotate
        elif self.query_dict.has_key('r1') and self.query_dict.has_key('r2'):
          self.view_func = view_diff
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
    if where:
      url = url + '/' + where

    # add suffix for tarball
    if view_func is download_tarball:
      if not where: url = url + '/root'
      url = url + '.tar.gz'

    # add trailing slash for a directory      
    elif pathtype == vclib.DIR:
      url = url + '/'

    # no need to explicitly specify log view for a file
    if view_func is view_log and pathtype == vclib.FILE:
      view_func = None

    # no need to explicitly specify directory view for a directory
    if view_func is view_directory and pathtype == vclib.DIR:
      view_func = None

    # no need to explicitly specify annotate view when
    # there's an annotate parameter
    if view_func is view_annotate and params.has_key('annotate'):
      view_func = None

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
_re_validate_revnum = re.compile('^[-_.a-zA-Z0-9:]*$')

# it appears that RFC 2045 also says these chars are legal: !#$%&'*+^{|}~`
# but woah... I'll just leave them out for now
_re_validate_mimetype = re.compile('^[-_.a-zA-Z0-9/]+$')

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

def html_footer(request):
  data = common_template_data(request)

  # generate the footer
  generate_page(request, cfg.templates.footer, data)

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
  return request.get_url(view_func=view_directory, where=where, 
                      pathtype=vclib.DIR, params={})


def prep_tags(request, tags):
  url, params = request.get_link(params={'only_with_tag': None})
  params = compat.urlencode(params)
  if params:
    url = urllib.quote(url, _URL_SAFE_CHARS) + '?' + params + '&only_with_tag='
  else:
    url = urllib.quote(url, _URL_SAFE_CHARS) + '?only_with_tag='

  links = [ ]
  for tag in tags:
    links.append(_item(name=tag, href=url+tag))
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
  }
  return data

def nav_header_data(request, rev):
  path, filename = os.path.split(request.where)
  if request.roottype == 'cvs' and path[-6:] == '/Attic':
    path = path[:-6]

  data = common_template_data(request)
  data.update({
    'nav_path' : clickable_path(request, 1, 0),
    'path' : path,
    'filename' : filename,
    'file_url' : request.get_url(view_func=view_log, params={}),
    'rev' : rev
  })
  return data

def copy_stream(fp):
  while 1:
    chunk = fp.read(CHUNK_SIZE)
    if not chunk:
      break
    sys.stdout.write(chunk)

def markup_stream_default(fp):
  print '<pre>'
  while 1:
    ### technically, the htmlify() could fail if something falls across
    ### the chunk boundary. TFB.
    chunk = fp.read(CHUNK_SIZE)
    if not chunk:
      break
    sys.stdout.write(htmlify(chunk))
  print '</pre>'

def markup_stream_python(fp):
  ### convert this code to use the recipe at:
  ###     http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52298
  ### note that the cookbook states all the code is licensed according to
  ### the Python license.
  try:
    # see if Marc-Andre Lemburg's py2html stuff is around
    # http://starship.python.net/crew/lemburg/SoftwareDescriptions.html#py2html.py
    ### maybe restrict the import to *only* this directory?
    sys.path.insert(0, cfg.options.py2html_path)
    import py2html
    import PyFontify
  except ImportError:
    # fall back to the default streamer
    markup_stream_default(fp)
  else:
    ### it doesn't escape stuff quite right, nor does it munge URLs and
    ### mailtos as well as we do.
    html = cgi.escape(fp.read())
    pp = py2html.PrettyPrint(PyFontify.fontify, "rawhtml", "color")
    html = pp.fontify(html)
    html = re.sub(_re_rewrite_url, r'<a href="\1">\1</a>', html)
    html = re.sub(_re_rewrite_email, r'<a href="mailto:\1">\1</a>', html)
    sys.stdout.write(html)

def markup_stream_php(fp):
  if not cfg.options.use_php:
    return markup_stream_default(fp)

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

  php = popen.pipe_cmds([[cfg.options.php_exe_path, "-q", "-s", "-n"]])

  while 1:
    chunk = fp.read(CHUNK_SIZE)
    if not chunk:
      if fp.eof() is None:
        time.sleep(1)
        continue
      break
    php.write(chunk)

  php.close()

def markup_stream_enscript(lang, fp):
  sys.stdout.flush()
  # I've tried to pass option '-C' to enscript to generate line numbers
  # Unfortunately this option doesn'nt work with HTML output in enscript
  # version 1.6.2.
  enscript = popen.pipe_cmds([(os.path.normpath(os.path.join(cfg.options.enscript_path,'enscript')),
                               '--color', '--language=html', 
                               '--pretty-print=' + lang, '-o',
                               '-', '-'),
                              ('sed', '-n', '/^<PRE>$/,/<\\/PRE>$/p')])

  try:
    while 1:
      chunk = fp.read(CHUNK_SIZE)
      if not chunk:
        if fp.eof() is None:
          time.sleep(1)
          continue
        break
      enscript.write(chunk)
  except IOError:
    print "<h3>Failure during use of an external program:</h3>"
    print "The command line was:"
    print "<pre>"
    print os.path.normpath(os.path.join(cfg.options.enscript_path,'enscript')
                          ) + " --color --language=html --pretty-print="+lang+" -o - -"
    print "</pre>"
    print "Please look at the error log of your webserver for more info."
    raise

  enscript.close()
  if sys.platform != "win32":
    os.wait()

markup_streamers = {
#  '.py' : markup_stream_python,
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
  # classic setting:
  # '.pas' : 'pascal',
  # most people using pascal today are using the Delphi system originally 
  # brought to us as Turbo-Pascal during the eighties of the last century:
  '.pas' : 'delphi',
  # ---
  '.patch' : 'diffu',
  # For Oracle sql packages.  The '.pkg' extension might be used for other
  # file types, adjust here if necessary.
  '.pkg' : 'sql', 
  '.pl' : 'perl',
  '.pm' : 'perl',
  '.pp' : 'pascal',
  '.ps' : 'postscript',
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

  ### use enscript or py2html?
  '.py' : 'python',
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

  data = nav_header_data(request, revision)
  data.update({
    'nav_file' : clickable_path(request, 1, 0),
    'href' : request.get_url(view_func=view_checkout, params={}),
    'text_href' : request.get_url(view_func=view_checkout, 
                                  params={'content-type': 'text/plain'}),
    'mime_type' : request.mime_type,
    'log' : None,
    'tag' : None,
    })

  if cfg.options.show_log_in_markup:
    if request.roottype == 'cvs':
      show_revs, rev_map, rev_order, taginfo, rev2tag, \
                 cur_branch, branch_points, branch_names = read_log(full_name)
      entry = rev_map[revision]
  
      idx = string.rfind(revision, '.')
      branch = revision[:idx]
  
      entry.date_str = make_time_string(entry.date)
  
      data.update({
        'roottype' : 'cvs',
        'date_str' : entry.date_str,
        'ago' : html_time(request, entry.date, 1),
        'author' : entry.author,
        'branches' : None,
        'tags' : None,
        'branch_points' : None,
        'changed' : entry.changed,
        'log' : htmlify(entry.log),
        'size' : None,
        'state' : entry.state,
        'vendor_branch' : ezt.boolean(_re_is_vendor_branch.match(revision)),
        })
  
      if rev2tag.has_key(branch):
        data['branches'] = string.join(rev2tag[branch], ', ')
      if rev2tag.has_key(revision):
        data['tags'] = string.join(rev2tag[revision], ', ')
      if branch_points.has_key(revision):
        data['branch_points'] = string.join(branch_points[revision], ', ')
  
      prev_rev = string.split(revision, '.')
      while 1:
        if prev_rev[-1] == '0':     # .0 can be caused by 'commit -r X.Y.Z.0'
          prev_rev = prev_rev[:-2]  # X.Y.Z.0 becomes X.Y.Z
        else:
          prev_rev[-1] = str(int(prev_rev[-1]) - 1)
        prev = string.join(prev_rev, '.')
        if rev_map.has_key(prev) or prev == '':
          break
      data['prev'] = prev
    elif request.roottype == 'svn':
      alltags, logs = vclib.svn.fetch_log(request.repos, where)
      this_rev = int(revision)
      entry = logs[this_rev]

      data.update({
        'roottype' : 'svn',
        'date_str' : make_time_string(entry.date),
        'ago' : html_time(request, entry.date, 1),
        'author' : entry.author,
        'branches' : None,
        'tags' : None,
        'branch_points' : None,
        'changed' : entry.changed,
        'log' : htmlify(entry.log),
        'state' : entry.state,
        'size' : entry.size,
        'vendor_branch' : None,
        })

      revs = logs.keys()
      revs.sort()
      rev_idx = revs.index(this_rev)
      if rev_idx > 0:
        data['prev'] = str(revs[rev_idx - 1])
      else:
        data['prev'] = None
  else:
    data['tag'] = query_dict.get('only_with_tag')

  request.server.header()
  generate_page(request, cfg.templates.markup, data)

  if is_viewable_image(request.mime_type):
    url = request.get_url(view_func=view_checkout, params={})
    print '<img src="%s"><br>' % url
    while fp.read(8192):
      pass
  else:
    basename, ext = os.path.splitext(data['filename'])
    streamer = markup_streamers.get(ext)
    if streamer:
      streamer(fp)
    elif not cfg.options.use_enscript:
      markup_stream_default(fp)
    else:
      lang = enscript_extensions.get(ext)
      if not lang:
        lang = enscript_filenames.get(basename)
      if lang and lang not in cfg.options.disable_enscript_lang:
        markup_stream_enscript(lang, fp)
      else:
        markup_stream_default(fp)
  status = fp.close()
  if status:
    raise 'pipe error status: %d' % status
  html_footer(request)

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
    info1 = file1.rev is not None and file1.rev != bincvs._FILE_HAD_ERROR
    info2 = file2.rev is not None and file2.rev != bincvs._FILE_HAD_ERROR
    if info1 and info2:
      # both are files, sort according to sortby
      if sortby == 'rev':
        return revcmp(file1.rev, file2.rev)
      elif sortby == 'date':
        return cmp(file2.date, file1.date)        # latest date is first
      elif sortby == 'log':
        return cmp(file1.log, file2.log)
      elif sortby == 'author':
        return cmp(file1.author, file2.author)
    elif info1:
      return -1
    elif info2:
      return 1

    # sort by file name
    return cmp(file1.name, file2.name)

  file_data.sort(file_sort_cmp)

  if sortdir == "down":
    file_data.reverse()

def view_directory(request):
  # if we have a directory and the request didn't end in "/", then redirect
  # so that it does.
  if request.server.getenv('PATH_INFO', '')[-1:] != '/':
    request.server.redirect(request.get_url())

  # List current directory
  if request.roottype == 'cvs':
    view_tag = request.query_dict.get('only_with_tag')
    hideattic = int(request.query_dict.get('hideattic', 
                                           cfg.options.hide_attic))
    file_data = request.repos.listdir(request.path_parts,
                                      not hideattic or view_tag)
    dir_params = {}
  else:
    file_data = request.repos.listdir(request.path_parts)
    dir_params = {'rev': request.query_dict.get('rev')}    

  # Filter file list if a regex is specified
  search_re = request.query_dict.get('search', '')
  if cfg.options.use_re_search and search_re:
    file_data = search_files(request.repos, request.path_parts,
                             file_data, search_re)

  # Retrieve log messages, authors, revision numbers, timestamps                     
  if request.roottype == 'cvs':
    get_dirs = cfg.options.show_subdir_lastmod and cfg.options.show_logs
    bincvs.get_logs(request.repos, request.path_parts,
                    file_data, view_tag, get_dirs)
  else:
    vclib.svn.get_logs(request.repos, request.where, file_data)

  # sort with directories first, and using the "sortby" criteria
  sortby = request.query_dict.get('sortby', cfg.options.sort_by) or 'file'
  sortdir = request.query_dict.get('sortdir', 'up')
  sort_file_data(file_data, sortdir, sortby)

  # loop through entries creating rows and changing these values
  rows = [ ]
  num_files = 0
  num_displayed = 0
  unreadable = 0
  have_logs = 0

  # current directory name and name plus trailing slash
  where = request.where
  where_prefix = where and where + '/'

  ### display a row for ".." ?
  for file in file_data:
    row = _item(href=None, graph_href=None,
                author=None, log=None, log_file=None, log_rev=None,
                show_log=None, state=None)

    if file.rev == bincvs._FILE_HAD_ERROR:
      row.cvs = 'error'
      unreadable = 1
    elif file.rev is None:
      row.cvs = 'none'
    else:
      row.cvs = 'data'
      row.rev = file.rev
      row.author = file.author or "&nbsp;"
      if request.roottype == 'cvs':
        row.state = file.state
      else:
        row.state = ''
      row.time = html_time(request, file.date)
      if cfg.options.show_logs and file.log:
        row.show_log = 'yes'
        row.log = format_log(file.log)
        have_logs = 1

    row.anchor = file.name
    row.name = file.name

    row.type = (file.kind == vclib.FILE and 'file') or \
               (file.kind == vclib.DIR and 'dir')

    if file.verboten or not row.type:
      row.type = 'unreadable'
      unreadable = 1

    if file.kind == vclib.DIR:
      if (request.roottype == 'cvs' and
          ((file.name == 'CVS') or # CVS directory is for fileattr
           (not hideattic and file.name == 'Attic') or
           (where == '' and (cfg.is_forbidden(file.name) or
                             (file.name == 'CVSROOT' and 
                              cfg.options.hide_cvsroot))))):
        continue

      row.href = request.get_url(view_func=view_directory,
                                 where=where_prefix+file.name,
                                 pathtype=vclib.DIR,
                                 params=dir_params)

      if request.roottype == 'cvs' and row.cvs == 'data':
        if cfg.options.use_cvsgraph:
          row.graph_href = '&nbsp;' 
        if cfg.options.show_logs:
          row.log_file = file.newest_file
          row.log_rev = file.rev

      ### needed because the subversion vclib retrieves logs for directories
      ### but the template code can't display them properly
      if request.roottype == 'svn':
        row.cvs = 'none'

    elif file.kind == vclib.FILE:
      num_files = num_files + 1
      if (request.roottype == 'cvs' and 
          ((file.rev is None and not file.verboten) or 
           (hideattic and view_tag and file.state == 'dead'))):
        continue
      num_displayed = num_displayed + 1

      if request.roottype == 'cvs': 
        file_where = where_prefix + (file.in_attic and 'Attic/' or '') \
                     + file.name
      else:
        file_where = where_prefix + file.name

      row.href = request.get_url(view_func=view_log,
                                 where=file_where,
                                 pathtype=vclib.FILE,
                                 params={})

      row.rev_href = request.get_url(view_func=view_auto,
                                     where=file_where,
                                     pathtype=vclib.FILE,
                                     params={'rev': str(file.rev)})

      if cfg.options.use_cvsgraph:
         row.graph_href = request.get_url(view_func=view_cvsgraph,
                                          where=file_where,
                                          pathtype=vclib.FILE,
                                          params={})

    rows.append(row)

  # prepare the data that will be passed to the template
  data = common_template_data(request)
  data.update({
    'roottype' : request.roottype,
    'where' : request.where,
    'current_root' : request.repos.name,
    'rows' : rows,
    'sortby' : sortby,
    'sortdir' : sortdir,
    'tarball_href' : None,
    'search_re' : search_re and htmlify(search_re) or None,
    'dir_pagestart' : None,
    'sortby_file_href' :   request.get_url(params={'sortby': 'file'}),
    'sortby_rev_href' :    request.get_url(params={'sortby': 'rev'}),
    'sortby_date_href' :   request.get_url(params={'sortby': 'date'}),
    'sortby_author_href' : request.get_url(params={'sortby': 'author'}),
    'sortby_log_href' :    request.get_url(params={'sortby': 'log'}),
    'sortdir_down_href' :  request.get_url(params={'sortdir': 'down'}),
    'sortdir_up_href' :    request.get_url(params={'sortdir': 'up'}),
    'num_files' :  num_files,
    'files_shown' : num_displayed,
    'no_match' : ezt.boolean(num_files and not num_displayed),
    'unreadable' : ezt.boolean(unreadable),

    # have_logs will be 0 if we only have dirs and !show_subdir_lastmod.
    # in that case, we don't need the extra columns
    'have_logs' : ezt.boolean(have_logs),

    ### in the future, it might be nice to break this path up into
    ### a list of elements, allowing the template to display it in
    ### a variety of schemes.
    'nav_path' : clickable_path(request, 0, 0),
  })

  # set cvs-specific fields
  if request.roottype == 'cvs':
    has_tags = (view_tag or request.repos.branch_tags 
                or request.repos.plain_tags)
    data.update({
      'view_tag' : view_tag,    
      'attic_showing' : ezt.boolean(not hideattic),
      'show_attic_href' : request.get_url(params={'hideattic': 0}),
      'hide_attic_href' : request.get_url(params={'hideattic': 1}),
      'has_tags' : ezt.boolean(has_tags),
      ### one day, if EZT has "or" capability, we can lose this
      'selection_form' : ezt.boolean(has_tags or cfg.options.use_re_search),
      'branch_tags': request.repos.branch_tags,
      'plain_tags': request.repos.plain_tags,
    })
  else:
    data.update({
      'view_tag' : None,
      'has_tags' : None,
      'selection_form' : None,
    })

  if not request.where:
    url, params = request.get_link(params={'root': None})
    data['change_root_action'] = urllib.quote(url, _URL_SAFE_CHARS)
    data['change_root_hidden_values'] = prepare_hidden_values(params)

    # add in the roots for the selection
    allroots = list_roots(cfg)
    if len(allroots) < 2:
      roots = [ ]
    else:
      roots = allroots.keys()
      roots.sort(lambda n1, n2: cmp(string.lower(n1), string.lower(n2)))
    data['roots'] = roots

  if cfg.options.use_pagesize:
    url, params = request.get_link(params={'dir_pagestart': None})
    data['dir_paging_action'] = urllib.quote(url, _URL_SAFE_CHARS)
    data['dir_paging_hidden_values'] = prepare_hidden_values(params)

  if cfg.options.allow_tar:
    data['tarball_href'] = request.get_url(view_func=download_tarball, 
                                           params={})
  if request.roottype == 'svn':
    data['tree_rev'] = str(request.repos.rev)
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
    data['dir_pagestart'] = int(query_dict.get('dir_pagestart',0))
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
  return -cmp(rev1.date, rev2.date) or -revcmp(rev1.rev, rev2.rev)

def logsort_rev_cmp(rev1, rev2):
  # sort highest revision first
  return -revcmp(rev1.rev, rev2.rev)

def find_first_rev(taginfo, revs):
  "Find first revision that matches a normal tag or is on a branch tag"
  for rev in revs:
    if taginfo.matches_rev(rev) or taginfo.holds_rev(rev):
      return rev
  return None

def read_log(full_name, which_rev=None, view_tag=None, logsort='cvs'):
  head, cur_branch, taginfo, revs = bincvs.fetch_log(cfg.general,
                                                     full_name, which_rev)

  rev_order = map(lambda entry: entry.rev, revs)
  rev_order.sort(revcmp)
  rev_order.reverse()

  # HEAD is an artificial tag which is simply the highest tag number on the
  # main branch, unless there is a branch tag in the RCS file in which case
  # it's the highest revision on that branch.  Find it by looking through
  # rev_order; it is the first commit listed on the appropriate branch.
  # This is not neccesary the same revision as marked as head in the RCS file.
  ### Why are we defining our own HEAD instead of just using the revision
  ### marked as head? What's wrong with: taginfo['HEAD'] = bincvs.TagInfo(head)
  taginfo['MAIN'] = bincvs.TagInfo(cur_branch)
  taginfo['HEAD'] = find_first_rev(taginfo['MAIN'], rev_order)

  # map revision numbers to tag names
  rev2tag = { }

  # names of symbols at each branch point
  branch_points = { }

  branch_names = [ ]

  # Now that we know all of the revision numbers, we can associate
  # absolute revision numbers with all of the symbolic names, and
  # pass them to the form so that the same association doesn't have
  # to be built then.

  items = taginfo.items()
  items.sort()
  items.reverse()
  for name, tag in items:
    if not isinstance(tag, bincvs.TagInfo):
      taginfo[name] = tag = bincvs.TagInfo(tag)

    number = tag.number()

    if tag.is_branch():    
      branch_names.append(name)

      if number == cur_branch:
        default_branch = name

      if not tag.is_trunk():
        rev = tag.branches_at()
        if branch_points.has_key(rev):
          branch_points[rev].append(name)
        else:
          branch_points[rev] = [ name ]

      # revision number you'd get if you checked out this branch
      tag.co_rev = find_first_rev(tag, rev_order)
    else:
      tag.co_rev = number

    if rev2tag.has_key(number):
      rev2tag[number].append(name)
    else:
      rev2tag[number] = [ name ]

  if view_tag:
    tag = taginfo.get(view_tag)
    if not tag:
      raise debug.ViewcvsException('Tag %s not defined.' % view_tag,
                                   '404 Tag Not Found')

    show_revs = [ ]
    for entry in revs:
      rev = entry.rev
      if tag.matches_rev(rev) or tag.holds_rev(rev):
        show_revs.append(entry)
  else:
    show_revs = revs

  if logsort == 'date':
    show_revs.sort(logsort_date_cmp)
  elif logsort == 'rev':
    show_revs.sort(logsort_rev_cmp)
  else:
    # no sorting
    pass

  # build a map of revision number to entry information
  rev_map = { }
  for entry in revs:
    rev_map[entry.rev] = entry

  ### some of this return stuff doesn't make a lot of sense...
  return show_revs, rev_map, rev_order, taginfo, rev2tag, \
         default_branch, branch_points, branch_names

_re_is_vendor_branch = re.compile(r'^1\.1\.1\.\d+$')

def augment_entry(entry, request, rev_map, rev2tag, branch_points,
                  rev_order, extended, name_printed):
  "Augment the entry with additional, computed data from the log output."

  query_dict = request.query_dict

  rev = entry.rev
  idx = string.rfind(rev, '.')
  branch = rev[:idx]

  entry.vendor_branch = ezt.boolean(_re_is_vendor_branch.match(rev))

  entry.date_str = make_time_string(entry.date)

  entry.ago = html_time(request, entry.date, 1)

  entry.branches = prep_tags(request, rev2tag.get(branch, [ ]))
  entry.tags = prep_tags(request, rev2tag.get(rev, [ ]))
  entry.branch_points = prep_tags(request, branch_points.get(rev, [ ]))

  prev_rev = string.split(rev, '.')
  while 1:
    if prev_rev[-1] == '0':     # .0 can be caused by 'commit -r X.Y.Z.0'
      prev_rev = prev_rev[:-2]  # X.Y.Z.0 becomes X.Y.Z
    else:
      prev_rev[-1] = str(int(prev_rev[-1]) - 1)
    prev = string.join(prev_rev, '.')
    if rev_map.has_key(prev) or prev == '':
      break
  entry.prev = prev

  ### maybe just overwrite entry.log?
  entry.html_log = htmlify(entry.log)

  if extended:
    entry.tag_names = rev2tag.get(rev, [ ])
    if rev2tag.has_key(branch) and not name_printed.has_key(branch):
      entry.branch_names = rev2tag.get(branch)
      name_printed[branch] = 1
    else:
      entry.branch_names = [ ]

    entry.href = request.get_url(view_func=view_checkout, params={'rev': rev})
    entry.view_href = request.get_url(view_func=view_markup, 
                                      params={'rev': rev})
    entry.text_href = request.get_url(view_func=view_checkout,
                                      params={'content-type': 'text/plain',
                                              'rev': rev})
    
    entry.annotate_href = request.get_url(view_func=view_annotate, 
                                          params={'annotate': rev})

    # figure out some target revisions for performing diffs
    entry.branch_point = None
    entry.next_main = None

    idx = string.rfind(branch, '.')
    if idx != -1:
      branch_point = branch[:idx]

      if not entry.vendor_branch \
         and branch_point != rev and branch_point != prev:
        entry.branch_point = branch_point

    # if it's on a branch (and not a vendor branch), then diff against the
    # next revision of the higher branch (e.g. change is committed and
    # brought over to -stable)
    if string.count(rev, '.') > 1 and not entry.vendor_branch:
      # locate this rev in the ordered list of revisions
      i = rev_order.index(rev)

      # create a rev that can be compared component-wise
      c_rev = string.split(rev, '.')

      while i:
        next = rev_order[i - 1]
        c_work = string.split(next, '.')
        if len(c_work) < len(c_rev):
          # found something not on the branch
          entry.next_main = next
          break

        # this is a higher version on the same branch; the lower one (rev)
        # shouldn't have a diff against the "next main branch"
        if c_work[:-1] == c_rev[:len(c_work) - 1]:
          break

        i = i - 1

    # the template could do all these comparisons itself, but let's help
    # it out.
    r1 = query_dict.get('r1')
    if r1 and r1 != rev and r1 != prev and r1 != entry.branch_point \
       and r1 != entry.next_main:
      entry.to_selected = 'yes'
    else:
      entry.to_selected = None

def view_log(request):
  diff_format = request.query_dict.get('diff_format', cfg.options.diff_format)
  logsort = request.query_dict.get('logsort', cfg.options.log_sort)
  
  data = common_template_data(request)
  data.update({
    'roottype' : request.roottype,
    'current_root' : request.repos.name,
    'where' : request.where,
    'nav_path' : clickable_path(request, 1, 0),
    'branch' : None,
    'mime_type' : request.mime_type,
    'rev_selected' : request.query_dict.get('r1'), 
    'path_selected' : request.query_dict.get('p1'), 
    'diff_format' : diff_format,
    'logsort' : logsort,
    'viewable' : ezt.boolean(request.default_viewable),
    'is_text'  : ezt.boolean(is_text(request.mime_type)),
    'human_readable' : ezt.boolean(diff_format in ('h', 'l')),
    'log_pagestart' : None,
    'graph_href' : None,    
  })

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

  if request.roottype == 'svn':
    view_log_svn(request, data, logsort)
  else:
    view_log_cvs(request, data, logsort)

def view_log_svn(request, data, logsort):
  query_dict = request.query_dict

  alltags, logs = vclib.svn.fetch_log(request.repos, request.where)
  up_where, filename = os.path.split(request.where)

  entries = []
  prev_rev = None
  prev_path = None
  show_revs = logs.keys()
  show_revs.sort()
  for rev in show_revs:
    entry = logs[rev]
    entry.prev = prev_rev
    entry.prev_path = prev_path
    entry.href = request.get_url(view_func=view_checkout, where=entry.filename,
                                 pathtype=vclib.FILE, params={'rev': rev})
    entry.view_href = request.get_url(view_func=view_markup, 
                                      where=entry.filename,
                                      pathtype=vclib.FILE,
                                      params={'rev': rev})
    entry.text_href = request.get_url(view_func=view_checkout,
                                      where=entry.filename,
                                      pathtype=vclib.FILE,
                                      params={'content-type': 'text/plain',
                                              'rev': rev})
    entry.revision_href = request.get_url(view_func=view_revision,
                                          where=None,
                                          pathtype=None,
                                          params={'rev': rev})

    if entry.copy_path:
      entry.copy_href = request.get_url(view_func=view_log, 
                                        where=entry.copy_path,
                                        pathtype=vclib.FILE, params={})

    entry.tags = [ ]
    entry.branches = [ ]
    entry.branch_point = None
    entry.branch_points = [ ]
    entry.next_main = None
    entry.to_selected = None
    entry.vendor_branch = None
    entry.ago = html_time(request, entry.date, 1)
    entry.date_str = make_time_string(entry.date)
    entry.tag_names = [ ]
    entry.branch_names = [ ]
    if not entry.log:
      entry.log = ""
    entry.html_log = htmlify(entry.log)

    # the template could do all these comparisons itself, but let's help
    # it out.
    r1 = query_dict.get('r1')
    if r1 and r1 != str(rev) and r1 != str(prev_rev):
      entry.to_selected = 'yes'
    else:
      entry.to_selected = None

    entries.append(entry)
    prev_rev = rev
    prev_path = entry.filename
  show_revs.reverse()
  entries.reverse()
  
  data.update({
    'back_url' : request.get_url(view_func=view_directory, pathtype=vclib.DIR,
                                 where=up_where, params={}),
    'filename' : filename,
    'view_tag' : None,
    'entries' : entries,
    'tags' : [ ],
    'branch_names' : [ ],
    })

  if len(show_revs):
    data['tr1'] = show_revs[-1]
    data['tr2'] = show_revs[0]
  else:
    data['tr1'] = None
    data['tr2'] = None

  if cfg.options.use_pagesize:
    data['log_pagestart'] = int(query_dict.get('log_pagestart',0))
    data['entries'] = paging(data, 'entries', data['log_pagestart'], 'rev')

  request.server.header()
  generate_page(request, cfg.templates.log, data)
  
def view_log_cvs(request, data, logsort):
  full_name = request.full_name
  where = request.where
  query_dict = request.query_dict

  view_tag = query_dict.get('only_with_tag')

  show_revs, rev_map, rev_order, taginfo, rev2tag, \
             cur_branch, branch_points, branch_names = \
             read_log(full_name, None, view_tag, logsort)

  up_where = get_up_path(request, where, int(query_dict.get('hideattic',
                                             cfg.options.hide_attic)))

  filename = os.path.basename(where)

  data.update({
    'back_url' : request.get_url(view_func=view_directory, pathtype=vclib.DIR,
                                 where=up_where, params={}),
    'filename' : filename,
    'view_tag' : view_tag,
    'entries' : show_revs,   ### rename the show_rev local to entries?
    
  })

  if cfg.options.use_cvsgraph:
    data['graph_href'] = request.get_url(view_func=view_cvsgraph, params={})

  if cur_branch:
    data['branch'] = cur_branch

    ### I don't like this URL construction stuff. the value
    ### for head_abs_href vs head_href is a bit bogus: why decide to
    ### include/exclude the mime type from the URL? should just always be
    ### the same, right?
    if request.default_viewable:
      data['head_href'] = request.get_url(view_func=view_markup, params={})
      data['head_abs_href'] = request.get_url(view_func=view_checkout, 
                                              params={})
    else:
      data['head_href'] = request.get_url(view_func=view_checkout, params={})

  name_printed = { }
  for entry in show_revs:
    # augment the entry with (extended=1) info.
    augment_entry(entry, request, rev_map, rev2tag, branch_points,
                  rev_order, 1, name_printed)

  tagitems = taginfo.items()
  tagitems.sort()
  tagitems.reverse()

  data['tags'] = tags = [ ]
  for tag, rev in tagitems:
    if rev.co_rev:
      tags.append(_item(rev=rev.co_rev, name=tag))
        
  if query_dict.has_key('r1'):
    diff_rev = query_dict['r1']
  else:
    diff_rev = show_revs[-1].rev
  data['tr1'] = diff_rev

  if query_dict.has_key('r2'):
    diff_rev = query_dict['r2']
  else:
    diff_rev = show_revs[0].rev
  data['tr2'] = diff_rev

  branch_names.sort()
  branch_names.reverse()
  data['branch_names'] = branch_names

  if branch_names:
    url, params = request.get_link(params={'only_with_tag': None})
    data['branch_select_action'] = urllib.quote(url, _URL_SAFE_CHARS)
    data['branch_select_hidden_values'] = prepare_hidden_values(params)

  if cfg.options.use_pagesize:
    data['log_pagestart'] = int(query_dict.get('log_pagestart',0))
    data['entries'] = paging(data, 'entries', data['log_pagestart'], 'rev')

  request.server.header()
  generate_page(request, cfg.templates.log, data)

def view_checkout(request):
  rev = request.query_dict.get('rev')
  fp = request.repos.openfile(request.path_parts, rev)[0]
  mime_type = request.query_dict.get('content-type', request.mime_type)
  request.server.header(mime_type)
  copy_stream(fp)

def view_annotate(request):
  if not cfg.options.allow_annotate:
    raise "annotate no allows"

  rev = request.query_dict.get('annotate')
  data = nav_header_data(request, rev)

  request.server.header()
  generate_page(request, cfg.templates.annotate, data)

  ### be nice to hook this into the template...
  import blame
  blame.make_html(request.repos.rootpath, request.where + ',v', rev,
                  compat.urlencode(request.get_options()))

  html_footer(request)


def view_cvsgraph_image(request):
  "output the image rendered by cvsgraph"
  # this function is derived from cgi/cvsgraphmkimg.cgi

  if not cfg.options.use_cvsgraph:
    raise "cvsgraph no allows"
  
  request.server.header('image/png')
  fp = popen.popen(os.path.normpath(os.path.join(cfg.options.cvsgraph_path,'cvsgraph')),
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
  try:
    fp = open(os.path.join(doc_directory, help_page), "rb")
  except IOError, v:
    raise debug.ViewcvsException('help file "%s" not available\n(%s)'
                                 % (help_page, str(v)), '404 Not Found')
  if help_page[-3:] == 'png':
    request.server.header('image/png')
  elif help_page[-3:] == 'jpg':
    request.server.header('image/jpeg')
  elif help_page[-3:] == 'gif':
    request.server.header('image/gif')
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
def human_readable_diff(request, fp, rev1, rev2, sym1, sym2):
  # do this now, in case we need to print an error
  request.server.header()

  query_dict = request.query_dict

  where = request.where

  data = nav_header_data(request, rev2)

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
    rcs_diff = [ (_item(type='binary-diff')) ]
  elif rcsdiff_eflag == _RCSDIFF_ERROR:
    rcs_diff = [ (_item(type='error')) ]
  else:
    rcs_diff = DiffSource(fp)

  data.update({
    'where' : where,
    'rev1' : rev1,
    'rev2' : rev2,
    'tag1' : sym1,
    'tag2' : sym2,
    'date1' : ', ' + rcsdiff_date_reformat(date1),
    'date2' : ', ' + rcsdiff_date_reformat(date2),
    'changes' : rcs_diff,
    'diff_format' : query_dict.get('diff_format', cfg.options.diff_format),
    })
    
  params = request.query_dict.copy()
  params['diff_format'] = None
    
  url, params = request.get_link(params=params)
  data['diff_format_action'] = urllib.quote(url, _URL_SAFE_CHARS)
  data['diff_format_hidden_values'] = prepare_hidden_values(params)

  generate_page(request, cfg.templates.diff, data)

def spaced_html_text(text):
  text = string.expandtabs(string.rstrip(text))

  # in the code below, "\x01" will be our stand-in for "&". We don't want
  # to insert "&" because it would get escaped by htmlify().  Similarly,
  # we use "\x02" as a stand-in for "<br>"

  if cfg.options.hr_breakable > 1 and len(text) > cfg.options.hr_breakable:
    text = re.sub('(' + ('.' * cfg.options.hr_breakable) + ')',
                  '\\1\x02',
                  text)
  if cfg.options.hr_breakable:
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
    
  human_readable = 0
  unified = 0
  args = [ ]

  ### Note: these options only really work out where rcsdiff (used by
  ### CVS) and regular diff (used by SVN) overlap.  If for some reason
  ### our use of the options for these starts to deviate too much,
  ### this code may a re-org to just do different things for different
  ### VC types.
  
  format = query_dict.get('diff_format', cfg.options.diff_format)
  if format == 'c':
    args.append('-c')
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
    fp = bincvs.rcs_popen(cfg.general, 'rcsdiff', args, 'rt')
  else:
    try:
      date1 = vclib.svn.date_from_rev(request.repos, int(rev1))
      date2 = vclib.svn.date_from_rev(request.repos, int(rev2))
    except vclib.InvalidRevision:
      raise debug.ViewcvsException('Invalid revision(s) passed to diff',
                                   '400 Bad Request')
      
    date1 = time.strftime('%Y/%m/%d %H:%M:%S', time.gmtime(date1))
    date2 = time.strftime('%Y/%m/%d %H:%M:%S', time.gmtime(date2))
    args.append("-L")
    args.append(p1 + "\t" + date1 + "\t" + rev1)
    args.append("-L")
    args.append(p2 + "\t" + date2 + "\t" + rev2)

    # Need to keep a reference to the FileDiff object around long
    # enough to use.  It destroys its underlying temporary files when
    # the class is destroyed.
    diffobj = vclib.svn.do_diff(request.repos, p1, int(rev1),
                                p2, int(rev2), args)
    
    fp = diffobj.get_pipe()
    
  if human_readable:
    human_readable_diff(request, fp, rev1, rev2, sym1, sym2)
    return

  request.server.header('text/plain')

  rootpath = request.repos.rootpath
  if unified:
    f1 = '--- ' + rootpath
    f2 = '+++ ' + rootpath
  else:
    f1 = '*** ' + rootpath
    f2 = '--- ' + rootpath

  while 1:
    line = fp.readline()
    if not line:
      break

    if line[:len(f1)] == f1:
      line = string.replace(line, rootpath + '/', '')
      if sym1:
        line = line[:-1] + ' %s\n' % sym1
    elif line[:len(f2)] == f2:
      line = string.replace(line, rootpath + '/', '')
      if sym2:
        line = line[:-1] + ' %s\n' % sym2

    print line[:-1]


def generate_tarball_header(out, name, size=0, mode=None, mtime=0, uid=0, gid=0, typefrag=None, linkname='', uname='viewcvs', gname='viewcvs', devmajor=1, devminor=0, prefix=None, magic='ustar', version='', chksum=None):
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

def generate_tarball_cvs(out, request, tar_top, rep_top, reldir, tag, stack=[]):
  if (rep_top == '' and 0 < len(reldir) and
      ((reldir[0] == 'CVSROOT' and cfg.options.hide_cvsroot)
       or cfg.is_forbidden(reldir[0]))):
    return

  rep_path = rep_top + reldir
  tar_dir = string.join(tar_top + reldir, '/') + '/'

  entries = request.repos.listdir(rep_path, tag)

  subdirs = [ ]
  for file in entries:
    if not file.verboten and file.kind == vclib.DIR:
      subdirs.append(file.name)

  stack.append(tar_dir)

  bincvs.get_logs(request.repos, rep_path, entries, tag)

  entries.sort(lambda a, b: cmp(a.name, b.name))

  for file in entries:
    if file.rev is None or file.state == 'dead':
      continue

    for dir in stack:
      generate_tarball_header(out, dir)
    del stack[0:]

    info = os.stat(file.path)
    mode = (info[stat.ST_MODE] & 0555) | 0200

    rev_flag = '-p' + file.rev
    fp = bincvs.rcs_popen(cfg.general, 'co', (rev_flag, file.path), 'rb', 0)
    contents = fp.read()
    status = fp.close()

    generate_tarball_header(out, tar_dir + file.name,
                            len(contents), mode, file.date)
    out.write(contents)
    out.write('\0' * (511 - ((len(contents) + 511) % 512)))

  subdirs.sort()
  for subdir in subdirs:
    if subdir != 'Attic':
      generate_tarball_cvs(out, request, tar_top, rep_top,
		       reldir + [subdir], tag, stack)

  if len(stack):
    del stack[-1:]

def generate_tarball_svn(out, request, tar_top, rep_top, reldir, tag, stack=[]):
  rep_dir = string.join(rep_top + reldir, '/')
  tar_dir = string.join(tar_top + reldir, '/') + '/'

  entries = request.repos.listdir(rep_top + reldir)

  subdirs = []
  for entry in entries:
    if entry.kind == vclib.DIR:
      subdirs.append(entry.name)

  vclib.svn.get_logs(request.repos, rep_dir, entries)

  stack.append(tar_dir)

  for file in entries:
    if file.kind != vclib.FILE:
      continue

    for dir in stack:
      generate_tarball_header(out, dir)
    del stack[0:]

    mode = 0644

    fp = request.repos.openfile(rep_top + reldir + [file.name])[0]

    contents = ""
    while 1:
      chunk = fp.read(CHUNK_SIZE)
      if not chunk:
        break
      contents = contents + chunk

    status = fp.close()

    generate_tarball_header(out, tar_dir + file.name,
                            len(contents), mode, file.date)
    out.write(contents)
    out.write('\0' * (511 - ((len(contents) + 511) % 512)))

  for subdir in subdirs:
    generate_tarball_svn(out, request, tar_top, rep_top,
                         reldir + [subdir], tag, stack)

  if len(stack):
    del stack[-1:]

def download_tarball(request):
  if not cfg.options.allow_tar:
    raise "tarball no allows"

  query_dict = request.query_dict
  rep_top = tar_top = request.path_parts
  tag = query_dict.get('only_with_tag')

  ### look for GZIP binary

  request.server.header('application/octet-stream')
  sys.stdout.flush()
  fp = popen.pipe_cmds([('gzip', '-c', '-n')])

  # Switch based on the repository root type.
  if request.roottype == 'cvs':
    generate_tarball_cvs(fp, request, tar_top, rep_top, [], tag)
  elif request.roottype == 'svn':
    generate_tarball_svn(fp, request, tar_top, rep_top, [], tag)

  fp.write('\0' * 1024)
  fp.close()

def view_revision(request):
  data = common_template_data(request)
  data.update({
    'roottype' : request.roottype,
  })

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
                                           params={})
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
    'ago' : html_time(request, date, 1),
    'changes' : changes,
    'jump_rev' : str(rev),
    'prev_href' : prev_rev_href,
    'next_href' : next_rev_href,
  })

  url, params = request.get_link(view_func=view_revision,
                                 where=None,
                                 pathtype=None,
                                 params={'rev': None})
  data['jump_rev_action'] = urllib.quote(url, _URL_SAFE_CHARS)
  data['jump_rev_hidden_values'] = prepare_hidden_values(params)

  request.server.header()
  generate_page(request, cfg.templates.revision, data)


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
  'rev':      view_revision,
  'tar':      download_tarball,
}

_view_codes = {}
for code, view in _views.items():
  _view_codes[view] = code

def list_roots(cfg):
  allroots = { }
  allroots.update(cfg.general.cvs_roots)
  allroots.update(cfg.general.svn_roots)
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

    # special handling for svn_parent_path.  any subdirectories
    # present in the directory specified as the svn_parent_path that
    # have a child file named "format" will be treated as svn_roots.
    if cfg.general.svn_parent_path is not None:
      pp = cfg.general.svn_parent_path
      try:
        subpaths = os.listdir(pp)
      except OSError:
        raise debug.ViewcvsException(
          "The setting for 'svn_parent_path' does not refer to "
          "a valid directory.")

      for subpath in subpaths:
        if os.path.exists(os.path.join(pp, subpath)) \
           and os.path.exists(os.path.join(pp, subpath, "format")):
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
