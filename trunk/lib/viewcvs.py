# -*-python-*-
#
# Copyright (C) 1999-2001 The ViewCVS Group. All Rights Reserved.
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

__version__ = '0.8-dev'

#########################################################################
#
# INSTALL-TIME CONFIGURATION
#
# These values will be set during the installation process. During
# development, they will remain None.
#

CONF_PATHNAME = None

#########################################################################

# standard modules that we know are in the path or builtin
import sys
import os
import cgi
import string
import urllib
import mimetypes
import time
import re
import stat
import struct

# these modules come from our library (the stub has set up the path)
import compat
import config
import popen
import ezt

#########################################################################

checkout_magic_path = '~checkout~'
helppage_magic_path = '~helppage~'
viewcvs_mime_type = 'text/vnd.viewcvs-markup'

# put here the variables we need in order to hold our state - they will be
# added (with their current value) to any link/query string you construct
_sticky_vars = (
  'cvsroot',
  'hideattic',
  'sortby',
  'logsort',
  'diff_format',
  'only_with_tag'
  )

# regex used to move from a file to a directory
_re_up_path = re.compile('(Attic/)?[^/]+$')

_EOF_FILE = 'end of file entries'       # no more entries for this RCS file
_EOF_LOG = 'end of log'                 # hit the true EOF on the pipe
_EOF_ERROR = 'error message found'      # rlog issued an error

_FILE_HAD_ERROR = 'could not read file'

_UNREADABLE_MARKER = '//UNREADABLE-MARKER//'

header_comment = '''\
<!-- ViewCVS       -- http://viewcvs.sourceforge.net/
     by Greg Stein -- mailto:gstein@lyra.org
  -->
'''

# for reading/writing between a couple descriptors
CHUNK_SIZE = 8192

# if your rlog doesn't use 77 '=' characters, then this must change
LOG_END_MARKER = '=' * 77 + '\n'
ENTRY_END_MARKER = '-' * 28 + '\n'

if CONF_PATHNAME:
  # installed
  g_template_dir = os.path.dirname(CONF_PATHNAME)
else:
  # development directories
  g_template_dir = os.pardir # typically, ".."


class Request:
  def __init__(self):
    where = os.environ.get('PATH_INFO', '')

    # clean it up. this removes duplicate '/' characters and any that may
    # exist at the front or end of the path.
    parts = filter(None, string.split(where, '/'))

    self.has_checkout_magic = 0
    self.has_helppage_magic = 0
    # does it have a magic prefix?
    if parts:
      if parts[0] == checkout_magic_path:
        self.has_checkout_magic = 1
        del parts[0]
      elif parts[0] == helppage_magic_path:
        self.has_helppage_magic = 1
        del parts[0]

    # put it back together
    where = string.join(parts, '/')

    script_name = os.environ['SCRIPT_NAME']     ### clean this up?
    if where:
      url = script_name + '/' + urllib.quote(where)
    else:
      url = script_name

    self.where = where
    self.script_name = script_name
    self.url = url
    if parts:
      self.module = parts[0]
    else:
      self.module = None

    self.browser = os.environ.get('HTTP_USER_AGENT', 'unknown')

    # in lynx, it it very annoying to have two links
    # per file, so disable the link at the icon
    # in this case:
    self.no_file_links = string.find(self.browser, 'Lynx') != -1

    # newer browsers accept gzip content encoding
    # and state this in a header
    # (netscape did always but didn't state it)
    # It has been reported that these
    #  braindamaged MS-Internet Explorers claim that they
    # accept gzip .. but don't in fact and
    # display garbage then :-/
    self.may_compress = (
      ( string.find(os.environ.get('HTTP_ACCEPT_ENCODING', ''), 'gzip') != -1
        or string.find(self.browser, 'Mozilla/3') != -1)
      and string.find(self.browser, 'MSIE') == -1
      )

    # parse the query params into a dictionary (and use defaults)
    query_dict = default_settings.copy()
    for name, values in cgi.parse().items():
      query_dict[name] = values[0]

    # set up query strings, prefixed by question marks and ampersands
    query = sticky_query(query_dict)
    if query:
      self.qmark_query = '?' + query
      self.amp_query = '&' + query
    else:
      self.qmark_query = ''
      self.amp_query = ''

    self.query_dict = query_dict

    # set up the CVS repository to use
    self.cvsrep = query_dict.get('cvsroot', cfg.general.default_root)
    try:
      self.cvsroot = cfg.general.cvs_roots[self.cvsrep]
    except KeyError:
      if query_dict.has_key('cvsroot'):
          error("Repository cvsroot %s not configured in viewcvs.conf" % 
                self.cvsrep, "404 Repository not found")
      else:
          error("The settings of 'cvs_roots' and "
                "default_root=%s are misconfigured in the viewcvs.conf file." %
                self.cvsrep)

    self.full_name = self.cvsroot + '/' + where

  def setup_mime_type_info(self):
    if cfg.general.mime_types_file:
      mimetypes.init([cfg.general.mime_types_file])
    self.mime_type, self.encoding = mimetypes.guess_type(self.where)
    if not self.mime_type:
      self.mime_type = 'text/plain'
    self.default_text_plain = self.mime_type == 'text/plain'
    self.default_viewable = cfg.options.allow_markup and \
                            is_viewable(self.mime_type)


class LogHeader:
  "Hold state from the header portion of an 'rlog' output."
  def __init__(self, filename, head=None, branch=None, taginfo=None):
    self.filename = filename
    self.head = head
    self.branch = branch
    self.taginfo = taginfo


class LogEntry:
  "Hold state for each revision entry in an 'rlog' output."
  def __init__(self, rev, date, author, state, changed, log):
    self.rev = rev
    self.date = date
    self.author = author
    self.state = state
    self.changed = changed
    self.log = log


def redirect(location):
  print 'Status: 301 Moved'
  print 'Location:', location
  print
  print 'This document is located <a href="%s">here</a>.' % location
  sys.exit(0)

def error(msg, status='500 Internal Server Error'):
  print 'Status:', status
  print
  print msg
  sys.exit(0)

_header_sent = 0
def http_header(content_type='text/html'):
  global _header_sent
  if _header_sent:
    return
  print 'Content-Type:', content_type
  print
  _header_sent = 1

def html_footer():
  print '<hr noshade><table width="100&#37;" border=0 cellpadding=0 cellspacing=0><tr>'
  print '<td align=left><address>%s</address></td>' % cfg.general.address
  print '<td align=right>Powered by<br><a href="http://viewcvs.sourceforge.net/">ViewCVS %s</a>' % __version__
  print '</td></tr></table>'
  print '</body></html>'

def sticky_query(dict):
  sticky_dict = { }
  for varname in _sticky_vars:
    value = dict.get(varname)
    if value is not None and value != default_settings.get(varname, ''):
      sticky_dict[varname] = value
  return compat.urlencode(sticky_dict)

def toggle_query(query_dict, which, value=None):
  dict = query_dict.copy()
  if value is None:
    dict[which] = not dict[which]
  else:
    dict[which] = value
  query = sticky_query(dict)
  if query:
    return '?' + query
  return ''

def clickable_path(request, path, leaf_is_link, leaf_is_file, drop_leaf):
  s = '<a href="%s/%s#dirlist">[%s]</a>' % \
      (request.script_name, request.qmark_query, request.cvsrep)
  parts = filter(None, string.split(path, '/'))
  if drop_leaf:
    del parts[-1]
    leaf_is_link = 1
    leaf_is_file = 0
  where = ''
  for i in range(len(parts)):
    where = where + '/' + parts[i]
    is_leaf = i == len(parts) - 1
    if not is_leaf or leaf_is_link:
      if is_leaf and leaf_is_file:
        slash = ''
      else:
        slash = '/'
      ### should we be encoding/quoting the URL stuff? (probably...)
      s = s + ' / <a href="%s%s%s%s#dirlist">%s</a>' % \
          (request.script_name, where, slash, request.qmark_query, parts[i])
    else:
      s = s + ' / ' + parts[i]

  return s

def html_link(contents, link):
  return '<a href="%s">%s</a>' % (link, contents)

def prep_tags(query_dict, file_url, tags):
  links = [ ]
  for tag in tags:
    href = file_url + toggle_query(query_dict, 'only_with_tag', tag)
    links.append(_item(name=tag, href=href))
  return links

def is_viewable(mime_type):
  return mime_type[:5] == 'text/' or mime_type[:6] == 'image/'

_re_rewrite_url = re.compile('((http|ftp)(://[-a-zA-Z0-9%.~:_/]+)([?&]([-a-zA-Z0-9%.~:_]+)=([-a-zA-Z0-9%.~:_])+)*(#([-a-zA-Z0-9%.~:_]+)?)?)')
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

