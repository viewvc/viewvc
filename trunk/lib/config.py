# -*- Mode: python -*-
#
# Copyright (C) 2000-2001 The ViewCVS Group. All Rights Reserved.
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
#       1) edit the viewcvs.conf created by the viewcvs-install(er)
#       2) as (1), but delete all unchanged entries from viewcvs.conf
#       3) do not use viewcvs.conf and just edit the defaults in this file
#
# Most users will want to use (1), but there are slight speed advantages
# to the other two options. Note that viewcvs.conf values are a bit easier
# to work with since it is raw text, rather than python literal values.
#
#########################################################################

class Config:
  _sections = ('general', 'images', 'options', 'colors', 'cvsdb', 'templates')
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

    if vhost and parser.has_section('vhosts'):
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
    self.general.address = '<a href="mailto:viewcvs@lyra.org">viewcvs@lyra.org</a>'
    self.general.main_title = 'CVS Repository'
    self.general.forbidden = ()

    self.templates.directory = 'templates/directory.ezt'
    self.templates.log = 'templates/log.ezt'

    self.cvsdb.enabled = 0
    self.cvsdb.host = ''
    self.cvsdb.database_name = ''
    self.cvsdb.user = ''
    self.cvsdb.passwd = ''
    self.cvsdb.readonly_user = ''
    self.cvsdb.readonly_passwd = '' 

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
    self.options.allow_annotate = 1
    self.options.allow_markup = 1
    self.options.allow_compress = 1
    self.options.use_java_script = 1
    self.options.open_extern_window = 1
    self.options.checkout_magic = 1
    self.options.show_subdir_lastmod = 0
    self.options.show_logs = 1
    self.options.show_log_in_markup = 1
    self.options.py2html_path = '.'
    self.options.short_log_len = 80
    self.options.diff_font_face = 'Helvetica,Arial'
    self.options.diff_font_size = -1
    self.options.use_enscript = 0
    self.options.enscript_path = ''
    self.options.disable_enscript_lang = ()
    self.options.allow_tar = 0
    self.options.use_cvsgraph = 0

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

if not hasattr(sys, 'hexversion'):
  # Python 1.5 or 1.5.1. fix the syntax for ConfigParser options.
  import regex
  ConfigParser.option_cre = regex.compile('^\([-A-Za-z0-9._]+\)\(:\|['
                                          + string.whitespace
                                          + ']*=\)\(.*\)$')
