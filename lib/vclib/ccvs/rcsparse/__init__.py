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

"""This package provides parsing tools for RCS files."""

from common import *

try:
  from tparse import parse
except ImportError:
  try:
    from texttools import Parser
  except ImportError:
    from default import Parser

  def parse(file, sink):
    return Parser().parse(file, sink)
