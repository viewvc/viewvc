#
# Copyright (C) 2000-2002 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# This software is being maintained as part of the ViewVC project.
# Information is available at:
#    http://viewvc.org/
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
