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
# -------------
#
# There are three forms of configuration:
#
#    1. edit the viewvc.conf created by the viewvc-install(er)
#    2. as (1), but delete all unchanged entries from viewvc.conf
#    3. do not use viewvc.conf and just edit the defaults in this file
#
# Most users will want to use (1), but there are slight speed advantages
# to the other two options. Note that viewvc.conf values are a bit easier
# to work with since it is raw text, rather than python literal values.
#
#
# A WORD ABOUT OPTION LAYERING/OVERRIDES
# --------------------------------------
#
# ViewVC has three "layers" of configuration options:
#
#    1. base configuration options - very basic configuration bits
#       found in sections like 'general', 'options', etc.
#    2. vhost overrides - these options overlay/override the base
#       configuration on a per-vhost basis.
#    3. root overrides - these options overlay/override the base
#       configuration and vhost overrides on a per-root basis.
#
# Here's a diagram of the valid overlays/overrides:
#
#         PER-ROOT          PER-VHOST            BASE
#       
#                         ,-----------.     ,-----------.
#                         | vhost-*/  |     |           |
#                         |  general  | --> |  general  |
#                         |           |     |           |
#                         `-----------'     `-----------'
#       ,-----------.     ,-----------.     ,-----------.
#       |  root-*/  |     | vhost-*/  |     |           |
#       |  options  | --> |  options  | --> |  options  |
#       |           |     |           |     |           |
#       `-----------'     `-----------'     `-----------'
#       ,-----------.     ,-----------.     ,-----------.
#       |  root-*/  |     | vhost-*/  |     |           |
#       | templates | --> | templates | --> | templates |
#       |           |     |           |     |           |
#       `-----------'     `-----------'     `-----------'
#       ,-----------.     ,-----------.     ,-----------.
#       |  root-*/  |     | vhost-*/  |     |           |
#       | utilities | --> | utilities | --> | utilities |
#       |           |     |           |     |           |
#       `-----------'     `-----------'     `-----------'
#                         ,-----------.     ,-----------.
#                         | vhost-*/  |     |           |
#                         |   cvsdb   | --> |   cvsdb   |
#                         |           |     |           |
#                         `-----------'     `-----------'
#       ,-----------.     ,-----------.     ,-----------.
#       |  root-*/  |     | vhost-*/  |     |           |
#       |  authz-*  | --> |  authz-*  | --> |  authz-*  |
#       |           |     |           |     |           |
#       `-----------'     `-----------'     `-----------'
#                                           ,-----------.
#                                           |           |
#                                           |  vhosts   |
#                                           |           |
#                                           `-----------'
#                                           ,-----------.
#                                           |           |
#                                           |   query   |
#                                           |           |
#                                           `-----------'
#
# ### TODO:  Figure out what this all means for the 'kv' stuff.
#
#########################################################################

