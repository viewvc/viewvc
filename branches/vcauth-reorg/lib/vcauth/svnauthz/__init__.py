# -*-python-*-
#
# Copyright (C) 2006 The ViewCVS Group. All Rights Reserved.
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
    self.username = username
    self.rootpaths = { }  # {root -> { paths -> access boolean for USERNAME }}
    
    # Get the authz file location from a passed-in parameter.
    self.authz_file = params.get('authzfile')
    if not self.authz_file:
      raise debug.ViewVCException("No authzfile configured")
    if not os.path.exists(self.authz_file):
      raise debug.ViewVCException("Configured authzfile file not found")

  def _get_paths_for_root(self, root):
    rootname = root.rootname()
    if self.rootpaths.has_key(rootname):
      return self.rootpaths[rootname]

    paths_for_root = { }
    
    # Parse the authz file.
    cp = ConfigParser()
    cp.read(self.authz_file)

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
        if group_member:
          groups.append(groupname)
        return group_member
      
      # Process the groups
      for group in cp.options('groups'):
        _process_group(group)

    # Read the other (non-"groups") sections, and figure out in which
    # repositories USERNAME or his groups have read rights.
    root_is_readable = 0
    for section in cp.sections():

      # Skip the "groups" section -- we handled that already.
      if section == 'groups':
        continue

      # Skip sections not related to our rootname.  While we're at it,
      # go ahead and figure out the repository path we're talking about.
      if section.find(':') == -1:
        path = section
      else:
        name, path = string.split(section, ':', 1)
        if name != rootname:
          continue

      # Figure if this path is explicitly allowed or denied to USERNAME.
      allow = deny = 0
      for user in cp.options(section):
        user = string.strip(user)
        if user == '*' \
           or user == self.username \
           or (user[0:1] == "@" and user[1:] in groups):
          # See if the 'r' permission is among the ones granted to
          # USER.  If so, we can stop looking.  (Entry order is not
          # relevant -- we'll use the most permissive entry, meaning
          # one 'allow' is all we need.)
          allow = string.find(cp.get(section, user), 'r') != -1
          deny = not allow
          if allow:
            break
          
      # If we got an explicit access determination for this path and this
      # USERNAME, record it.
      if allow or deny:
        if allow:
          root_is_readable = 1
        if path != '/':
          path = '/' + string.join(filter(None, string.split(path, '/')), '/')
        paths_for_root[path] = allow

    # If the root isn't readable, there's no point in caring about all
    # the specific paths the user can't see.  Just point the rootname
    # to a None paths dictionary.
    if not root_is_readable:
      paths_for_root = None
      
    self.rootpaths[rootname] = paths_for_root
    return paths_for_root

  def check_root_access(self, root):
    paths = self._get_paths_for_root(root)
    return (paths is not None) and 1 or 0
  
  def check_path_access(self, root, path_parts, rev=None):
    # Crawl upward from the path represented by PATH_PARTS toward to
    # the root of the repository, looking for an explicitly grant or
    # denial of access.
    paths = self._get_paths_for_root(root)
    if paths is None:
      return 0
    parts = path_parts[:]
    while parts:
      path = '/' + string.join(parts, '/')
      if paths.has_key(path):
        return paths[path]
      del parts[-1]
    return paths.get('/', 0)
