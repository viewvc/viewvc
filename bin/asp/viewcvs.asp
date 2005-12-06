<%@ LANGUAGE = Python %>
<%

# -*-python-*-
#
# Copyright (C) 1999-2002 The ViewCVS Group. All Rights Reserved.
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
# viewcvs: View CVS repositories via a web browser
#
# -----------------------------------------------------------------------
#
# This is a teeny stub to launch the main ViewCVS app. It checks the load
# average, then loads the (precompiled) viewcvs.py file and runs it.
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
import viewcvs

server = sapi.AspServer(Server, Request, Response, Application)
try:
  cfg = viewcvs.load_config(CONF_PATHNAME, server)
  viewcvs.main(server, cfg)
finally:
  s.close()

%>
