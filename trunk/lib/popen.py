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
import sys

def popen(cmd, args, mode, capture_err=1):
  # flush the stdio buffers since we are about to change the FD under them
  sys.stdout.flush()
  sys.stderr.flush()

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
    ### this isn't quite right... we may want the child to read from stdin
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
    ### this isn't quite right... we may want the child to write to these
    os.dup2(null, 1)
    os.dup2(null, 2)

  # don't need these FDs any more
  os.close(null)
  os.close(r)
  os.close(w)

  # the stdin/stdout/stderr are all set up. exec the target
  try:
    os.execvp(cmd, (cmd,) + tuple(args))
  except:
    # aid debugging, if the os.execvp above fails for some reason:
    import string
    print "<h2>exec failed:</h2><pre>", cmd, string.join(args), "</pre>"
    raise

  # crap. shouldn't be here.
  sys.exit(127)

def pipe_cmds(cmds):
  # flush the stdio buffers since we are about to change the FD under them
  sys.stdout.flush()
  sys.stderr.flush()

  prev_r, parent_w = os.pipe()

  null = os.open('/dev/null', os.O_RDWR)

  for cmd in cmds[:-1]:
    r, w = os.pipe()
    pid = os.fork()
    if not pid:
      # in the child

      # hook up stdin to the "read" channel
      os.dup2(prev_r, 0)

      # hook up stdout to the output channel
      os.dup2(w, 1)

      # toss errors
      os.dup2(null, 2)

      # close these extra descriptors
      os.close(prev_r)
      os.close(parent_w)
      os.close(null)
      os.close(r)
      os.close(w)

      # time to run the command
      try:
        os.execvp(cmd[0], cmd)
      except:
        pass

      sys.exit(127)

    # in the parent

    # we don't need these any more
    os.close(prev_r)
    os.close(w)

    # the read channel of this pipe will feed into to the next command
    prev_r = r

  # no longer needed
  os.close(null)

  # done with most of the commands. set up the last command to write to stdout
  pid = os.fork()
  if not pid:
    # in the child (the last command)

    # hook up stdin to the "read" channel
    os.dup2(prev_r, 0)

    # close these extra descriptors
    os.close(prev_r)
    os.close(parent_w)

    # run the last command
    try:
      os.execvp(cmds[-1][0], cmds[-1])
    except:
      pass

    sys.exit(127)

  # not needed any more
  os.close(prev_r)

  # write into the first pipe, wait on the final process
  return _pipe(os.fdopen(parent_w, 'w'), pid)


class _pipe:
  "Wrapper for a file which can wait() on a child process at close time."

  def __init__(self, file, child_pid):
    self.file = file
    self.child_pid = child_pid

  def eof(self):
    pid, status = os.waitpid(self.child_pid, os.WNOHANG)
    if pid:
      self.file.close()
      self.file = None
      return status
    return None

  def close(self):
    if self.file:
      self.file.close()
      self.file = None
      return os.waitpid(self.child_pid, 0)[1]
    return None

  def __getattr__(self, name):
    return getattr(self.file, name)

  def __del__(self):
    if self.file:
      self.close()
