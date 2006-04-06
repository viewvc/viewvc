#!/usr/bin/python
# -*- Mode: python -*-
#
# Copyright (C) 2000-2001 The ViewCVS Group. All Rights Reserved.
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

#########################################################################
#
# INSTALL-TIME CONFIGURATION
#
# These values will be set during the installation process. During
# development, they will remain None.
#

LIBRARY_DIR = None
CONF_PATHNAME = None
HTML_TEMPLATE_DIR = None

# Adjust sys.path to include our library directory
import sys

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)
else:
  sys.path[:0] = ['../lib']	# any other places to look?

#########################################################################

import os, string


def HTMLHeader():
    print "Content-type: text/html"
    print
    

def Main():
    HTMLHeader()
    template_path = os.path.join(HTML_TEMPLATE_DIR, "queryformtemplate.html")
    print open(template_path, "r").read()


if __name__ == '__main__':
    Main()
