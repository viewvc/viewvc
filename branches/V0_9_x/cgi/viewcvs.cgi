#!/usr/bin/python
# -*-python-*-
#
# Copyright (C) 1999-2001 The ViewCVS Group. All Rights Reserved.
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

#########################################################################
#
# Adjust sys.path to include our library directory
#

import sys

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)
else:
  sys.path[:0] = ['../lib']	# any other places to look?

#########################################################################

### add code for checking the load average

#########################################################################

# go do the work
import viewcvs
viewcvs.run_cgi()
