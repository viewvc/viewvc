#! /usr/bin/python

# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.  The terms
# are also available at http://subversion.tigris.org/license-1.html.
# If newer versions of this license are posted there, you may use a
# newer version instead, at your option.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs, available at https://github.com/viewvc/viewvc/.
# ====================================================================

"""Run tests of rcsparse code."""

import sys
import os
import glob
if sys.version_info[0] >= 3:
  from io import StringIO
else:
  from cStringIO import StringIO
from difflib import Differ

# Since there is nontrivial logic in __init__.py, we have to import
# parse() via that file.  First make sure that the directory
# containing this script is in the path:
script_dir = os.path.dirname(sys.argv[0])
sys.path.insert(0, script_dir)
# Since there is nontrivial logic in __init__.py, we have to import
# parse() via that file.  However, __init__.py uses relative import
# for the package now, so we must import it as a package:
# containing this script is in the path:
p_dir, p_name = os.path.split(os.path.dirname(os.path.abspath(sys.argv[0])))
sys.path.insert(0, p_dir)
script_dir = os.path.dirname(sys.argv[0])

#from __init__ import parse
rcsparse = __import__(p_name)
parse = rcsparse.parse

sys.path.insert(0, script_dir)
from parse_rcs_file import LoggingSink

test_dir = os.path.join(script_dir, 'test-data')

filelist = glob.glob(os.path.join(test_dir, '*,v'))
filelist.sort()

all_tests_ok = 1

for filename in filelist:
    sys.stderr.write('%s: ' % (filename,))
    f = StringIO()
    try:
        parse(open(filename, 'rt'), LoggingSink(f))
    except Exception as e:
        sys.stderr.write('Error parsing file: %s!\n' % (e,))
        raise
        all_tests_ok = 0
    else:
        output = f.getvalue()

        expected_output_filename = filename[:-2] + '.out'
        expected_output = open(expected_output_filename, 'rt').read()

        if output == expected_output:
            sys.stderr.write('OK\n')
        else:
            sys.stderr.write('Output does not match expected output!\n')
            differ = Differ()
            for diffline in differ.compare(
                expected_output.splitlines(1), output.splitlines(1)
                ):
                sys.stderr.write(diffline)
            all_tests_ok = 0

if all_tests_ok:
    sys.exit(0)
else:
    sys.exit(1)

