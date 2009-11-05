# -*-python-*-
#
# Copyright (C) 1999-2009 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# config.py: configuration utilities
#
# -----------------------------------------------------------------------

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
#       1) edit the viewvc.conf created by the viewvc-install(er)
#       2) as (1), but delete all unchanged entries from viewvc.conf
#       3) do not use viewvc.conf and just edit the defaults in this file
#
# Most users will want to use (1), but there are slight speed advantages
# to the other two options. Note that viewvc.conf values are a bit easier
# to work with since it is raw text, rather than python literal values.
#
#########################################################################

class Config:
  _sections = ('general', 'utilities', 'options', 'cvsdb', 'templates')
  _force_multi_value = ('cvs_roots', 'svn_roots', 'languages', 'kv_files',
                        'root_parents', 'allowed_views', 'mime_types_files')

  def __init__(self):
    for section in self._sections:
      setattr(self, section, _sub_config())

  def load_config(self, pathname, vhost=None, rootname=None):
    self.conf_path = os.path.isfile(pathname) and pathname or None
    self.base = os.path.dirname(pathname)
    self.parser = ConfigParser.ConfigParser()
    self.parser.read(self.conf_path or [])

    for section in self._sections:
      if self.parser.has_section(section):
        self._process_section(self.parser, section, section)

    if vhost and self.parser.has_section('vhosts'):
      self._process_vhost(self.parser, vhost)

    if rootname:
      self._process_root_options(self.parser, rootname)

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

  def path(self, path):
    """Return path relative to the config file directory"""
    return os.path.join(self.base, path)

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

      if opt == 'cvs_roots' or opt == 'svn_roots':
        value = _parse_roots(opt, value)

      setattr(sc, opt, value)

  def _process_vhost(self, parser, vhost):
    # find a vhost name for this vhost, if any (if not, we've nothing to do)
    canon_vhost = self._find_canon_vhost(parser, vhost)
    if not canon_vhost:
      return

    # overlay any option sections associated with this vhost name
    cv = 'vhost-%s/' % (canon_vhost)
    lcv = len(cv)
    for section in parser.sections():
      if section[:lcv] == cv:
        base_section = section[lcv:]
        if base_section not in self._sections:
          raise IllegalOverrideSection('vhost', section)
        self._process_section(parser, section, base_section)

  def _find_canon_vhost(self, parser, vhost):
    vhost = string.split(string.lower(vhost), ':')[0]  # lower-case, no port
    for canon_vhost in parser.options('vhosts'):
      value = parser.get('vhosts', canon_vhost)
      patterns = map(string.lower, map(string.strip,
                                       filter(None, string.split(value, ','))))
      for pat in patterns:
        if fnmatch.fnmatchcase(vhost, pat):
          return canon_vhost

    return None

  def _process_root_options(self, parser, rootname):
    rn = 'root-%s/' % (rootname)
    lrn = len(rn)
    for section in parser.sections():
      if section[:lrn] == rn:
        base_section = section[lrn:]
        if base_section in self._sections:
          if base_section == 'general':
            raise IllegalOverrideSection('root', section)
          self._process_section(parser, section, base_section)
        elif _startswith(base_section, 'authz-'):
          pass
        else:
          raise IllegalOverrideSection('root', section)
          
  def overlay_root_options(self, rootname):
    "Overly per-root options atop the existing option set."
    if not self.conf_path:
      return
    self._process_root_options(self.parser, rootname)

  def _get_parser_items(self, parser, section):
    """Basically implement ConfigParser.items() for pre-Python-2.3 versions."""
    try:
      return self.parser.items(section)
    except AttributeError:
      d = {}
      for option in parser.options(section):
        d[option] = parser.get(section, option)
      return d.items()
    
  def get_authorizer_params(self, authorizer, rootname=None):
    if not self.conf_path:
      return {}

    params = {}
    authz_section = 'authz-%s' % (authorizer)
    for section in self.parser.sections():
      if section == authz_section:
        for key, value in self._get_parser_items(self.parser, section):
          params[key] = value
    if rootname:
      root_authz_section = 'root-%s/authz-%s' % (rootname, authorizer)
      for section in self.parser.sections():
        if section == root_authz_section:
          for key, value in self._get_parser_items(self.parser, section):
            params[key] = value
    return params
  
  def set_defaults(self):
    "Set some default values in the configuration."

    self.general.cvs_roots = { }
    self.general.svn_roots = { }
    self.general.root_parents = []
    self.general.default_root = ''
    self.general.mime_types_files = ["mimetypes.conf"]
    self.general.address = ''
    self.general.kv_files = [ ]
    self.general.languages = ['en-us']

    self.utilities.rcs_dir = ''
    if sys.platform == "win32":
      self.utilities.cvsnt = 'cvs'
    else:
      self.utilities.cvsnt = None
    self.utilities.svn = ''
    self.utilities.diff = ''
    self.utilities.cvsgraph = ''

    self.options.root_as_url_component = 1
    self.options.checkout_magic = 0
    self.options.allowed_views = ['annotate', 'diff', 'markup', 'roots']
    self.options.authorizer = None
    self.options.mangle_email_addresses = 0
    self.options.default_file_view = "log"
    self.options.http_expiration_time = 600
    self.options.generate_etags = 1
    self.options.svn_ignore_mimetype = 0
    self.options.svn_config_dir = None
    self.options.use_rcsparse = 0
    self.options.sort_by = 'file'
    self.options.sort_group_dirs = 1
    self.options.hide_attic = 1
    self.options.hide_errorful_entries = 0
    self.options.log_sort = 'date'
    self.options.diff_format = 'h'
    self.options.hide_cvsroot = 1
    self.options.hr_breakable = 1
    self.options.hr_funout = 1
    self.options.hr_ignore_white = 0
    self.options.hr_ignore_keyword_subst = 1
    self.options.hr_intraline = 0
    self.options.allow_compress = 0
    self.options.template_dir = "templates"
    self.options.docroot = None
    self.options.show_subdir_lastmod = 0
    self.options.show_logs = 1
    self.options.show_log_in_markup = 1
    self.options.cross_copies = 1
    self.options.use_localtime = 0
    self.options.short_log_len = 80
    self.options.enable_syntax_coloration = 1
    self.options.tabsize = 8
    self.options.detect_encoding = 0
    self.options.use_cvsgraph = 0
    self.options.cvsgraph_conf = "cvsgraph.conf"
    self.options.use_re_search = 0
    self.options.dir_pagesize = 0
    self.options.log_pagesize = 0
    self.options.limit_changes = 100

    self.templates.diff = None
    self.templates.directory = None
    self.templates.error = None
    self.templates.file = None
    self.templates.graph = None
    self.templates.log = None
    self.templates.query = None
    self.templates.query_form = None
    self.templates.query_results = None
    self.templates.roots = None

    self.cvsdb.enabled = 0
    self.cvsdb.host = ''
    self.cvsdb.port = 3306
    self.cvsdb.database_name = ''
    self.cvsdb.user = ''
    self.cvsdb.passwd = ''
    self.cvsdb.readonly_user = ''
    self.cvsdb.readonly_passwd = '' 
    self.cvsdb.row_limit = 1000
    self.cvsdb.rss_row_limit = 100
    self.cvsdb.check_database_for_root = 0

