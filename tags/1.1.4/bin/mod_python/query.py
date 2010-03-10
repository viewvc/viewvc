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
#
# ViewVC: View CVS/SVN repositories via a web browser
#
# -----------------------------------------------------------------------
#
# This is a teeny stub to launch the main ViewVC app. It checks the load
# average, then loads the (precompiled) viewvc.py file and runs it.
#
# -----------------------------------------------------------------------
#

#########################################################################
#
# INSTALL-TIME CONFIGURATION
#
# These values will be set during the installation process. During
# development, they will remain None.
#

LIBRARY_DIR = None
CONF_PATHNAME = None

#########################################################################
#
# Adjust sys.path to include our library directory
#

import sys

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)

import sapi
import imp

# Import real ViewVC module
fp, pathname, description = imp.find_module('viewvc', [LIBRARY_DIR])
try:
  viewvc = imp.load_module('viewvc', fp, pathname, description)
finally:
  if fp:
    fp.close()

# Import real ViewVC Query modules
fp, pathname, description = imp.find_module('query', [LIBRARY_DIR])
try:
  query = imp.load_module('query', fp, pathname, description)
finally:
  if fp:
    fp.close()

cfg = viewvc.load_config(CONF_PATHNAME)

def index(req):
  server = sapi.ModPythonServer(req)
  try:
    query.main(server, cfg, "viewvc.py")
  finally:
    server.close()

