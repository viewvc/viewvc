# -*-python-*-
#
# Copyright (C) 1999-2008 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

"Version Control lib driver for Subversion repositories"

import os
import os.path
import re

def SubversionRepository(name, rootpath, authorizer, utilities, config_dir):
  re_url = re.compile('^(http|https|file|svn|svn\+[^:]+)://')
  if re.search(re_url, rootpath):
    import svn_ra
    return svn_ra.RemoteSubversionRepository(name, rootpath, authorizer,
                                             utilities, config_dir)
  else:
    import svn_repos
    rootpath = os.path.normpath(rootpath)
    return svn_repos.LocalSubversionRepository(name, rootpath, authorizer,
                                               utilities, config_dir)
