# -*-python-*-
#
# Copyright (C) 1999-2020 The ViewCVS Group. All Rights Reserved.
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

def recode_latin1_path(path):
  return path.encode('latin-1').decode('utf-8')

def application(environ, start_response):
  server = sapi.WsgiServer(environ, start_response)

  # PEP 3333 demands that PATH_INFO et al carry only latin-1 strings,
  # so multibyte versioned path names arrive munged, with each byte
  # being a character.  But ViewVC generates it's own URLs from
  # Unicode strings, where UTF-8 is used during URI-encoding.  So we
  # need to reinterpret path-carrying CGI environment variables as
  # UTF-8 instead of as latin-1.
  environ['PATH_INFO'] = recode_latin1_path(environ['PATH_INFO'])
  environ['SCRIPT_NAME'] = recode_latin1_path(environ['SCRIPT_NAME'])

  cfg = viewvc.load_config(CONF_PATHNAME, server)
  viewvc.main(server, cfg)
  return []
