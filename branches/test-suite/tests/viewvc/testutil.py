# -*-python-*-
#
# Copyright (C) 2009 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "../../lib")))

import sapi
import viewvc
import config
import cStringIO
import difflib

def _abspath(path):
    """Return an absolute form of PATH, which is relative to the test
    suite directory.
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__),
                                        path))
    
def setup_default_config():
    """Return a Config object which contains default values, save for
    the addition of some test suite specifics (root_parents,
    template_dir, etc.)
    """
    cfg = config.Config()
    cfg.set_defaults()
    cfg.general.root_parents.append("%s:cvs" % (_abspath("testroots/cvsroots")))
    cfg.general.root_parents.append("%s:svn" % (_abspath("testroots/svnroots")))
    cfg.options.template_dir = _abspath("templates")
    return cfg

def run_viewvc(cfg, relurl, outfile, script_name, username=None):
    """Simulate a run ViewVC on RELURL, which is the portion of a
    ViewVC request URL (already URI-decoded) that follows the ViewVC
    script location in a typical URL.  For example:

       /projectname/trunk?view=directory&pathrev=34

    For the purposes of simulation, use SCRIPT_NAME as the script
    location during the ViewVC invocation, and USERNAME as the
    authenticated name of the browsing user.

    OUTFILE is a writable file pointer object to which ViewVC's output
    will be written.
    """
    try:
        path, query_string = relurl.split('?', 1)
    except ValueError:
        path = relurl
        query_string = ""
    os.environ['PATH_INFO'] = path
    os.environ['QUERY_STRING'] = query_string
    try:
        viewvc.main(sapi.OutfileServer(outfile, username, script_name), cfg)
    finally:
        del os.environ['PATH_INFO']
        del os.environ['QUERY_STRING']

def run_and_verify_viewvc(cfg, relurl, expected_out, username=None):
    """A wrapper around run_viewvc() which compares the generated
    output against EXPECTED_OUT.  EXPECTED_OUT is a string containing
    the exact expected output of ViewVC -- including any HTTP headers
    -- and in which the '__VIEWVC__' is used to represent the ViewVC
    script location.
    """
    outfile = cStringIO.StringIO()
    run_viewvc(cfg, relurl, outfile, '__VIEWVC__', username)
    actual_out = outfile.getvalue()
    diff = difflib.unified_diff(map(lambda a: a + '\n',
                                    actual_out.split('\n')),
                                map(lambda a: a + '\n',
                                    expected_out.split('\n')))
    sys.stdout.writelines(diff)
