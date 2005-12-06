# based on mod_python.publisher handler

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
