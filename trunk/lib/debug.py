# -*- Mode: python -*-
#
# Copyright (C) 2000-2001 The ViewCVS Group. All Rights Reserved.
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
# Note: a t_start/t_end pair consumes about 0.00005 seconds on a P3/700.
#       the lambda form (when debugging is disabled) should be even faster.
#

if 0:

  import time

  _timers = { }
  _times = { }

  def t_start(which):
    _timers[which] = time.time()

  def t_end(which):
    t = time.time() - _timers[which]
    if _times.has_key(which):
      _times[which] = _times[which] + t
    else:
      _times[which] = t

  def dump():
    for name, value in _times.items():
      print '%s: %.6f<br>' % (name, value)

else:

  t_start = t_end = dump = lambda *args: None
