#
# Copyright (C) 2000 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://www.lyra.org/viewcvs/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://www.lyra.org/viewcvs/
#
# -----------------------------------------------------------------------
#
# popen.py: a replacement for os.popen()
#
# This implementation of popen() provides a cmd + args calling sequence,
# rather than a system() type of convention. The shell facilities are not
# available, but that implies we can avoid worrying about shell hacks in
# the arguments.
#
# -----------------------------------------------------------------------
#

import os

def popen(cmd, args, mode, capture_err=1):
  r, w = os.pipe()
  pid = os.fork()
  if pid:
    # in the parent

    # close the descriptor that we don't need and return the other one.
    if mode == 'r':
      os.close(w)
      return _pipe(os.fdopen(r, 'r'), pid)
    os.close(r)
    return _pipe(os.fdopen(w, 'w'), pid)

  # in the child

  # we'll need /dev/null for the discarded I/O
  null = os.open('/dev/null', os.O_RDWR)

  if mode == 'r':
    # hook stdout/stderr to the "write" channel
    os.dup2(w, 1)
    # "close" stdin; the child shouldn't use it
    os.dup2(null, 0)
    # what to do with errors?
    if capture_err:
      os.dup2(w, 2)
    else:
      os.dup2(null, 2)
  else:
    # hook stdin to the "read" channel
    os.dup2(r, 0)
    # "close" stdout/stderr; the child shouldn't use them
    os.dup2(null, 1)
    os.dup2(null, 2)

  # don't need these FDs any more
  os.close(null)
  os.close(r)
  os.close(w)

  # the stdin/stdout/stderr are all set up. exec the target
  os.execvp(cmd, (cmd,) + tuple(args))

  # crap. shouldn't be here.
  sys.exit(127)


class _pipe:
  "Wrapper for a file which can wait() on a child process at close time."

  def __init__(self, file, child_pid):
    self.file = file
    self.child_pid = child_pid

  def close(self):
    self.file.close()
    self.file = None
    return os.waitpid(self.child_pid, 0)[1] or None

  def __getattr__(self, name):
    return getattr(self.file, name)

  def __del__(self):
    if self.file:
      self.close()
