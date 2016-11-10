#!/usr/bin/python
# -*-python-*-
#
# Copyright (C) 1999-2016 The ViewCVS Group. All Rights Reserved.
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
# This is a wsgi entry point for the main ViewVC app. It's appropriate
# for use with mod_wsgi. It defines a single application function that
# is a valid wsgi entry point.
#
# -----------------------------------------------------------------------

import sys, os

LIBRARY_DIR = None
CONF_PATHNAME = None

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)
else:
  sys.path.insert(0, os.path.abspath(os.path.join(sys.argv[0],
                                                  "../../../lib")))

import sapi
import viewvc

def application(environ, start_response):
  server = sapi.WsgiServer(environ, start_response)
  cfg = viewvc.load_config(CONF_PATHNAME, server)
  viewvc.main(server, cfg)
  return []
