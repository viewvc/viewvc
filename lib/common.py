# -*-python-*-
#
# Copyright (C) 1999-2010 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# common: common definitions for the viewvc library
#
# -----------------------------------------------------------------------

# Special type indicators for diff header processing and idiff return codes
_RCSDIFF_IS_BINARY = 'binary-diff'
_RCSDIFF_ERROR = 'error'
_RCSDIFF_NO_CHANGES = "no-changes"

class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
