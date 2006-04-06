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
  _sections = ('general', 'options', 'cvsdb', 'templates')
  _force_multi_value = ('cvs_roots', 'forbidden', 'disable_enscript_lang',
                        'languages', 'kv_files')

  def __init__(self):
    for section in self._sections:
      setattr(self, section, _sub_config())

  def load_config(self, fname, vhost=None):
    this_dir = os.path.dirname(sys.argv[0])
    pathname = os.path.join(this_dir, fname)
    self.base = os.path.dirname(pathname)

    parser = ConfigParser.ConfigParser()
    parser.read(pathname)

    for section in self._sections:
      if parser.has_section(section):
        self._process_section(parser, section, section)

    if vhost and parser.has_section('vhosts'):
      self._process_vhost(parser, vhost)

  def load_kv_files(self, language):
    kv = _sub_config()

    for fname in self.general.kv_files:
      if fname[0] == '[':
        idx = string.index(fname, ']')
        parts = string.split(fname[1:idx], '.')
        fname = string.strip(fname[idx+1:])
      else:
        parts = [ ]
      fname = string.replace(fname, '%lang%', language)

      parser = ConfigParser.ConfigParser()
      parser.read(os.path.join(self.base, fname))
      for section in parser.sections():
        for option in parser.options(section):
          full_name = parts + [section]
          ob = kv
          for name in full_name:
            try:
              ob = getattr(ob, name)
            except AttributeError:
              c = _sub_config()
              setattr(ob, name, c)
              ob = c
          setattr(ob, option, parser.get(section, option))

    return kv

  def _process_section(self, parser, section, subcfg_name):
    sc = getattr(self, subcfg_name)

    for opt in parser.options(section):
      value = parser.get(section, opt)
      if opt in self._force_multi_value:
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
    self.general.address = '<a href="mailto:user@insert.your.domain.here">No CVS admin address has been configured</a>'
    self.general.main_title = 'CVS Repository'
    self.general.forbidden = ()
    self.general.kv_files = [ ]
    self.general.languages = ['en-us']

    self.templates.directory = 'templates/directory.ezt'
    self.templates.log = 'templates/log.ezt'
    self.templates.query = 'templates/query.ezt'
    self.templates.footer = 'templates/footer.ezt'
    self.templates.diff = 'templates/diff.ezt'
    self.templates.graph = 'templates/graph.ezt'
    self.templates.annotate = 'templates/annotate.ezt'
    self.templates.markup = 'templates/markup.ezt'

    self.cvsdb.enabled = 0
    self.cvsdb.host = ''
    self.cvsdb.database_name = ''
    self.cvsdb.user = ''
    self.cvsdb.passwd = ''
    self.cvsdb.readonly_user = ''
    self.cvsdb.readonly_passwd = '' 
    self.cvsdb.row_limit = 1000

    self.options.sort_by = 'file'
    self.options.hide_attic = 1
    self.options.log_sort = 'date'
    self.options.diff_format = 'h'
    self.options.hide_cvsroot = 1
    self.options.hr_breakable = 1
    self.options.hr_funout = 1
    self.options.hr_ignore_white = 1
    self.options.hr_ignore_keyword_subst = 1
    self.options.allow_annotate = 1
    self.options.allow_markup = 1
    self.options.allow_compress = 1
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
    self.options.cvsgraph_path = ''
    self.options.cvsgraph_conf = "<VIEWCVS_INSTALL_DIRECTORY>/cvsgraph.conf"
    self.options.use_re_search = 0

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
  pass

if not hasattr(sys, 'hexversion'):
  # Python 1.5 or 1.5.1. fix the syntax for ConfigParser options.
  import regex
  ConfigParser.option_cre = regex.compile('^\([-A-Za-z0-9._]+\)\(:\|['
                                          + string.whitespace
                                          + ']*=\)\(.*\)$')
