from mod_python import apache

def handler(req):
  req.add_common_vars()
  execfile(req.subprocess_env["script_filename"], {}, {'Request': req})
  return apache.OK
