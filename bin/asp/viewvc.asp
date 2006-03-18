<%@ LANGUAGE = Python %>
<%

# -*-python-*-
#
# Copyright (C) 1999-2006 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# viewvc: View CVS/SVN repositories via a web browser
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
  if not LIBRARY_DIR in sys.path:
    sys.path.insert(0, LIBRARY_DIR)

#########################################################################

### add code for checking the load average

#########################################################################

# go do the work
import sapi
import viewvc

server = sapi.AspServer(Server, Request, Response, Application)
try:
  cfg = viewvc.load_config(CONF_PATHNAME, server)
  viewvc.main(server, cfg)
finally:
  s.close()

%>
