# -*-python-*-
#
# Copyright (C) 1999-2012 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# Mod_Python handler based on mod_python.publisher
#
# -----------------------------------------------------------------------

from mod_python import apache
import os.path

def handler(req):
  path, module_name = os.path.split(req.filename)
  module_name, module_ext = os.path.splitext(module_name)
  try:
    module = apache.import_module(module_name, path=[path])
  except ImportError:
    raise apache.SERVER_RETURN, apache.HTTP_NOT_FOUND

  req.add_common_vars()
  module.index(req)

  return apache.OK
