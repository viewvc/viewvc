from mod_python import apache, util 
import imp 
import os 
import sys
import thread

requests = {}

def GetRequest():
  return requests[thread.get_ident()]

def handler(req):
  # based on mod_python.cgihandler
  
  req.add_common_vars()

  if req.subprocess_env.has_key("script_filename"):
      dir, file = os.path.split(req.subprocess_env["script_filename"])
  else:
      dir, file = os.path.split(req.filename)
  module_name, ext = os.path.splitext(file)

  try:
      # we do not search the pythonpath (security reasons)
      fd, path, desc = imp.find_module(module_name, [dir])
  except ImportError:
      raise apache.SERVER_RETURN, apache.HTTP_NOT_FOUND
  
  # prevent scripts named query.py and viewcvs.py from shadowing
  # modules in viewcvs/lib directory
  module_name += '_page'
  
  requests[thread.get_ident()] = req
  try:
    imp.load_module(module_name, fd, path, desc)
  finally:
    del requests[thread.get_ident()]

  return apache.OK