def download_url(request, url, revision, mime_type):
  if cfg.options.checkout_magic and mime_type != viewcvs_mime_type:
    url = '%s/%s/%s/%s' % \
          (request.script_name, checkout_magic_path,
           os.path.dirname(request.where), url)

  url = url + '?rev=' + revision + request.amp_query
  if mime_type:
    return url + '&content-type=' + mime_type
  return url

def download_link(request, url, revision, text, mime_type=None):
  full_url = download_url(request, url, revision, mime_type)
  paren = text[0] == '('

  lparen = rparen = ''
  if paren:
    lparen = '('
    rparen = ')'
    text = text[1:-1]

  print '%s<a href="%s"' % (lparen, full_url)

  if cfg.options.open_extern_window and mime_type != viewcvs_mime_type:
    print ' target="cvs_checkout"'
    if cfg.options.use_java_script:
      print " onClick=\"window.open('about:blank','cvs_checkout'," \
            "'resizeable=1,scrollbars=1",
      if mime_type == 'text/html':
        print ',status,toolbar',
      print "');\""
  print '><b>%s</b></a>%s' % (text, rparen)

def html_icon(which):
  return cfg.images.get_image(which + '_icon')

def plural(num, text):
  if num == 1:
    return '1 ' + text
  if num:
    return '%d %ss' % (num, text)
  return ''

_time_desc = {
         1 : 'second',
        60 : 'minute',
      3600 : 'hour',
     86400 : 'day',
    604800 : 'week',
   2628000 : 'month',
  31536000 : 'year',
  }
def html_time(secs, extended=0):
  secs = long(time.time()) - secs
  if secs < 2:
    return 'very little time'
  breaks = _time_desc.keys()
  breaks.sort()
  i = 0
  while i < len(breaks):
    if secs < 2 * breaks[i]:
      break
    i = i + 1
  value = breaks[i - 1]
  s = plural(secs / value, _time_desc[value])

  if extended and i > 1:
    secs = secs % value
    value = breaks[i - 2]
    ext = plural(secs / value, _time_desc[value])
    if ext:
      s = s + ', ' + ext
  return s

def html_option(value, cur_value, text=None):
  if text is None:
    attr = ''
    text = value
  else:
    attr = 'value="%s"' % value

  if value == cur_value:
    print '<option %s selected>%s</option>' % (attr, text)
  else:
    print '<option %s>%s</option>' % (attr, text)

def print_diff_select(query_dict):
  print '<select name="diff_format"'
  if cfg.options.use_java_script:
    print 'onchange="submit()"'
  print '>'

  format = query_dict['diff_format']
  html_option('h', format, 'Colored Diff')
  html_option('l', format, 'Long Colored Diff')
  html_option('u', format, 'Unidiff')
  html_option('c', format, 'Context Diff')
  html_option('s', format, 'Side by Side')
  print '</select>'

def navigate_header(request, swhere, path, filename, rev, title):
  if swhere == request.url:
    swhere = urllib.quote(filename)

  print '<html><head>'
  print header_comment
  print '<title>%s/%s - %s - %s</title></head>' % (path, filename, title, rev)
  print '<body bgcolor="%s">' % cfg.colors.alt_background
  print '<table width="100&#37;" border=0 cellspacing=0 cellpadding=1 bgcolor="%s">' % cfg.colors.nav_header
  print '<tr valign=bottom><td>'
  print '<a href="%s%s#rev%s">%s</a>' % \
        (swhere, request.qmark_query, rev, html_icon('back'))
  print '<b>Return to %s CVS log</b> %s</td>' % \
        (html_link(filename,
                   '%s%s#rev%s' % (swhere, request.qmark_query, rev)),
         html_icon('file'))
  print '<td align=right>%s <b>Up to %s</b></td>' % \
        (html_icon('dir'), clickable_path(request, path, 1, 0, 0))
  print '</tr></table>'

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

