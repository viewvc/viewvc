# -*-python-*-
#
# Copyright (C) 2006-2011 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
# (c) 2006 Sergey Lapin <slapin@dataart.com>

import vcauth
import string
import os.path
import debug

from ConfigParser import ConfigParser

class ViewVCAuthorizer(vcauth.GenericViewVCAuthorizer):
  """Subversion authz authorizer module"""
  
  def __init__(self, username, params={}):
    self.rootpaths = { }  # {root -> { paths -> access boolean for USERNAME }}
    
    # Get the authz file location from a passed-in parameter.
    self.authz_file = params.get('authzfile')
    if not self.authz_file:
      raise debug.ViewVCException("No authzfile configured")
    if not os.path.exists(self.authz_file):
      raise debug.ViewVCException("Configured authzfile file not found")

    # See if the admin wants us to do case normalization of usernames.
    self.force_username_case = params.get('force_username_case')
    if self.force_username_case == "upper":
      self.username = username.upper()
    elif self.force_username_case == "lower":
      self.username = username.lower()
    elif not self.force_username_case:
      self.username = username
    else:
      raise debug.ViewVCException("Invalid value for force_username_case "
                                  "option")

  def _get_paths_for_root(self, rootname):
    if self.rootpaths.has_key(rootname):
      return self.rootpaths[rootname]

    paths_for_root = { }
    
    # Parse the authz file, replacing ConfigParser's optionxform()
    # method with something that won't futz with the case of the
    # option names.
    cp = ConfigParser()
    cp.optionxform = lambda x: x
    try:
      cp.read(self.authz_file)
    except:
      raise debug.ViewVCException("Unable to parse configured authzfile file")

    # Figure out if there are any aliases for the current username
    aliases = []
    if cp.has_section('aliases'):
      for alias in cp.options('aliases'):
        entry = cp.get('aliases', alias)
        if entry == self.username:
          aliases.append(alias)

    # Figure out which groups USERNAME has a part of.
    groups = []
    if cp.has_section('groups'):
      all_groups = []

      def _process_group(groupname):
        """Inline function to handle groups within groups.
        
        For a group to be within another group in SVN, the group
        definitions must be in the correct order in the config file.
        ie. If group A is a member of group B then group A must be
        defined before group B in the [groups] section.
        
        Unfortunately, the ConfigParser class provides no way of
        finding the order in which groups were defined so, for reasons
        of practicality, this function lets you get away with them
        being defined in the wrong order.  Recursion is guarded
        against though."""
        
        # If we already know the user is part of this already-
        # processed group, return that fact.
        if groupname in groups:
          return 1
        # Otherwise, ensure we don't process a group twice.
        if groupname in all_groups:          
          return 0
        # Store the group name in a global list so it won't be processed again
        all_groups.append(groupname)
        group_member = 0
        groupname = groupname.strip()
        entries = string.split(cp.get('groups', groupname), ',')
        for entry in entries:
          entry = string.strip(entry)
          if entry == self.username:
            group_member = 1
            break
          elif entry[0:1] == "@" and _process_group(entry[1:]):
            group_member = 1
            break
          elif entry[0:1] == "&" and entry[1:] in aliases:
            group_member = 1
            break
        if group_member:
          groups.append(groupname)
        return group_member
      
      # Process the groups
      for group in cp.options('groups'):
        _process_group(group)

    def _userspec_matches_user(userspec):
      # If there is an inversion character, recurse and return the
      # opposite result.
      if userspec[0:1] == '~':
        return not _userspec_matches_user(userspec[1:])

      # See if the userspec applies to our current user.
      return userspec == '*' \
             or userspec == self.username \
             or (self.username is not None and userspec == "$authenticated") \
             or (self.username is None and userspec == "$anonymous") \
             or (userspec[0:1] == "@" and userspec[1:] in groups) \
             or (userspec[0:1] == "&" and userspec[1:] in aliases)
      
    def _process_access_section(section):
      """Inline function for determining user access in a single
      config secction.  Return a two-tuple (ALLOW, DENY) containing
      the access determination for USERNAME in a given authz file
      SECTION (if any)."""
  
      # Figure if this path is explicitly allowed or denied to USERNAME.
      allow = deny = 0
      for user in cp.options(section):
        user = string.strip(user)
        if _userspec_matches_user(user):
          # See if the 'r' permission is among the ones granted to
          # USER.  If so, we can stop looking.  (Entry order is not
          # relevant -- we'll use the most permissive entry, meaning
          # one 'allow' is all we need.)
          allow = string.find(cp.get(section, user), 'r') != -1
          deny = not allow
          if allow:
            break
      return allow, deny
    
    # Read the other (non-"groups") sections, and figure out in which
    # repositories USERNAME or his groups have read rights.  We'll
    # first check groups that have no specific repository designation,
    # then superimpose those that have a repository designation which
    # matches the one we're asking about.
    root_sections = []
    for section in cp.sections():

      # Skip the "groups" section -- we handled that already.
      if section == 'groups':
        continue
      
      if section == 'aliases':
        continue

      # Process root-agnostic access sections; skip (but remember)
      # root-specific ones that match our root; ignore altogether
      # root-specific ones that don't match our root.  While we're at
      # it, go ahead and figure out the repository path we're talking
      # about.
      if section.find(':') == -1:
        path = section
      else:
        name, path = string.split(section, ':', 1)
        if name == rootname:
          root_sections.append(section)
        continue

      # Check for a specific access determination.
      allow, deny = _process_access_section(section)
          
      # If we got an explicit access determination for this path and this
      # USERNAME, record it.
      if allow or deny:
        if path != '/':
          path = '/' + string.join(filter(None, string.split(path, '/')), '/')
        paths_for_root[path] = allow

    # Okay.  Superimpose those root-specific values now.
    for section in root_sections:

      # Get the path again.
      name, path = string.split(section, ':', 1)
      
      # Check for a specific access determination.
      allow, deny = _process_access_section(section)
                
      # If we got an explicit access determination for this path and this
      # USERNAME, record it.
      if allow or deny:
        if path != '/':
          path = '/' + string.join(filter(None, string.split(path, '/')), '/')
        paths_for_root[path] = allow

    # If the root isn't readable, there's no point in caring about all
    # the specific paths the user can't see.  Just point the rootname
    # to a None paths dictionary.
    root_is_readable = 0
    for path in paths_for_root.keys():
      if paths_for_root[path]:
        root_is_readable = 1
        break
    if not root_is_readable:
      paths_for_root = None
      
    self.rootpaths[rootname] = paths_for_root
    return paths_for_root

  def check_root_access(self, rootname):
    paths = self._get_paths_for_root(rootname)
    return (paths is not None) and 1 or 0
  
  def check_universal_access(self, rootname):
    paths = self._get_paths_for_root(rootname)
    if not paths: # None or empty.
      return 0

    # Search the access determinations.  If there's a mix, we can't
    # claim a universal access determination.
    found_allow = 0
    found_deny = 0
    for access in paths.values():
      if access:
        found_allow = 1
      else:
        found_deny = 1
      if found_allow and found_deny:
        return None

    # We didn't find both allowances and denials, so we must have
    # found one or the other.  Denials only is a universal denial.
    if found_deny:
      return 0

    # ... but allowances only is only a universal allowance if read
    # access is granted to the root directory.
    if found_allow and paths.has_key('/'):
      return 1

    # Anything else is indeterminable.
    return None
    
  def check_path_access(self, rootname, path_parts, pathtype, rev=None):
    # Crawl upward from the path represented by PATH_PARTS toward to
    # the root of the repository, looking for an explicitly grant or
    # denial of access.
    paths = self._get_paths_for_root(rootname)
    if paths is None:
      return 0
    parts = path_parts[:]
    while parts:
      path = '/' + string.join(parts, '/')
      if paths.has_key(path):
        return paths[path]
      del parts[-1]
    return paths.get('/', 0)
