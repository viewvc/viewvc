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
# cvsgraphwrapper.cgi: Wrapper to run cvsgraph from viewcvs.
#
# -----------------------------------------------------------------------

import cgi
import os
import sys

# Set during install process.
LIBRARY_DIR = None

# I was going to pass this from viewcvs, but thought that the path printed 
# out in the URL would be insecure.  Is that true?
# Put cvsgraph executable in the viewcvs install directory.
path_to_cvsgraph = LIBRARY_DIR(:-3) + 'cvsgraph'

path_to_cvsgraph_conf = LIBRARY_DIR(:-3) + 'cvsgraph.conf'

form = cgi.FieldStorage()

# For debugging interaction with cvsgraph, it is sometimes useful to
# change 'Content-type: image/png' to 'Content-type: text/plain'.
# You might then see any error message from cvsgraph, or your browser
# will crash.  YMMV.
print 'Content-type: image/png'
print ''

# This statement is very important!  Otherwise you can't garantee the order
# that things get printed out to the browser!
sys.stdout.flush()

defaults = {'f': ''}

for key in defaults.keys():
  try:
    exec '%s = form["%s"].value' % (key,key)
  except KeyError:
    exec '%s = "%s"' % (key,defaults[key])

# Required only if cvsgraph needs to find it's supporting libraries.
# Uncomment and set accordingly if required.
#os.environ['LD_LIBRARY_PATH'] = '/usr/lib:/usr/local/lib'

os.system('%s -c %s -r "" -m "" %s' % (path_to_cvsgraph, path_to_cvsgraph_conf,  f))

