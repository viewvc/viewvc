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
path_to_cvsgraph = os.path.dirname(LIBRARY_DIR) + '/cvsgraph'
 
path_to_cvsgraph_conf = os.path.dirname(LIBRARY_DIR) + '/cvsgraph.conf'

form = cgi.FieldStorage()

# Defaults not used right now...
defaults = {'r': '',
            'm': '',
            'f': ''}
for key in defaults.keys():
  try:
    exec '%s = form["%s"].value' % (key,key)
  except KeyError:
    exec '%s = "%s"' % (key,defaults[key])

# Start the web page
print """Content-Type: text/html

<html>
<head>
  <title>Revisions of %s</title>
    <meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
    <meta name="generator" content="handcrafted">
</head>
<body bgcolor="#f0f0f0">
<center>
<title>Revisions of %s</title>""" % (f[:-2],f[:-2])


# This statement is very important!  Otherwise you can't garantee the order
# that things get printed out to the browser!
sys.stdout.flush()


# Required only if cvsgraph needs to find it's supporting libraries.
# Uncomment and set accordingly if required.
#os.environ['LD_LIBRARY_PATH'] = '/usr/lib:/usr/local/lib'

# Create an image map
command = "%s -i -c %s -r %s -m '%s' %s" % (path_to_cvsgraph, 
		    path_to_cvsgraph_conf, r, m, f)
if os.system(command) != 0:
    sys.stderr.write("\nFailed to execute '"+command+"'.\n")

print """<img border="0" 
          usemap="#MyMapName" 
          src="cvsgraphmkimg.cgi?c=%s&r=%s&m=%s&f=%s" 
          alt="Revisions of %s">""" % (path_to_cvsgraph_conf,r,m,f,f[:-2])

print '</center>'
print '</body>'
print '</html>'

