#!/usr/bin/python
# -*-python-*-
#
# Copyright (C) 1999-2002 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# query.cgi: View CVS/SVN commit database by web browser
#
# -----------------------------------------------------------------------
#
# This is a teeny stub to launch the main ViewVC app. It checks the load
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
import os

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)
else:
  sys.path.insert(0, os.path.abspath(os.path.join(sys.argv[0],
                                                  "../../../lib")))

#########################################################################

import sapi
import viewcvs
import query

server = sapi.CgiServer()
cfg = viewcvs.load_config(CONF_PATHNAME, server)
query.main(server, cfg, "viewcvs.cgi")
