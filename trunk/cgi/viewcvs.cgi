#!/usr/bin/python
# -*-python-*-
#
# Copyright (C) 1999-2000 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://www.lyra.org/viewcvs/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://www.lyra.org/viewcvs/
#
# -----------------------------------------------------------------------
#
# viewcvs: View CVS repositories via a web browser
#
# -----------------------------------------------------------------------
#
# This software is based on "cvsweb" by Henner Zeller (which is, in turn,
# derived from software by Bill Fenner, with additional modifications by
# Henrik Nordstrom and Ken Coar). The cvsweb distribution can be found
# on Zeller's site:
#   http://stud.fh-heilbronn.de/~zeller/cgi/cvsweb.cgi/
#
# -----------------------------------------------------------------------
#

__version__ = '0.6'

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

import sys
import os
import cgi
import string
import urllib
import mimetypes
import time
import re
import stat
import struct

#########################################################################
#
# Adjust sys.path to include our library directory
#

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)
else:
  sys.path[:0] = ['../lib']	# any other places to look?

# time for our imports now
import compat
import config
import popen


#########################################################################
