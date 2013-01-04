# -*-python-*-
#
# Copyright (C) 1999-2013 The ViewCVS Group. All Rights Reserved.
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


class TemplateData:
  """A custom dictionary-like object that allows one-time definition
  of keys, and only value fetches and changes, and key deletions,
  thereafter.

  EZT doesn't require the use of this special class -- a normal
  dict-type data dictionary works fine.  But use of this class will
  assist those who want the data sent to their templates to have a
  consistent set of keys."""

  def __init__(self, initial_data={}):
    self._items = initial_data
    
  def __getitem__(self, key):
    return self._items.__getitem__(key)

  def __setitem__(self, key, item):
    assert self._items.has_key(key)
    return self._items.__setitem__(key, item)

  def __delitem__(self, key):
    return self._items.__delitem__(key)

  def keys(self):
    return self._items.keys()

  def merge(self, template_data):
    """Merge the data in TemplataData instance TEMPLATA_DATA into this
    instance.  Avoid the temptation to use this conditionally in your
    code -- it rather defeats the purpose of this class."""
    
    assert isinstance(template_data, TemplateData)
    self._items.update(template_data._items)
