# -*-python-*-
#
# Copyright (C) 1999-2006 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

"""This package provides parsing tools for RCS files.

To use this package, first create a subclass of Sink.  This should
declare all the callback methods you care about.  Create an instance
of your class, and open() the RCS file you want to read.  Then call
parse() to parse the file.
"""

# Make the "Sink" class and the various exception classes visible in this
# scope.  That way, applications never need to import any of the
# sub-packages.
from common import *

try:
  from tparse import parse
except ImportError:
  try:
    from texttools import Parser
  except ImportError:
    from default import Parser

  def parse(file, sink):
    """Parse an RCS file.

    Parameters: FILE is the file object to parse.  (I.e. an object of the
    built-in Python type "file", usually created using Python's built-in
    "open()" function).  It should be opened in binary mode.
    SINK is an instance of (some subclass of) Sink.  It's methods will be
    called as the file is parsed; see the definition of Sink for the
    details.
    """
    return Parser().parse(file, sink)