class Config:
  _base_sections = (
    # Base configuration sections.
    'authz-*',
    'cvsdb',
    'general',
    'options',
    'query',
    'templates',
    'utilities',
    )
  _force_multi_value = (
    # Configuration values with multiple, comma-separated values.
    'allowed_views',
    'cvs_roots',
    'kv_files',
    'languages',
    'mime_types_files',
    'root_parents',
    'svn_roots',
    )
  _allowed_overrides = {
    # Mapping of override types to allowed overridable sections.
    'vhost' : ('authz-*',
               'cvsdb',
               'general',
               'options',
               'templates',
               'utilities',
               ),
    'root'  : ('authz-*',
               'options',
               'templates',
               'utilities',
               )
    }

  def __init__(self):
    self.root_options_overlayed = 0
    for section in self._base_sections:
      if section[-1] == '*':
        continue
      setattr(self, section, _sub_config())

  def load_config(self, pathname, vhost=None):
    """Load the configuration file at PATHNAME, applying configuration
    settings there as overrides to the built-in default values.  If
    VHOST is provided, also process the configuration overrides
    specific to that virtual host."""
    
    self.conf_path = os.path.isfile(pathname) and pathname or None
    self.base = os.path.dirname(pathname)
    self.parser = ConfigParser.ConfigParser()
    self.parser.optionxform = lambda x: x # don't case-normalize option names.
    self.parser.read(self.conf_path or [])
    
    for section in self.parser.sections():
      if self._is_allowed_section(section, self._base_sections):
        self._process_section(self.parser, section, section)

    if vhost and self.parser.has_section('vhosts'):
      self._process_vhost(self.parser, vhost)

  def load_kv_files(self, language):
    """Process the key/value (kv) files specified in the
    configuration, merging their values into the configuration as
    dotted heirarchical items."""
    
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
      parser.optionxform = lambda x: x # don't case-normalize option names.
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
    """Return PATH relative to the config file directory."""
    return os.path.join(self.base, path)

  def _process_section(self, parser, section, subcfg_name):
    if not hasattr(self, subcfg_name):
      setattr(self, subcfg_name, _sub_config())
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

      ### FIXME: This feels like unnecessary depth of knowledge for a
      ### semi-generic configuration object.
      if opt == 'cvs_roots' or opt == 'svn_roots':
        value = _parse_roots(opt, value)

      setattr(sc, opt, value)

  def _is_allowed_section(self, section, allowed_sections):
    """Return 1 iff SECTION is an allowed section, defined as being
    explicitly present in the ALLOWED_SECTIONS list or present in the
    form 'someprefix-*' in that list."""
    
    for allowed_section in allowed_sections:
      if allowed_section[-1] == '*':
        if _startswith(section, allowed_section[:-1]):
          return 1
      elif allowed_section == section:
        return 1
    return 0

  def _is_allowed_override(self, sectype, secspec, section):
    """Test if SECTION is an allowed override section for sections of
    type SECTYPE ('vhosts' or 'root', currently) and type-specifier
    SECSPEC (a rootname or vhostname, currently).  If it is, return
    the overridden base section name.  If it's not an override section
    at all, return None.  And if it's an override section but not an
    allowed one, raise IllegalOverrideSection."""

    cv = '%s-%s/' % (sectype, secspec)
    lcv = len(cv)
    if section[:lcv] != cv:
      return None
    base_section = section[lcv:]
    if self._is_allowed_section(base_section,
                                self._allowed_overrides[sectype]):
      return base_section
    raise IllegalOverrideSection(sectype, section)

  def _process_vhost(self, parser, vhost):
    # Find a vhost name for this VHOST, if any (else, we've nothing to do).
    canon_vhost = self._find_canon_vhost(parser, vhost)
    if not canon_vhost:
      return

    # Overlay any option sections associated with this vhost name.
    for section in parser.sections():
      base_section = self._is_allowed_override('vhost', canon_vhost, section)
      if base_section:
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

  def overlay_root_options(self, rootname):
    """Overlay per-root options for ROOTNAME atop the existing option
    set.  This is a destructive change to the configuration."""

    did_overlay = 0
    
    if not self.conf_path:
      return

    for section in self.parser.sections():
      base_section = self._is_allowed_override('root', rootname, section)
      if base_section:
        # We can currently only deal with root overlays happening
        # once, so check that we've not yet done any overlaying of
        # per-root options.
        assert(self.root_options_overlayed == 0)
        self._process_section(self.parser, section, base_section)
        did_overlay = 1

    # If we actually did any overlaying, remember this fact so we
    # don't do it again later.
    if did_overlay:
      self.root_options_overlayed = 1

  def _get_parser_items(self, parser, section):
    """Basically implement ConfigParser.items() for pre-Python-2.3 versions."""
    try:
      return self.parser.items(section)
    except AttributeError:
      d = {}
      for option in parser.options(section):
        d[option] = parser.get(section, option)
      return d.items()

  def get_authorizer_and_params_hack(self, rootname):
    """Return a 2-tuple containing the name and parameters of the
    authorizer configured for use with ROOTNAME.

    ### FIXME: This whole thing is a hack caused by our not being able
    ### to non-destructively overlay root options when trying to do
    ### something like a root listing (which might need to get
    ### different authorizer bits for each and every root in the list).
    ### Until we have a good way to do that, we expose this function,
    ### which assumes that base and per-vhost configuration has been
    ### absorbed into this object and that per-root options have *not*
    ### been overlayed.  See issue #371."""

    # We assume that per-root options have *not* been overlayed.
    assert(self.root_options_overlayed == 0)

    if not self.conf_path:
      return None, {}

    # Figure out the authorizer by searching first for a per-root
    # override, then falling back to the base/vhost configuration.
    authorizer = None
    root_options_section = 'root-%s/options' % (rootname)
    if self.parser.has_section(root_options_section) \
       and self.parser.has_option(root_options_section, 'authorizer'):
      authorizer = self.parser.get(root_options_section, 'authorizer')
    if not authorizer:
      authorizer = self.options.authorizer

    # No authorizer?  Get outta here.
    if not authorizer:
      return None, {}

    # Dig up the parameters for the authorizer, starting with the
    # base/vhost items, then overlaying any root-specific ones we find.
    params = {}
    authz_section = 'authz-%s' % (authorizer)
    if hasattr(self, authz_section):
      sub_config = getattr(self, authz_section)
      for attr in dir(sub_config):
        params[attr] = getattr(sub_config, attr)
    root_authz_section = 'root-%s/authz-%s' % (rootname, authorizer)
    for section in self.parser.sections():
      if section == root_authz_section:
        for key, value in self._get_parser_items(self.parser, section):
          params[key] = value
    return authorizer, params

  def get_authorizer_params(self, authorizer=None):
    """Return a dictionary of parameter names and values which belong
    to the configured authorizer (or AUTHORIZER, if provided)."""
    params = {}
    if authorizer is None:
      authorizer = self.options.authorizer
    if authorizer:
      authz_section = 'authz-%s' % (self.options.authorizer)
      if hasattr(self, authz_section):
        sub_config = getattr(self, authz_section)
        for attr in dir(sub_config):
          params[attr] = getattr(sub_config, attr)
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
    self.options.show_roots_lastmod = 0
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
    self.options.log_pagesextra = 3
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

    self.query.viewvc_base_url = None
    
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
