#!/usr/bin/env python3
# -*-python-*-
#
# Copyright (C) 1999-2025 The ViewCVS Group. All Rights Reserved.
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

import sys
import os


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

# Adjust sys.path to include our library directory.
if LIBRARY_DIR:
    sys.path.insert(0, LIBRARY_DIR)
else:
    sys.path.insert(0, os.path.abspath(os.path.join(sys.argv[0], "../../../lib")))
import sapi
import viewvc

# If admins want nicer processes, here's the place to get them.
#
# try:
#   os.nice(20) # bump the nice level of this process
# except:
#   pass

server = sapi.CgiServer()
cfg = viewvc.load_config(CONF_PATHNAME, server)
viewvc.main(server, cfg)