def markup_stream_enscript(lang, fp):
  sys.stdout.flush()
  enscript = popen.pipe_cmds([(cfg.options.enscript_path + 'enscript',
                               '--color', '-W', 'html', '-E' + lang, '-o',
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
  except IOError, v:
    print "<h3>Failure during use of an external program:</h3>"
    print "<pre>"
    print cfg.options.enscript_path+"enscript --color -W html -E"+lang+" -o - -"
    print "</pre>"
    raise

  enscript.close()

markup_streamers = {
#  '.py' : markup_stream_python,
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
  '.ada' : 'ada',
  '.adb' : 'ada',
  '.ads' : 'ada',
  '.awk' : 'awk',
  '.c' : 'c',
  '.c++' : 'cpp',
  '.cc' : 'cpp',
  '.cpp' : 'cpp',
  '.cxx' : 'cpp',
  '.el' : 'elisp',
  '.eps' : 'postscript',
  '.f' : 'fortran',
  '.gs' : 'haskell',
  '.h' : 'c',
  '.hs' : 'haskell',
  '.htm' : 'html',
  '.html' : 'html',
  '.idl' : 'idl',
  '.java' : 'java',
  '.js' : 'javascript',
  '.lgs' : 'haskell',
  '.lhs' : 'haskell',
  '.m' : 'objc',
  '.p' : 'pascal',
  '.pas' : 'pascal',
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
  '.st' : 'states',
  '.syn' : 'synopsys',
  '.synth' : 'synopsys',
  '.tcl' : 'tcl',
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
  'Makefile' : 'makefile',
  'makefile' : 'makefile',
  }

def markup_stream(request, fp, revision, mime_type):
  full_name = request.full_name
  where = request.where
  query_dict = request.query_dict

  pathname, filename = os.path.split(where)
  if pathname[-6:] == '/Attic':
    pathname = pathname[:-6]
  file_url = urllib.quote(filename)

  http_header()
  navigate_header(request, request.url, pathname, filename, revision, 'view')
  print '<hr noshade>'
  print '<table width="100&#37;"><tr><td bgcolor="%s">' % cfg.colors.markup_log
  print 'File:', clickable_path(request, where, 1, 1, 0), '</b>'
  download_link(request, file_url, revision, '(download)')
  if not request.default_text_plain:
    download_link(request, file_url, revision, '(as text)', 'text/plain')
  print '<br>'
  if cfg.options.show_log_in_markup:
    show_revs, rev_map, rev_order, taginfo, rev2tag, \
               cur_branch, branch_points, branch_names = read_log(full_name)

    print_log(request, rev_map, rev_order, rev_map[revision], rev2tag,
              branch_points)
  else:
    print 'Version: <b>%s</b><br>' % revision
    tag = query_dict.get('only_with_tag')
    if tag:
      print 'Tag: <b>%s</b><br>' % tag
  print '</td></tr></table>'

  print '<hr noshade>'
  if mime_type[:6] == 'image/':
    url = download_url(request, file_url, revision, mime_type)
    print '<img src="%s"><br>' % url
    while fp.read(8192):
      pass
  else:
    basename, ext = os.path.splitext(filename)
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
  html_footer()

def get_file_data(full_name):
  """Return a sequence of tuples containing various data about the files.

  data[0] = (relative) filename
  data[1] = full pathname
  data[2] = is_directory (0/1)

  Only RCS files (*,v) and subdirs are returned.
  """
  
  files = os.listdir(full_name)
  data = [ ]

  uid = os.getuid()
  gid = os.getgid()

  for file in files:
    pathname = full_name + '/' + file
    try:
      info = os.stat(pathname)
    except os.error:
      data.append((file, _UNREADABLE_MARKER, None))
      continue
    mode = info[stat.ST_MODE]
    isdir = stat.S_ISDIR(mode)
    isreg = stat.S_ISREG(mode)
    if (isreg and file[-2:] == ',v') or isdir:
      #
      # Quick version of access() where we use existing stat() data.
      #
      # This might not be perfect -- the OS may return slightly different
      # results for some bizarre reason. However, we make a good show of
      # "can I read this file/dir?" by checking the various perm bits.
      #
      # NOTE: if the UID matches, then we must match the user bits -- we
      # cannot defer to group or other bits. Similarly, if the GID matches,
      # then we must have read access in the group bits.
      #
      if isdir:
        mask = stat.S_IROTH | stat.S_IXOTH
      else:
        mask = stat.S_IROTH

      valid = 1
      if info[stat.ST_UID] == uid:
        if ((mode >> 6) & mask) != mask:
          valid = 0
      elif info[stat.ST_GID] == gid:
        if ((mode >> 3) & mask) != mask:
          valid = 0
      elif (mode & mask) != mask:
        valid = 0

      if valid:
        data.append((file, pathname, isdir))
      else:
        data.append((file, _UNREADABLE_MARKER, isdir))

  return data

def get_last_modified(file_data):
  """Return mapping of subdir to info about the most recently modified subfile.

  key     = subdir
  data[0] = "subdir/subfile" of the most recently modified subfile
  data[1] = the mod time of that file (time_t)
  """

  lastmod = { }
  for file, pathname, isdir in file_data:
    if not isdir or pathname == _UNREADABLE_MARKER:
      continue
    if file == 'Attic':
      continue

    subfiles = os.listdir(pathname)
    latest = ('', 0)
    for subfile in subfiles:
      ### filter CVS locks? stale NFS handles?
      if subfile[-2:] != ',v':
        continue
      subpath = pathname + '/' + subfile
      info = os.stat(subpath)
      if not stat.S_ISREG(info[stat.ST_MODE]):
        continue
      if info[stat.ST_MTIME] > latest[1]:
        latest = (file + '/' + subfile, info[stat.ST_MTIME])
    if latest[0]:
      lastmod[file] = latest
  return lastmod

def parse_log_header(fp):
  """Parse and RCS/CVS log header.

  fp is a file (pipe) opened for reading the log information.

  On entry, fp should point to the start of a log entry.
  On exit, fp will have consumed the separator line between the header and
  the first revision log.

  If there is no revision information (e.g. the "-h" switch was passed to
  rlog), then fp will consumed the file separator line on exit.
  """
  filename = head = branch = None
  taginfo = { }         # tag name => revision

  parsing_tags = 0
  eof = None

  while 1:
    line = fp.readline()
    if not line:
      # the true end-of-file
      eof = _EOF_LOG
      break

    if parsing_tags:
      if line[0] == '\t':
        [ tag, rev ] = map(string.strip, string.split(line, ':'))
        taginfo[tag] = rev
      else:
        # oops. this line isn't tag info. stop parsing tags.
        parsing_tags = 0

    if not parsing_tags:
      if line[:9] == 'RCS file:':
        # remove the trailing ,v
        filename = line[10:-3]
      elif line[:5] == 'head:':
        head = line[6:-1]
      elif line[:7] == 'branch:':
        branch = line[8:-1]
      elif line[:14] == 'symbolic names':
        # start parsing the tag information
        parsing_tags = 1
      elif line == ENTRY_END_MARKER:
        # end of the headers
        break
      elif line == LOG_END_MARKER:
        # end of this file's log information
        eof = _EOF_FILE
        break
      elif line[:6] == 'rlog: ':
        # rlog: filename/goes/here,v: error message
        idx = string.find(line, ':', 6)
        if idx != -1:
          if line[idx:idx+32] == ': warning: Unknown phrases like ':
            # don't worry about this warning. it can happen with some RCS
            # files that have unknown fields in them (e.g. "permissions 644;"
            continue

          # looks like a filename
          filename = line[6:idx]
          if filename[-2:] == ',v':
            filename = filename[:-2]
          return LogHeader(filename), _EOF_ERROR
        # dunno what this is

  return LogHeader(filename, head, branch, taginfo), eof

_re_date_author = re.compile(r'^date:\s+([^;]+);\s+author:\s+([^;]+);.*')
_re_log_info = re.compile(r'^date:\s+([^;]+);'
                          r'\s+author:\s+([^;]+);'
                          r'\s+state:\s+([^;]+);'
                          r'(\s+lines:\s+([0-9\s+-]+))?\n$')
### _re_rev should be updated to extract the "locked" flag
_re_rev = re.compile(r'^revision\s+([0-9.]+).*')
def parse_log_entry(fp):
  """Parse a single log entry.

  On entry, fp should point to the first line of the entry (the "revision"
  line).
  On exit, fp will have consumed the log separator line (dashes) or the
  end-of-file marker (equals).

  Returns: revision, date (time_t secs), author, state, lines changed,
  the log text, and eof flag (see _EOF_*)
  """
  rev = None
  line = fp.readline()
  if not line:
    return None, _EOF_LOG
  if line[:8] == 'revision':
    match = _re_rev.match(line)
    if not match:
      return None, _EOF_LOG
    rev = match.group(1)

    line = fp.readline()
    if not line:
      return None, _EOF_LOG
    match = _re_log_info.match(line)

  eof = None
  log = ''
  while 1:
    line = fp.readline()
    if not line:
      # true end-of-file
      eof = _EOF_LOG
      break
    if line[:9] == 'branches:':
      continue
    if line == ENTRY_END_MARKER:
      break
    if line == LOG_END_MARKER:
      # end of this file's log information
      eof = _EOF_FILE
      break

    log = log + line

  if not rev or not match:
    # there was a parsing error
    return None, eof

  # parse out a time tuple for the local time
  tm = compat.cvs_strptime(match.group(1))
  try:
   date = int(time.mktime(tm)) - time.timezone
  except OverflowError:
    # it is possible that CVS recorded an "illegal" time, such as those
    # which occur during a Daylight Savings Time switchover (there is a
    # gap in the time continuum). Let's advance one hour and try again.
    # While the time isn't necessarily "correct", recall that the gap means
    # that times *should* be an hour forward. This is certainly close enough
    # for our needs.
    #
    # Note: a true overflow will simply raise an error again, which we won't
    # try to catch a second time.
    tm = tm[:3] + (tm[3] + 1,) + tm[4:]
    date = int(time.mktime(tm)) - time.timezone

  return LogEntry(rev, date,
                  # author, state, lines changed
                  match.group(2), match.group(3), match.group(5),
                  log), eof

def skip_file(fp):
  "Skip the rest of a file's log information."
  while 1:
    line = fp.readline()
    if not line:
      break
    if line == LOG_END_MARKER:
      break

def process_rlog_output(rlog, full_name, view_tag, fileinfo, alltags):
  "Fill in fileinfo and alltags with info from the rlog output."

  # consume each file found in the resulting log
  while 1:

    revwanted = None
    branch = None
    branchpoint = None

    header, eof = parse_log_header(rlog)
    filename = header.filename
    head = header.head
    branch = header.branch
    symrev = header.taginfo

    # the rlog output is done
    if eof == _EOF_LOG:
      break

    if filename:
      # convert from absolute to relative
      if filename[:len(full_name)] == full_name:
        filename = filename[len(full_name)+1:]

      # for a subdir (not Attic files!), use the subdir for a key
      idx = string.find(filename, '/')
      if idx != -1 and filename[:6] != 'Attic/':
        info_key = filename[:idx]
      else:
        info_key = filename

    # an error was found regarding this file
    if eof == _EOF_ERROR:
      fileinfo[info_key] = _FILE_HAD_ERROR
      continue

    # if we hit the end of the log information (already!), then there is
    # nothing we can do with this file
    if eof:
      continue

    if not filename or not head:
      # parsing error. skip the rest of this file.
      skip_file(rlog)
      continue

    if not branch:
      idx = string.rfind(head, '.')
      branch = head[:idx]
    idx = string.rfind(branch, '.')
    if idx == -1:
      branch = '0.' + branch
    else:
      branch = branch[:idx] + '.0' + branch[idx:]

    symrev['MAIN'] = symrev['HEAD'] = branch

    if symrev.has_key(view_tag):
      revwanted = symrev[view_tag]
      if revwanted[:2] == '0.': ### possible?
        branch = revwanted[2:]
      else:
        idx = string.find(revwanted, '.0.')
        if idx == -1:
          branch = revwanted
        else:
          branch = revwanted[:idx] + revwanted[idx+2:]
      if revwanted != branch:
        revwanted = None

      idx = string.rfind(branch, '.')
      if idx == -1:
        branchpoint = ''
      else:
        branchpoint = branch[:idx]

    elif view_tag:
      # the tag wasn't found, so skip this file
      skip_file(rlog)
      continue

    # we don't care about the values -- just the keys. this the fastest
    # way to merge the set of keys
    alltags.update(symrev)

    # read all of the log entries until we find the revision we want
    while 1:

      # fetch one of the log entries
      entry, eof = parse_log_entry(rlog)

      if not entry:
        # parsing error
        if not eof:
          skip_file(rlog)
        break

      rev = entry.rev

      idx = string.rfind(rev, '.')
      revbranch = rev[:idx]

      if not view_tag or (not revwanted and branch == revbranch):
        revwanted = rev

      if rev == revwanted or rev == branchpoint:
        fileinfo[info_key] = (rev, entry.date, entry.log, entry.author,
                              filename, entry.state)

        if rev == revwanted:
          # done with this file now
          if not eof:
            skip_file(rlog)
          break

      # if we hit the true EOF, or just this file's end-of-info, then we are
      # done collecting log entries.
      if eof:
        break

def get_logs(full_name, files, view_tag):

  if len(files) == 0:
    return { }, { }

  fileinfo = { }
  alltags = {           # all the tags seen in the files of this dir
    'MAIN' : '1',
    'HEAD' : '1',
    }

  chunk_size = 100
  while files:
    chunk = files[:chunk_size]
    del files[:chunk_size]

    # prepend the full pathname for each file
    for i in range(len(chunk)):
      chunk[i] = full_name + '/' + chunk[i]

    if view_tag:
      # NOTE: can't pass tag on command line since a tag may contain "-"
      #       we'll search the output for the appropriate revision
      rlog = popen.popen(cfg.general.rcs_path + 'rlog', chunk, 'r')
    else:
      # fetch the latest revision on the default branch
      chunk = ('-r',) + tuple(chunk)
      rlog = popen.popen(cfg.general.rcs_path + 'rlog', chunk, 'r')

    process_rlog_output(rlog, full_name, view_tag, fileinfo, alltags)

    ### it would be nice to verify that we got SOMETHING from rlog about
    ### each file. if we didn't, then it could be that the chunk is still
    ### too large, so we want to cut the chunk_size in half and try again.
    ###
    ### BUT: if we didn't get feedback for some *other* reason, then halving
    ### the chunk size could merely send us into a needless retry loop.
    ###
    ### more work for later...

    status = rlog.close()
    if status:
      raise 'error during rlog: '+hex(status)

  return fileinfo, alltags

def revcmp(rev1, rev2):
  rev1 = map(int, string.split(rev1, '.'))
  rev2 = map(int, string.split(rev2, '.'))
  return cmp(rev1, rev2)

def view_directory(request):
  full_name = request.full_name
  where = request.where
  query_dict = request.query_dict

  view_tag = query_dict.get('only_with_tag')
  hideattic = int(query_dict.get('hideattic'))  ### watch for errors in int()?
  sortby = query_dict.get('sortby', 'file')

  file_data = get_file_data(full_name)

  if cfg.options.show_subdir_lastmod:
    lastmod = get_last_modified(file_data)
  else:
    lastmod = { }
  if cfg.options.show_logs:
    subfiles = map(lambda (subfile, mtime): subfile, lastmod.values())
  else:
    subfiles = [ ]

  attic_files = [ ]
  if not hideattic or view_tag:
    try:
      attic_files = os.listdir(full_name + '/Attic')
    except os.error:
      pass
    else:
      ### filter for just RCS files?
      attic_files = map(lambda file: 'Attic/' + file, attic_files)

  # get all the required info
  rcs_files = subfiles + attic_files
  for file, pathname, isdir in file_data:
    if not isdir and pathname != _UNREADABLE_MARKER:
      rcs_files.append(file)
  fileinfo, alltags = get_logs(full_name, rcs_files, view_tag)

  # append the Attic files into the file_data now
  # NOTE: we only insert the filename and isdir==0
  for file in attic_files:
    file_data.append((file, None, 0))

  http_header()

  template = ezt.Template()
  template.parse_file(os.path.join(g_template_dir, cfg.templates.directory))

  # prepare the data that will be passed to the template
  data = {
    'where' : where,
    'request' : request,
    'cfg' : cfg,
    'current_root' : request.cvsrep,
    'view_tag' : view_tag,
    'sortby' : sortby,
    'headers' : [ ],
    'no_match' : None,
    'unreadable' : None,
    'has_tags' : None,
    'tarball_href' : None,
    'address' : cfg.general.address,
    'vsn' : __version__,
    }

  # add in the CVS roots for the selection
  if len(cfg.general.cvs_roots) < 2:
    roots = [ ]
  else:
    roots = cfg.general.cvs_roots.keys()
    roots.sort(lambda n1, n2: cmp(string.lower(n1), string.lower(n2)))
  data['roots'] = roots

  if where:
    ### in the future, it might be nice to break this path up into
    ### a list of elements, allowing the template to display it in
    ### a variety of schemes.
    data['nav_path'] = clickable_path(request, where, 0, 0, 0)

  def add_header(title, which, data=data, query_dict=query_dict, colspan=1):
    href = './' + toggle_query(query_dict, 'sortby', which) + '#dirlist'
    data['headers'].append(_item(title=title, which=which, href=href,
                                 colspan=colspan))

  if cfg.options.use_cvsgraph:
    add_header('File', 'file', colspan=2)
  else:
    add_header('File', 'file')

  # fileinfo will be len==0 if we only have dirs and !show_subdir_lastmod
  # in that case, we don't need the extra columns
  if len(fileinfo):
    add_header('Rev.', 'rev')
    add_header('Age', 'date')
    if cfg.options.show_author:
      add_header('Author', 'author')
    if cfg.options.show_logs:
      add_header('Last log entry', 'log')

  num_cols = len(data['headers']) + cfg.options.use_cvsgraph


  def file_sort_cmp(data1, data2, sortby=sortby, fileinfo=fileinfo):
    if data1[2]:        # is_directory
      if data2[2]:
        # both are directories. sort on name.
        return cmp(data1[0], data2[0])
      # data1 is a directory, it sorts first.
      return -1
    if data2[2]:
      # data2 is a directory, it sorts first.
      return 1

    # the two files should be RCS files. drop the ",v" from the end.
    file1 = data1[0][:-2]
    file2 = data2[0][:-2]

    # we should have data on these. if not, then it is because we requested
    # a specific tag and that tag is not present on the file.
    info1 = fileinfo.get(file1)
    if info1 == _FILE_HAD_ERROR:
      info1 = None
    info2 = fileinfo.get(file2)
    if info2 == _FILE_HAD_ERROR:
      info2 = None
    if info1 and info2:
      if sortby == 'rev':
        result = revcmp(info1[0], info2[0])
      elif sortby == 'date':
        result = cmp(info2[1], info1[1])        # latest date is first
      elif sortby == 'log':
        result = cmp(info1[2], info2[2])
      elif sortby == 'author':
        result = cmp(info1[3], info2[3])
      else:
        # sortby == 'file' ... fall thru
        result = 0

      # return for unequal values; or fall thru for secondary-sort on name
      if result:
        return result

    # sort by file name
    if file1[:6] == 'Attic/':
      file1 = file1[6:]
    if file2[:6] == 'Attic/':
      file2 = file2[6:]
    return cmp(file1, file2)

  # sort with directories first, and using the "sortby" criteria
  file_data.sort(file_sort_cmp)

  num_files = 0
  num_displayed = 0
  unreadable = 0

  attic_toggle_link = '<a href="./%s#dirlist">[Hide]</a>' % \
                      toggle_query(query_dict, 'hideattic', 1)

  ### display a row for ".." ?

  rows = data['rows'] = [ ]

  for file, pathname, isdir in file_data:

    row = _item(href=None, hide_attic_href=None, graph_href=None,
                author=None, log=None, log_file=None, log_rev=None,
                show_log=None)

    if pathname == _UNREADABLE_MARKER:
      if isdir is None:
        # We couldn't even stat() the file to figure out what it is.
        slash = ''
      elif isdir:
        slash = '/'
      else:
        slash = ''
        file = file[:-2]        # strip the ,v
        num_displayed = num_displayed + 1
      row.anchor = file
      row.name = file + slash
      row.span = num_cols - 1
      row.type = 'unreadable'

      rows.append(row)

      unreadable = 1
      continue

    if isdir:
      if not hideattic and file == 'Attic':
        continue
      if where == '' and ((file == 'CVSROOT' and cfg.options.hide_cvsroot)
                          or cfg.is_forbidden(file)):
        continue
      if file == 'CVS': # CVS directory in a repository is used for fileattr.
        continue

      url = urllib.quote(file) + '/' + request.qmark_query

      row.anchor = file
      row.href = url
      row.name = file + '/'
      row.type = 'dir'

      if file == 'Attic':
        row.hide_attic_href = './' + toggle_query(query_dict, 'hideattic', 0) \
                              + '#dirlist'

      info = fileinfo.get(file)
      if info == _FILE_HAD_ERROR:
        row.cvs = 'error'
        row.span = num_cols - 1

        unreadable = 1
      elif info:
        row.cvs = 'data'
        row.time = html_time(info[1])

        if cfg.options.use_cvsgraph:
          row.graph_href = '&nbsp;' 
        if cfg.options.show_author:
          row.author = info[3]
        if cfg.options.show_logs:
          row.show_log = 'yes'
          subfile = info[4]
          idx = string.find(subfile, '/')
          row.log_file = subfile[idx+1:]
          row.log_rev = info[0]
          if info[2]:
            row.log = format_log(info[2])
      else:
        row.cvs = 'none'
        row.cols = [ '' ] * (num_cols - 1)

      rows.append(row)

    else:
      # remove the ",v"
      file = file[:-2]

      row.type = 'file'
      row.anchor = file
      row.name = file

      num_files = num_files + 1
      info = fileinfo.get(file)
      if info == _FILE_HAD_ERROR:
        row.cvs = 'error'
        row.span = num_cols - 1
        rows.append(row)

        num_displayed = num_displayed + 1
        unreadable = 1
        continue
      elif not info:
        continue
      elif hideattic and view_tag and info[5] == 'dead':
        continue
      num_displayed = num_displayed + 1

      file_url = urllib.quote(file)
      url = file_url + request.qmark_query

      if view_tag:
        if info[5] == 'dead':
          attic = ' (not exist)&nbsp;' + attic_toggle_link
        else:
          attic = ''
      else:
        if file[:6] == 'Attic/':
          attic = ' (in the Attic)&nbsp;' + attic_toggle_link
        else:
          attic = ''

      if file[:6] == 'Attic/':
        file = file[6:]

      row.cvs = 'data'
      row.href = url
      row.rev = info[0]

      ### it would be good to break this out into bits so the .ezt can
      ### format this info however it likes
      row.attic = attic

      row.rev_href = file_url + '?rev=' + row.rev + request.amp_query

      row.time = html_time(info[1])

      if cfg.options.use_cvsgraph:
         row.graph_href = file_url + '?graph=' + row.rev + request.amp_query

      if cfg.options.show_author:
        row.author = info[3]

      if cfg.options.show_logs:
        row.show_log = 'yes'
        row.log = format_log(info[2])

      rows.append(row)

  data['num_files'] = num_files

  if num_files and not num_displayed:
    data['no_match'] = 'yes'
  if unreadable:
    data['unreadable'] = 'yes'

  if alltags or view_tag:
    data['has_tags'] = 'yes'
    data['params'] = params = [ ]

    for varname in _sticky_vars:
      value = query_dict.get(varname, '')
      if value != '' and value != default_settings.get(varname, '') and \
         varname != 'only_with_tag':
        params.append(_item(name=varname, value=query_dict[varname]))

    alltagnames = alltags.keys()
    alltagnames.sort(lambda t1, t2: cmp(string.lower(t1), string.lower(t2)))
    alltagnames.reverse()
    branchtags = []
    nonbranchtags = []
    for tag in alltagnames:
      rev = alltags[tag]
      if string.find(rev, '.0.') == -1:
        nonbranchtags.append(tag)
      else:
        branchtags.append(tag)

    data['branch_tags'] = branchtags
    data['plain_tags'] = nonbranchtags

  if cfg.options.allow_tar:
    tar_basename = os.path.basename(where) 
    if not tar_basename:
      tar_basename = "cvs_root"
    url = tar_basename + '.tar.gz?tarball=1'
    query = sticky_query(query_dict)
    if query:
      url = url + '&' + query
    data['tarball_href'] = url

  # generate the page
  template.generate(sys.stdout, data)

def fetch_log(full_name, which_rev=None):
  if which_rev:
    args = ('-r' + which_rev, full_name)
  else:
    args = (full_name,)
  rlog = popen.popen(cfg.general.rcs_path + 'rlog', args, 'r')

  header, eof = parse_log_header(rlog)
  filename = header.filename
  head = header.head
  branch = header.branch
  taginfo = header.taginfo

  if eof:
    # no log entries or a parsing failure
    return head, branch, taginfo, [ ]

  revs = [ ]
  while 1:
    entry, eof = parse_log_entry(rlog)
    if entry:
      # valid revision info
      revs.append(entry)
    if eof:
      break

  return head, branch, taginfo, revs

def logsort_date_cmp(rev1, rev2):
  # sort on date; secondary on revision number
  return -cmp(rev1.date, rev2.date) or -revcmp(rev1.rev, rev2.rev)

def logsort_rev_cmp(rev1, rev2):
  # sort highest revision first
  return -revcmp(rev1.rev, rev2.rev)

_re_is_branch = re.compile(r'^((.*)\.)?\b0\.(\d+)$')
def read_log(full_name, which_rev=None, view_tag=None, logsort='cvs'):
  head, cur_branch, taginfo, revs = fetch_log(full_name, which_rev)

  if not cur_branch:
    idx = string.rfind(head, '.')
    cur_branch = head[:idx]

  rev_order = map(lambda entry: entry.rev, revs)
  rev_order.sort(revcmp)
  rev_order.reverse()

  # HEAD is an artificial tag which is simply the highest tag number on the
  # main branch, unless there is a branch tag in the RCS file in which case
  # it's the highest revision on that branch.  Find it by looking through
  # rev_order; it is the first commit listed on the appropriate branch.
  # This is not neccesary the same revision as marked as head in the RCS file.
  idx = string.rfind(cur_branch, '.')
  if idx == -1:
    taginfo['MAIN'] = '0.' + cur_branch
  else:
    taginfo['MAIN'] = cur_branch[:idx] + '.0' + cur_branch[idx:]

  for rev in rev_order:
    idx = string.rfind(rev, '.')
    if idx != -1 and cur_branch == rev[:idx]:
      taginfo['HEAD'] = rev
      break
  else:
    idx = string.rfind(cur_branch, '.')
    taginfo['HEAD'] = cur_branch[:idx]

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
  for tag, rev in items:
    match = _re_is_branch.match(rev)
    if match:
      branch_names.append(tag)

      #
      # A revision number of A.B.0.D really translates into
      # "the highest current revision on branch A.B.D".
      #
      # If there is no branch A.B.D, then it translates into
      # the head A.B .
      #
      # This reasoning also applies to the main branch A.B,
      # with the branch number 0.A, with the exception that
      # it has no head to translate to if there is nothing on
      # the branch, but I guess this can never happen?
      # (the code below gracefully forgets about the branch
      # if it should happen)
      #
      head = match.group(2) or ''
      branch = match.group(3)
      if head:
        branch_rev = head + '.' + branch
      else:
        branch_rev = branch
      rev = head
      for r in rev_order:
        if r == branch_rev or r[:len(branch_rev)+1] == branch_rev + '.':
          rev = branch_rev
          break
      if rev == '':
        continue
      if rev != head and head != '':
        if branch_points.has_key(head):
          branch_points[head].append(tag)
        else:
          branch_points[head] = [ tag ]

    if rev2tag.has_key(rev):
      rev2tag[rev].append(tag)
    else:
      rev2tag[rev] = [ tag ]

  if view_tag:
    view_rev = taginfo.get(view_tag)
    if not view_rev:
      error('Tag %s not defined.' % view_tag, '404 Tag not found')

    if view_rev[:2] == '0.':
      view_rev = view_rev[2:]
      idx = string.rfind(view_rev, '.')
      branch_point = view_rev[:idx]
    else:
      idx = string.find(view_rev, '.0.')
      if idx == -1:
        branch_point = view_rev
      else:
        view_rev = view_rev[:idx] + view_rev[idx+2:]
        idx = string.rfind(view_rev, '.')
        branch_point = view_rev[:idx]

    show_revs = [ ]
    for entry in revs:
      rev = entry.rev
      idx = string.rfind(rev, '.')
      branch = rev[:idx]
      if branch == view_rev or rev == branch_point:
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
         cur_branch, branch_points, branch_names

g_name_printed = { }    ### gawd, what a hack...
def augment_entry(entry, request, file_url, rev_map, rev2tag, branch_points,
                  rev_order, extended):
  "Augment the entry with additional, computed data from the log output."

  query_dict = request.query_dict

  rev = entry.rev
  idx = string.rfind(rev, '.')
  branch = rev[:idx]

  if _re_is_vendor_branch.match(rev):
    entry.vendor_branch = 'yes'
  else:
    entry.vendor_branch = None

  entry.utc_date = time.asctime(time.gmtime(entry.date))
  entry.ago = html_time(entry.date, 1)

  entry.branches = prep_tags(query_dict, file_url, rev2tag.get(branch, [ ]))
  entry.tags = prep_tags(query_dict, file_url, rev2tag.get(rev, [ ]))
  entry.branch_points = prep_tags(query_dict, file_url,
                                  branch_points.get(rev, [ ]))

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
    if rev2tag.has_key(branch) and not g_name_printed.has_key(branch):
      entry.branch_names = rev2tag.get(branch)
      g_name_printed[branch] = 1
    else:
      entry.branch_names = [ ]

    ### I don't like this URL construction stuff. not obvious enough (how
    ### it keys off the mime_type to do different things). also, the
    ### value for entry.href is a bit bogus: why decide to include/exclude
    ### the mime type from the URL? should just always be the same, right?
    entry.view_href = download_url(request, file_url, rev, viewcvs_mime_type)
    if request.default_viewable:
      entry.href = download_url(request, file_url, rev, None)
    else:
      entry.href = download_url(request, file_url, rev, request.mime_type)
    entry.text_href = download_url(request, file_url, rev, 'text/plain')

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

_re_is_vendor_branch = re.compile(r'^1\.1\.1\.\d+$')
def print_log(request, rev_map, rev_order, entry, rev2tag, branch_points):
  query_dict = request.query_dict
  where = request.where
  rev = entry.rev

  idx = string.rfind(rev, '.')
  branch = rev[:idx]

  print 'Revision <b>%s</b>' % rev

  if _re_is_vendor_branch.match(rev):
    print '<i>(vendor branch)</i>'

  print ', <i>%s UTC</i> (%s ago) by <i>%s</i>' % \
        (time.asctime(time.gmtime(entry.date)),
         html_time(entry.date, 1),
         entry.author)

  if rev2tag.has_key(branch):
    print '<br>Branch: <b>%s</b>' % string.join(rev2tag[branch], ', ')
  if rev2tag.has_key(rev):
    print '<br>CVS Tags: <b>%s</b>' % string.join(rev2tag[rev], ', ')
  if branch_points.has_key(rev):
    print '<br>Branch point for: <b>%s</b>' % \
          string.join(branch_points[rev], ', ')

  prev_rev = string.split(rev, '.')
  while 1:
    if prev_rev[-1] == '0':     # .0 can be caused by 'commit -r X.Y.Z.0'
      prev_rev = prev_rev[:-2]  # X.Y.Z.0 becomes X.Y.Z
    else:
      prev_rev[-1] = str(int(prev_rev[-1]) - 1)
    prev = string.join(prev_rev, '.')
    if rev_map.has_key(prev) or prev == '':
      break
  if prev and entry.changed:
    print '<br>Changes since <b>%s: %s lines</b>' % (prev, entry.changed)

  if entry.state == 'dead':
    print '<br><b><i>FILE REMOVED</i></b>'

  print '<pre>' + htmlify(entry.log) + '</pre>'

def view_log(request):
  full_name = request.full_name
  where = request.where
  query_dict = request.query_dict

  view_tag = query_dict.get('only_with_tag')

  show_revs, rev_map, rev_order, taginfo, rev2tag, \
             cur_branch, branch_points, branch_names = \
             read_log(full_name, None, view_tag, query_dict['logsort'])

  up_where = re.sub(_re_up_path, '', where)

  ### whoops. this sometimes/always? does not have the ",v"
  assert full_name[-2:] != ',v', 'please report this error to viewcvs@lyra.org'
  #filename = os.path.basename(full_name[:-2])  # drop the ",v"
  filename = os.path.basename(full_name)

  ### can we use filename rather than where? need to clarify the two vars
  file_url = urllib.quote(os.path.basename(where))

  ### try: "./" + query + "#" + filename
  back_url = request.script_name + '/' + urllib.quote(up_where) + \
             request.qmark_query + '#' + filename

  data = {
    'where' : where,
    'request' : request,
    'back_url' : back_url,
    'href' : file_url,

    'query' : request.amp_query,
    'qquery' : request.qmark_query,

    ### in the future, it might be nice to break this path up into
    ### a list of elements, allowing the template to display it in
    ### a variety of schemes.
    ### maybe use drop_leaf here?
    'nav_path' : clickable_path(request, up_where, 1, 0, 0),

    'branch' : None,
    'mime_type' : request.mime_type,
    'view_tag' : view_tag,
    'entries' : show_revs,   ### rename the show_rev local to entries?
    'rev_selected' : query_dict.get('r1'),
    'diff_format' : query_dict['diff_format'],
    'logsort' : query_dict['logsort'],

    'address' : cfg.general.address,
    'vsn' : __version__,
    }

  if cfg.options.use_cvsgraph:
    data['graph_href'] = file_url + '?graph=1' + request.amp_query
  else:
    data['graph_href'] = None

  if request.default_viewable:
    data['viewable'] = 'yes'
  else:
    data['viewable'] = None

  if query_dict['diff_format'] == 'h' or query_dict['diff_format'] == 'l':
    data['human_readable'] = 'yes'
  else:
    data['human_readable'] = None

  if cur_branch:
    ### note: we really shouldn't have more than one tag in here. a "default
    ### branch" implies singular :-)  However, if a vendor branch is created
    ### and no further changes are made (e.g. the HEAD is 1.1.1.1), then we
    ### end up seeing the branch point tag and MAIN in this list.
    ### FUTURE: fix all the branch point logic in ViewCVS and get this right.
    data['branch'] = string.join(rev2tag.get(cur_branch, [ cur_branch ]), ', ')

    ### I don't like this URL construction stuff. not obvious enough (how
    ### it keys off the mime_type to do different things). also, the value
    ### for head_abs_href vs head_href is a bit bogus: why decide to
    ### include/exclude the mime type from the URL? should just always be
    ### the same, right?
    if request.default_viewable:
      data['head_href'] = download_url(request, file_url, 'HEAD',
                                       viewcvs_mime_type)
      data['head_abs_href'] = download_url(request, file_url, 'HEAD',
                                           request.mime_type)
    else:
      data['head_href'] = download_url(request, file_url, 'HEAD', None)

  for entry in show_revs:
    # augment the entry with (extended=1) info.
    augment_entry(entry, request, file_url, rev_map, rev2tag, branch_points,
                  rev_order, 1)

  tagitems = taginfo.items()
  tagitems.sort()
  tagitems.reverse()

  data['tags'] = tags = [ ]
  for tag, rev in tagitems:
    tags.append(_item(rev=rev, name=tag))

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

  ### would be nice to find a way to use [query] or somesuch instead
  hidden_values = ''
  for varname in _sticky_vars:
    if varname != 'only_with_tag' and varname != 'logsort':
      value = query_dict.get(varname, '')
      if value != '' and value != default_settings.get(varname):
        hidden_values = hidden_values + \
                        '<input type=hidden name="%s" value="%s">' % \
                        (varname, value)
  data['hidden_values'] = hidden_values

  branch_names.sort()
  branch_names.reverse()
  data['branch_names'] = branch_names

  template = ezt.Template()
  template.parse_file(os.path.join(g_template_dir, cfg.templates.log))

  http_header()

  # generate the page
  template.generate(sys.stdout, data)

### suck up other warnings in _re_co_warning?
_re_co_filename = re.compile(r'^(.*),v\s+-->\s+standard output\s*\n$')
_re_co_warning = re.compile(r'^.*co: .*,v: warning: Unknown phrases like .*\n$')
_re_co_revision = re.compile(r'^revision\s+([\d\.]+)\s*\n$')
def view_checkout(request):
  full_name = request.full_name
  where = request.where
  query_dict = request.query_dict

  rev = query_dict.get('rev')

  ### validate the revision?

  if not rev or rev == 'HEAD':
    rev_flag = '-p'
  else:
    rev_flag = '-p' + rev

  mime_type = query_dict.get('content-type')
  if mime_type:
    ### validate it?
    pass
  else:
    mime_type = request.mime_type

  fp = popen.popen(cfg.general.rcs_path + 'co', (rev_flag, full_name), 'r')

  # header from co:
  #
  #/home/cvsroot/mod_dav/dav_shared_stub.c,v  -->  standard output
  #revision 1.1
  #
  # Sometimes, the following line might occur at line 2:
  #co: INSTALL,v: warning: Unknown phrases like `permissions ...;' are present.

  # parse the output header
  filename = revision = None

  line = fp.readline()
  if not line:
    error('Missing output from co.<br>'
          'fname="%s". url="%s"' % (filename, where))

  match = _re_co_filename.match(line)
  if not match:
    error('First line of co output is not the filename.<br>'
          'Line was: %s<br>'
          'fname="%s". url="%s"' % (line, filename, where))
  filename = match.group(1)

  line = fp.readline()
  if not line:
    error('Missing second line of output from co.<br>'
          'fname="%s". url="%s"' % (filename, where))
  match = _re_co_revision.match(line)
  if not match:
    match = _re_co_warning.match(line)
    if not match:
      error('Second line of co output is not the revision.<br>'
            'Line was: %s<br>'
            'fname="%s". url="%s"' % (line, filename, where))

    # second line was a warning. ignore it and move along.
    line = fp.readline()
    if not line:
      error('Missing third line of output from co (after a warning).<br>'
            'fname="%s". url="%s"' % (filename, where))
    match = _re_co_revision.match(line)
    if not match:
      error('Third line of co output is not the revision.<br>'
            'Line was: %s<br>'
            'fname="%s". url="%s"' % (line, filename, where))

  # one of the above cases matches the revision. grab it.
  revision = match.group(1)

  if filename != full_name:
    error('The filename from co did not match. Found "%s". Wanted "%s"<br>'
          'url="%s"' % (filename, full_name, where))

  if mime_type == viewcvs_mime_type:
    # use the "real" MIME type
    markup_stream(request, fp, revision, request.mime_type)
  else:
    http_header(mime_type)
    while 1:
      chunk = fp.read(8192)
      if not chunk:
        break
      sys.stdout.write(chunk)

def view_annotate(request):
  rev = request.query_dict['annotate']

  pathname, filename = os.path.split(request.where)
  if pathname[-6:] == '/Attic':
    pathname = pathname[:-6]

  http_header()
  navigate_header(request, request.url, pathname, filename, rev, 'view')
  print '<hr noshade>'

  import blame
  blame.make_html(request.cvsroot, request.where + ',v', rev,
                  sticky_query(request.query_dict))

  html_footer()


def cvsgraph_image(cfg, request):
  "output the image rendered by cvsgraph"
  # this function is derived from cgi/cvsgraphmkimg.cgi
  http_header('image/png')
  fp = popen.popen(cfg.options.cvsgraph_path + 'cvsgraph',
                               ("-c", cfg.options.cvsgraph_conf,
                                "-r", request.cvsroot,
                                request.where + ',v'), 'r')
  copy_stream(fp)
  fp.close()

def view_cvsgraph(cfg, request):
  "output a page containing an image rendered by cvsgraph"
  # this function is derived from cgi/cvsgraphwrapper.cgi
  rev = request.query_dict['graph']
  where = request.where

  pathname, filename = os.path.split(where)
  if pathname[-6:] == '/Attic':
    pathname = pathname[:-6]

  http_header()
  # FIXME: use navigate_header(request, request.url, pathname, filename, rev, 'view')
  # FIXME: Move this into a template ?
  print """<html>
<head>
  <title>Revision graph of %(where)s</title>
        <meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
        <meta name="generator" content="handcrafted">
</head>
<body bgcolor="#f0f0f0">
  <center>
  <h1>Revision graph of %(where)s</h1>""" % locals()
  # Required only if cvsgraph needs to find it's supporting libraries.
  # Uncomment and set accordingly if required.
  #os.environ['LD_LIBRARY_PATH'] = '/usr/lib:/usr/local/lib'

  # Create an image map
  fp = popen.popen(cfg.options.cvsgraph_path + 'cvsgraph',
                   ("-i",
                    "-c", cfg.options.cvsgraph_conf,
                    "-r", request.cvsroot,
                    request.where + ',v'), 'r')
  copy_stream(fp)
  fp.close()
  print """<img border="0" 
              usemap="#MyMapName" 
              src="%s?graph=%s&makeimage=1%s" 
              alt="Revisions of %s">""" % (request.url, 
                                           rev, request.amp_query, where)
  print '</center>'
  html_footer()


def view_helppage(request):
  """serve ViewCVS help pages locally.  Using this avoids the need for 
  modifying the setup of the web server."""
  help_page = request.where
  # FIXME: The following is an ugly hack.  It depends on knowledge about what
  # happens in ../cgi/viewcvs.cgi with LIBRARYDIR.  But I dunno how to do this
  # clean here:
  viewcvs_install_directory = os.path.dirname(sys.path[0])
  if CONF_PATHNAME:
    doc_directory = os.path.join(viewcvs_install_directory, "doc")
  else:
    # aid testing from CVS working copy:
    doc_directory = os.path.join(viewcvs_install_directory, "website")
  try:
    fp = open(os.path.join(doc_directory, help_page), "rt")
    if help_page[-3:] == 'png':
      http_header('image/png')
    elif help_page[-3:] == 'jpg':
      http_header('image/jpeg')
    elif help_page[-3:] == 'gif':
      http_header('image/gif')
    else: # assume HTML:
      http_header()
    copy_stream(fp)
    fp.close()
  except IOError, v:
    error('help file "%s" not available\n(%s)' % (help_page, str(v)), 
          '404 Not Found')

   
_re_extract_rev = re.compile(r'^[-+]+ [^\t]+\t([^\t]+)\t((\d+\.)+\d+)$')
_re_extract_info = re.compile(r'@@ \-([0-9]+).*\+([0-9]+).*@@(.*)')
_re_extract_diff = re.compile(r'^([-+ ])(.*)')
def human_readable_diff(request, fp, rev1, rev2, sym1, sym2):
  query_dict = request.query_dict

  where_nd = request.where[:-5] # remove the ".diff"
  pathname, filename = os.path.split(where_nd)

  navigate_header(request, request.script_name + '/' + where_nd, pathname,
                  filename, rev2, 'diff')

  log_rev1 = log_rev2 = None
  date1 = date2 = ''
  r1r = r2r = ''
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
        date1 = ', ' + match.group(1)
        log_rev1 = match.group(2)
    elif line[:4] == '+++ ':
      match = _re_extract_rev.match(line)
      if match:
        date2 = ', ' + match.group(1)
        log_rev2 = match.group(2)
      break

  if (log_rev1 and log_rev1 != rev1) or (log_rev2 and log_rev2 != rev2):
    print '<strong>ERROR:</strong> rcsdiff did not return the correct'
    print 'version number in its output.'
    print '(got "%s" / "%s", expected "%s" / "%s")' % \
          (log_rev1, log_rev2, rev1, rev2)
    print '<p>Aborting operation.'
    sys.exit(0)

  print '<h3 align=center>Diff for /%s between version %s and %s</h3>' % \
        (where_nd, rev1, rev2)
  print '<table border=0 cellspacing=0 cellpadding=0 width="100&#37;">'
  print '<tr bgcolor=white>'
  print '<th width="50&#37;" valign=top>'
  print 'version %s%s' % (rev1, date1)
  if sym1:
    print '<br>Tag:', sym1
  print '</th>'
  print '<th width="50&#37;" valign=top>'
  print 'version %s%s' % (rev2, date2)
  if sym2:
    print '<br>Tag:', sym2
  print '</th></tr>'

  fs = '<font face="%s" size="%s">' % \
       (cfg.options.diff_font_face, cfg.options.diff_font_size)
  left_row = right_row = 0

  # this will be set to true if any changes are found
  changes_seen = 0

  while 1:
    line = fp.readline()
    if not line:
      break

    # we've seen some kind of change
    changes_seen = 1

    if line[:2] == '@@':
      match = _re_extract_info.match(line)
      print '<tr bgcolor="%s"><td width="50&#37;">' % cfg.colors.diff_heading
      print '<table width="100&#37;" border=1 cellpadding=5><tr>'
      print '<td><b>Line %s</b>&nbsp;<font size="-1">%s</font></td>' % \
            (match.group(1), match.group(3))
      print '</tr></table></td><td width="50&#37;">'
      print '<table width="100&#37;" border=1 cellpadding=5><tr>'
      print '<td><b>Line %s</b>&nbsp;<font size="-1">%s</font></td>' % \
            (match.group(2), match.group(3))
      print '</tr></table></td></tr>'

      state = 'dump'
      left_col = [ ]
      right_col = [ ]
    elif line[0] == '\\':
      # \ No newline at end of file
      flush_diff_rows(state, left_col, right_col)
      left_col = [ ]
      right_col = [ ]
    else:
      match = _re_extract_diff.match(line)
      line = spaced_html_text(match.group(2))

      # add font stuff
      line = '<tt>' + fs + '&nbsp;' + line + '</font>' + '</tt>' 

      diff_code = match.group(1)
      if diff_code == '+':
        if state == 'dump':
          print '<tr><td bgcolor="%s">&nbsp;</td>' \
                '<td bgcolor="%s">%s</td></tr>' % \
                (cfg.colors.diff_empty, cfg.colors.diff_add, line)
        else:
          state = 'pre-change-add'
          right_col.append(line)
      elif diff_code == '-':
        state = 'pre-change-remove'
        left_col.append(line)
      else:
        flush_diff_rows(state, left_col, right_col)
        print '<tr><td>%s</td><td>%s</td></tr>' % (line, line)
        state = 'dump'
        left_col = [ ]
        right_col = [ ]

  if changes_seen:
    flush_diff_rows(state, left_col, right_col)
  else:
    print '<tr><td colspan=2>&nbsp;</td></tr>'
    print '<tr bgcolor="%s"><td colspan=2 align=center><br><b>- No changes -</b><br>&nbsp;</td></tr>' % (cfg.colors.diff_empty)

  print '</table><br><hr noshade width="100&#37;">'
  print '<table border=0 cellpadding=10><tr><td>'

  # print the legend
  print '<table border=1><tr><td>Legend:<br>'
  print '<table border=0 cellspacing=0 cellpadding=1>'
  print '<tr><td align=center bgcolor="%s">Removed from v.%s</td><td bgcolor="%s">&nbsp;</td></tr>' % (cfg.colors.diff_remove, rev1, cfg.colors.diff_empty)
  print '<tr bgcolor="%s"><td align=center colspan=2>changed lines</td></tr>' % cfg.colors.diff_change
  print '<tr><td bgcolor="%s">&nbsp;</td><td align=center bgcolor="%s">Added in v.%s</td></tr>' % (cfg.colors.diff_empty, cfg.colors.diff_add, rev2)
  print '</table></td></tr></table></td>'

  # format selector
  print '<td><form method="GET" action="%s">' % request.url
  for varname, value in query_dict.items():
    if varname != 'diff_format' and value != default_settings.get(varname):
      print '<input type=hidden name="%s" value="%s">' % \
            (varname, cgi.escape(value))
  print_diff_select(query_dict)
  print '<input type=submit value="Show"></form></td></tr>'
  print '</table>'
  html_footer()


def flush_diff_rows(state, left_col, right_col):
  if state == 'pre-change-remove':
    for row in left_col:
      print '<tr><td bgcolor="%s">%s</td><td bgcolor="%s">&nbsp;</td></tr>' % \
            (cfg.colors.diff_remove, row, cfg.colors.diff_empty)
  elif state == 'pre-change-add':
    for i in range(max(len(left_col), len(right_col))):
      if i < len(left_col):
        left = '<td bgcolor="%s">%s</td>' % (cfg.colors.diff_change, left_col[i])
      else:
        left = '<td bgcolor="%s">&nbsp;</td>' % cfg.colors.diff_dark_change
      if i < len(right_col):
        right = '<td bgcolor="%s">%s</td>' % (cfg.colors.diff_change, right_col[i])
      else:
        right = '<td bgcolor="%s">&nbsp;</td>' % cfg.colors.diff_dark_change
      print '<tr>%s%s</tr>' % (left, right)

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

def view_diff(request, cvs_filename):
  query_dict = request.query_dict
  cvsroot = request.cvsroot

  r1 = query_dict['r1']
  r2 = query_dict['r2']

  sym1 = sym2 = ''

  if r1 == 'text':
    rev1 = query_dict['tr1']
  else:
    idx = string.find(r1, ':')
    if idx == -1:
      rev1 = r1
    else:
      rev1 = r1[:idx]
      sym1 = r1[idx+1:]

  if r2 == 'text':
    rev2 = query_dict['tr2']
    sym2 = ''
  else:
    idx = string.find(r2, ':')
    if idx == -1:
      rev2 = r2
    else:
      rev2 = r2[:idx]
      sym2 = r2[idx+1:]

  if revcmp(rev1, rev2) > 0:
    rev1, rev2 = rev2, rev1
    sym1, sym2 = sym2, sym1

  human_readable = 0
  unified = 0

  args = [ ]

  format = query_dict['diff_format']
  if format == 'c':
    args.append('-c')
    diff_name = 'Context diff'
  elif format == 's':
    args.append('--side-by-side')
    args.append('--width=164')
    diff_name = 'Side by Side'
  elif format == 'l':
    args.append('--unified=15')
    diff_name = 'Long Human readable'
    human_readable = 1
    unified = 1
  elif format == 'h':
    args.append('-u')
    diff_name = 'Human readable'
    human_readable = 1
    unified = 1
  elif format == 'u':
    args.append('-u')
    diff_name = 'Unidiff'
    unified = 1
  else:
    error('Diff format %s not understood' % format, '400 Bad arguments')

  if human_readable:
    if cfg.options.hr_funout:
      args.append('-p')
    if cfg.options.hr_ignore_white:
      args.append('-w')
    if cfg.options.hr_ignore_keyword_subst:
      args.append('-kk')

  args[len(args):] = ['-r' + rev1, '-r' + rev2, cvs_filename]
  fp = popen.popen(cfg.general.rcs_path + 'rcsdiff', args, 'r')

  if human_readable:
    http_header()
    human_readable_diff(request, fp, rev1, rev2, sym1, sym2)
    sys.exit(0)

  http_header('text/plain')

  if unified:
    f1 = '--- ' + cvsroot
    f2 = '+++ ' + cvsroot
  else:
    f1 = '*** ' + cvsroot
    f2 = '--- ' + cvsroot

  while 1:
    line = fp.readline()
    if not line:
      break

    if line[:len(f1)] == f1:
      line = string.replace(line, cvsroot + '/', '')
      if sym1:
        line = line[:-1] + ' %s\n' % sym1
    elif line[:len(f2)] == f2:
      line = string.replace(line, cvsroot + '/', '')
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

def generate_tarball(out, relative, directory, tag, stack=[]):
  subdirs = [ ]
  rcs_files = [ ]
  for file, pathname, isdir in get_file_data(directory):
    if pathname == _UNREADABLE_MARKER:
      continue
    if isdir:
      subdirs.append(file)
    else:
      rcs_files.append(file)
  if tag and 'Attic' in subdirs:
    for file, pathname, isdir in get_file_data(directory + '/Attic'):
      if not isdir and pathname != _UNREADABLE_MARKER:
        rcs_files.append('Attic/' + file)

  stack.append(relative + '/')

  fileinfo, alltags = get_logs(directory, rcs_files, tag)

  files = fileinfo.keys()
  files.sort(lambda a, b: cmp(os.path.basename(a), os.path.basename(b)))

  for file in files:
    info = fileinfo.get(file)
    rev = info[0]
    date = info[1]
    filename = info[4]
    state = info[5]
    if state == 'dead':
      continue

    for dir in stack:
      generate_tarball_header(out, dir)
    del stack[0:]

    info = os.stat(directory + '/' + file + ',v')
    mode = (info[stat.ST_MODE] & 0555) | 0200

    rev_flag = '-p' + rev
    full_name = directory + '/' + file + ',v'
    fp = popen.popen(cfg.general.rcs_path + 'co', (rev_flag, full_name), 'r', 0)
    contents = fp.read()
    status = fp.close()

    generate_tarball_header(out, relative + '/' + os.path.basename(filename), len(contents), mode, date)
    out.write(contents)
    out.write('\0' * (511 - ((len(contents) + 511) % 512)))

  subdirs.sort()
  for subdir in subdirs:
    if subdir != 'Attic':
      generate_tarball(out, relative + '/' + subdir, directory + '/' + subdir, tag, stack)

  if len(stack):
    del stack[-1:]

def download_tarball(request):
  query_dict = request.query_dict
  full_name = request.full_name

  directory = re.sub(_re_up_path, '', full_name)[0:-1]
  filename = os.path.basename(full_name)

  tag = query_dict.get('only_with_tag')

  http_header('application/octet-stream')
  fp = popen.pipe_cmds([('gzip', '-c', '-n')])
  generate_tarball(fp, os.path.basename(directory), directory, tag)
  fp.write('\0' * 1024)
  fp.close()

def handle_config():
  global cfg
  cfg = config.Config()
  cfg.set_defaults()

  # load in configuration information from the config file
  pathname = CONF_PATHNAME or 'viewcvs.conf'
  cfg.load_config(pathname, os.environ.get('HTTP_HOST'))

  global default_settings
  default_settings = {
    "sortby" : cfg.options.sort_by,
    "hideattic" : cfg.options.hide_attic,
    "logsort" : cfg.options.log_sort,
    "diff_format" : cfg.options.diff_format,
    "hidecvsroot" : cfg.options.hide_cvsroot,
    "hidenonreadable" : cfg.options.hide_non_readable,
    }


def main():
  # handle the configuration stuff
  handle_config()

  # build a Request object, which contains info about the HTTP request
  request = Request()

  # is the CVS root really there?
  if not os.path.isdir(request.cvsroot):
    error('%s not found!\nThe server on which the CVS tree lives is '
          'probably down. Please try again in a few minutes.' %
          request.cvsroot)

  full_name = request.full_name
  isdir = os.path.isdir(full_name)

  url = request.url
  where = request.where

  ### look for GZIP binary

  # if we have a directory and the request didn't end in "/", then redirect
  # so that it does. (so that relative URLs in our output work right)
  if isdir and os.environ.get('PATH_INFO', '')[-1:] != '/':
    redirect(url + '/' + request.qmark_query)

  # check the forbidden list
  if cfg.is_forbidden(request.module):
    error('Access to "%s" is forbidden.' % request.module, '403 Forbidden')

  if isdir:
    view_directory(request)
    return

  # since we aren't talking about a directory, set up the mime type info
  # for the file.
  request.setup_mime_type_info()

  query_dict = request.query_dict

  if os.path.isfile(full_name + ',v'):
    if query_dict.has_key('rev') or request.has_checkout_magic:
      view_checkout(request)
    elif query_dict.has_key('annotate') and cfg.options.allow_annotate:
      view_annotate(request)
    elif query_dict.has_key('r1') and query_dict.has_key('r2'):
      view_diff(request, full_name)
    elif query_dict.has_key('graph') and cfg.options.use_cvsgraph:
      if not query_dict.has_key('makeimage'):
        view_cvsgraph(cfg, request)
      else: 
        cvsgraph_image(cfg, request)
    else:
      view_log(request)
  elif full_name[-5:] == '.diff' and os.path.isfile(full_name[:-5] + ',v') \
       and query_dict.has_key('r1') and query_dict.has_key('r2'):
    view_diff(request, full_name[:-5])
  elif cfg.options.allow_tar \
       and full_name[-7:] == '.tar.gz' and query_dict.has_key('tarball'):
    download_tarball(request)
  elif request.has_helppage_magic:
    view_helppage(request)
  else:
    # if the file is in the Attic, then redirect
    idx = string.rfind(full_name, '/')
    attic_name = full_name[:idx] + '/Attic' + full_name[idx:] + ',v'
    if os.path.isfile(attic_name):
      idx = string.rfind(url, '/')
      redirect(url[:idx] + '/Attic' + url[idx:])

    error('%s: unknown location' % request.url, '404 Not Found')


def run_cgi():
  try:
    main()
  except SystemExit, e:
    # don't catch SystemExit (caused by sys.exit()). propagate the exit code
    sys.exit(e[0])
  except:
    info = sys.exc_info()
    http_header()
    print '<html><head><title>Python Exception Occurred</title></head>'
    print '<body bgcolor=white><h1>Python Exception Occurred</h1>'
    import traceback
    lines = apply(traceback.format_exception, info)
    print '<pre>'
    print cgi.escape(string.join(lines, ''))
    print '</pre>'
    html_footer()


class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
