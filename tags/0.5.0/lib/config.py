# -*- Mode: python -*-
#
# Copyright (C) 2000 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://www.lyra.org/viewcvs/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://www.lyra.org/viewcvs/
#
# -----------------------------------------------------------------------
#
# config.py: configuration utilities
#
# -----------------------------------------------------------------------
#

import sys
import os
import string
import ConfigParser
import fnmatch


#########################################################################
#
# CONFIGURATION
#
# There are three forms of configuration:
#
#       1) copy viewcvs.conf.dist to viewcvs.conf and edit
#       2) as (1), but delete all unchanged entries from viewcvs.conf
#       3) do not use viewcvs.conf and just edit the defaults in this file
#
# Most users will want to use (1), but there are slight speed advantages
# to the other two options. Note that viewcvs.conf values are a bit easier
# to work with since it is raw text, rather than python literal values.
#
#########################################################################

class Config:
  _sections = ('general', 'images', 'options', 'colors', 'text', 'cvsdb')
  _force_multi_value = ('cvs_roots', 'forbidden', 'even_odd',
                        'disable_enscript_lang')

  def __init__(self):
    for section in self._sections:
      setattr(self, section, _sub_config())

  def load_config(self, fname, vhost=None):
    this_dir = os.path.dirname(sys.argv[0])
    pathname = os.path.join(this_dir, fname)
    parser = ConfigParser.ConfigParser()
    parser.read(pathname)

    for section in self._sections:
      if parser.has_section(section):
        self._process_section(parser, section, section)

    if vhost:
      self._process_vhost(parser, vhost)

  def _process_section(self, parser, section, subcfg_name):
    sc = getattr(self, subcfg_name)

    for opt in parser.options(section):
      value = parser.get(section, opt)
      if opt in self._force_multi_value or subcfg_name == 'images':
        value = map(string.strip, filter(None, string.split(value, ',')))
      else:
        try:
          value = int(value)
        except ValueError:
          pass

      if opt == 'cvs_roots':
        roots = { }
        for root in value:
          name, path = map(string.strip, string.split(root, ':'))
          roots[name] = path
        value = roots
      setattr(sc, opt, value)

  def _process_vhost(self, parser, vhost):
    canon_vhost = self._find_canon_vhost(parser, vhost)
    if not canon_vhost:
      # none of the vhost sections matched
      return

    cv = canon_vhost + '-'
    lcv = len(cv)
    for section in parser.sections():
      if section[:lcv] == cv:
        self._process_section(parser, section, section[lcv:])

  def _find_canon_vhost(self, parser, vhost):
    vhost = string.lower(vhost)

    for canon_vhost in parser.options('vhosts'):
      value = parser.get('vhosts', canon_vhost)
      patterns = map(string.lower, map(string.strip,
                                       filter(None, string.split(value, ','))))
      for pat in patterns:
        if fnmatch.fnmatchcase(vhost, pat):
          return canon_vhost

    return None

  def set_defaults(self):
    "Set some default values in the configuration."

    self.general.cvs_roots = {
      # user-visible-name : path
      "Development" : "/home/cvsroot",
      }
    self.general.default_root = "Development"
    self.general.rcs_path = ''
    self.general.mime_types_file = ''
    self.general.address = '<a href="mailto:gstein@lyra.org">gstein@lyra.org</a>'
    self.general.main_title = 'CVS Repository'
    self.general.forbidden = ()

    self.cvsdb.enabled = 0
    self.cvsdb.host = ''
    self.cvsdb.database_name = ''
    self.cvsdb.user = ''
    self.cvsdb.passwd = ''
    self.cvsdb.readonly_user = ''
    self.cvsdb.readonly_passwd = '' 

    self.images.logo = "/icons/apache_pb.gif", 259, 32
    self.images.back_icon = "/icons/small/back.gif", 16, 16
    self.images.dir_icon = "/icons/small/dir.gif",  16, 16
    self.images.file_icon = "/icons/small/text.gif", 16, 16

    self.colors.markup_log = "#ffffff"

    self.colors.diff_heading = "#99cccc"
    self.colors.diff_empty = "#cccccc"
    self.colors.diff_remove = "#ff9999"
    self.colors.diff_change = "#99ff99"
    self.colors.diff_add = "#ccccff"
    self.colors.diff_dark_change = "#99cc99"

    self.colors.even_odd = ("#ccccee", "#ffffff")

    self.colors.nav_header = "#9999ee"

    self.colors.text = "#000000"
    self.colors.background = "#ffffff"
    self.colors.alt_background = "#eeeeee"

    self.colors.column_header_normal = "#cccccc"
    self.colors.column_header_sorted = "#88ff88"

    self.colors.table_border = None	# no border

    self.options.sort_by = 'file'
    self.options.hide_attic = 1
    self.options.log_sort = 'date'
    self.options.diff_format = 'h'
    self.options.hide_cvsroot = 1
    self.options.hide_non_readable = 1
    self.options.show_author = 1
    self.options.hr_breakable = 1
    self.options.hr_funout = 1
    self.options.hr_ignore_white = 1
    self.options.hr_ignore_keyword_subst = 1
    self.options.allow_annotate = 0	### doesn't work yet!
    self.options.allow_markup = 1
    self.options.allow_compress = 1
    self.options.use_java_script = 1
    self.options.open_extern_window = 1
    self.options.extern_window_width = 600
    self.options.extern_window_height = 440
    self.options.checkout_magic = 1
    self.options.show_subdir_lastmod = 0
    self.options.show_logs = 1
    self.options.show_log_in_markup = 1
    self.options.allow_version_select = 1
    self.options.py2html_path = '.'
    self.options.short_log_len = 80
    self.options.table_padding = 2
    self.options.diff_font_face = 'Helvetica,Arial'
    self.options.diff_font_size = -1
    self.options.input_text_size = 12
    self.options.use_enscript = 0
    self.options.enscript_path = ''
    self.options.disable_enscript_lang = ()

    self.text.long_intro = """\
    <p>
    This is a WWW interface for CVS Repositories.
    You can browse the file hierarchy by picking directories
    (which have slashes after them, <i>e.g.</i>, <b>src/</b>).
    If you pick a file, you will see the revision history
    for that file.
    Selecting a revision number will download that revision of
    the file.  There is a link at each revision to display
    diffs between that revision and the previous one, and
    a form at the bottom of the page that allows you to
    display diffs between arbitrary revisions.
    </p>
    <p>
    This script
    (<a href="http://www.lyra.org/viewcvs/">ViewCVS</a>)
    has been written by Greg Stein
    &lt;<a href="mailto:gstein@lyra.org">gstein@lyra.org</a>&gt;
    based on the
    <a href="http://linux.fh-heilbronn.de/~zeller/cgi/cvsweb.cgi">cvsweb</a>
    script by Henner Zeller
    &lt;<a href="mailto:zeller@think.de">zeller@think.de</a>&gt;;
    it is covered by the
    <a href="http://www.opensource.org/licenses/bsd-license.html">BSD-License</a>.
    If you would like to use this CGI script on your own web server and
    CVS tree, see Greg's
    <a href="http://www.lyra.org/viewcvs/">ViewCVS distribution
    site</a>.
    Please send any suggestions, comments, etc. to
    <a href="mailto:gstein@lyra.org">Greg Stein</a>.
    </p>
    """
    # ' stupid emacs...

    self.text.doc_info = """
    <h3>CVS Documentation</h3>
    <blockquote>
    <p>
      <a href="http://www.loria.fr/~molli/cvs/doc/cvs_toc.html">CVS
      User's Guide</a><br>
      <a href="http://www.arc.unm.edu/~rsahu/cvs.html">CVS Tutorial</a><br>
      <a href="http://cellworks.washington.edu/pub/docs/cvs/tutorial/cvs_tutorial_1.html">Another CVS tutorial</a><br>
      <a href="http://www.csc.calpoly.edu/~dbutler/tutorials/winter96/cvs/">Yet another CVS tutorial (a little old, but nice)</a><br>
      <a href="http://www.cs.utah.edu/dept/old/texinfo/cvs/FAQ.txt">An old but very useful FAQ about CVS</a>
    </p>
    </blockquote>
    """

    # Fill in stuff on (say) anonymous pserver access here. For example, what
    # access mechanism, login, path, etc should be used.
    self.text.repository_info = """
    <!-- insert repository access instructions here -->
    """

    self.text.short_intro = """\
    <p>
    Click on a directory to enter that directory. Click on a file to display
    its revision history and to get a chance to display diffs between revisions. 
    </p>
    """

  def is_forbidden(self, module):
    if not module:
      return 0
    default = 0
    for pat in self.general.forbidden:
      if pat[0] == '!':
        default = 1
        if fnmatch.fnmatchcase(module, pat[1:]):
          return 0
      elif fnmatch.fnmatchcase(module, pat):
        return 1
    return default

class _sub_config:
  def get_image(self, which):
    text = '[%s]' % string.upper(which)
    path, width, height = getattr(self, which)
    if path:
      return '<img src="%s" alt="%s" border=0 width=%s height=%s>' % \
             (path, text, width, height)
    return text