def _startswith(somestr, substr):
  return somestr[:len(substr)] == substr

def _parse_roots(config_name, config_value):
  roots = { }
  for root in config_value:
    pos = string.find(root, ':')
    if pos < 0:
      raise MalformedRoot(config_name, root)
    name, path = map(string.strip, (root[:pos], root[pos+1:]))
    roots[name] = path
  return roots

class ViewVCConfigurationError(Exception):
  pass

class IllegalOverrideSection(ViewVCConfigurationError):
  def __init__(self, override_type, section_name):
    self.section_name = section_name
    self.override_type = override_type
  def __str__(self):
    return "malformed configuration: illegal %s override section: %s" \
           % (self.override_type, self.section_name)
  
class MalformedRoot(ViewVCConfigurationError):
  def __init__(self, config_name, value_given):
    Exception.__init__(self, config_name, value_given)
    self.config_name = config_name
    self.value_given = value_given
  def __str__(self):
    return "malformed configuration: '%s' uses invalid syntax: %s" \
           % (self.config_name, self.value_given)


class _sub_config:
  pass

if not hasattr(sys, 'hexversion'):
  # Python 1.5 or 1.5.1. fix the syntax for ConfigParser options.
  import regex
  ConfigParser.option_cre = regex.compile('^\([-A-Za-z0-9._]+\)\(:\|['
                                          + string.whitespace
                                          + ']*=\)\(.*\)$')
