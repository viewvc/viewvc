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
# history and logs, available at http://viewvc.tigris.org/.
# ====================================================================

"""Run tests of rcsparse code."""

import sys
import os
import glob
from cStringIO import StringIO
from difflib import Differ

# Since there is nontrivial logic in __init__.py, we have to import
# parse() via that file.  First make sure that the directory
# containing this script is in the path:
script_dir = os.path.dirname(sys.argv[0])
sys.path.insert(0, script_dir)

from __init__ import parse
from parse_rcs_file import LoggingSink


test_dir = os.path.join(script_dir, 'test-data')

filelist = glob.glob(os.path.join(test_dir, '*,v'))
filelist.sort()

all_tests_ok = 1

for filename in filelist:
    sys.stderr.write('%s: ' % (filename,))
    f = StringIO()
    try:
        parse(open(filename, 'rb'), LoggingSink(f))
    except Exception, e:
        sys.stderr.write('Error parsing file: %s!\n' % (e,))
        all_tests_ok = 0
    else:
        output = f.getvalue()

        expected_output_filename = filename[:-2] + '.out'
        expected_output = open(expected_output_filename, 'rb').read()

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

