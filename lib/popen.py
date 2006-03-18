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
#
# popen.py: a replacement for os.popen()
#
# This implementation of popen() provides a cmd + args calling sequence,
# rather than a system() type of convention. The shell facilities are not
# available, but that implies we can avoid worrying about shell hacks in
# the arguments.
#
# -----------------------------------------------------------------------

import os
import sys
import sapi
import threading
import string

if sys.platform == "win32":
  import win32popen
  import win32event
  import win32process
  import debug
  import StringIO

def popen(cmd, args, mode, capture_err=1):
  if sys.platform == "win32":
    command = win32popen.CommandLine(cmd, args)

    if string.find(mode, 'r') >= 0:
      hStdIn = None

      if debug.SHOW_CHILD_PROCESSES:
        dbgIn, dbgOut = None, StringIO.StringIO()

        handle, hStdOut = win32popen.MakeSpyPipe(0, 1, (dbgOut,))

        if capture_err:
          hStdErr = hStdOut
          dbgErr = dbgOut
        else:
          dbgErr = StringIO.StringIO()
          x, hStdErr = win32popen.MakeSpyPipe(None, 1, (dbgErr,))
      else:
        handle, hStdOut = win32popen.CreatePipe(0, 1)
        if capture_err:
          hStdErr = hStdOut
        else:
          hStdErr = win32popen.NullFile(1)

    else:
      if debug.SHOW_CHILD_PROCESSES:
        dbgIn, dbgOut, dbgErr = StringIO.StringIO(), StringIO.StringIO(), StringIO.StringIO()
        hStdIn, handle = win32popen.MakeSpyPipe(1, 0, (dbgIn,))
        x, hStdOut = win32popen.MakeSpyPipe(None, 1, (dbgOut,))
        x, hStdErr = win32popen.MakeSpyPipe(None, 1, (dbgErr,))
      else:
        hStdIn, handle = win32popen.CreatePipe(0, 1)
        hStdOut = None
        hStdErr = None

    phandle, pid, thandle, tid = win32popen.CreateProcess(command, hStdIn, hStdOut, hStdErr)

    if debug.SHOW_CHILD_PROCESSES:
      debug.Process(command, dbgIn, dbgOut, dbgErr)

    return _pipe(win32popen.File2FileObject(handle, mode), phandle)

  # flush the stdio buffers since we are about to change the FD under them
  sys.stdout.flush()
  sys.stderr.flush()

  r, w = os.pipe()
  pid = os.fork()
  if pid:
    # in the parent

    # close the descriptor that we don't need and return the other one.
    if string.find(mode, 'r') >= 0:
      os.close(w)
      return _pipe(os.fdopen(r, mode), pid)
    os.close(r)
    return _pipe(os.fdopen(w, mode), pid)

  # in the child

  # we'll need /dev/null for the discarded I/O
  null = os.open('/dev/null', os.O_RDWR)

  if string.find(mode, 'r') >= 0:
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
    print "<h2>exec failed:</h2><pre>", cmd, string.join(args), "</pre>"
    raise

  # crap. shouldn't be here.
  sys.exit(127)

def pipe_cmds(cmds, out=None):
  """Executes a sequence of commands. The output of each command is directed to
  the input of the next command. A _pipe object is returned for writing to the
  first command's input. The output of the last command is directed to the
  "out" file object or the standard output if "out" is None. If "out" is not an
  OS file descriptor, a separate thread will be spawned to send data to its
  write() method."""

  if out is None:
    out = sys.stdout

  if sys.platform == "win32":
    ### FIXME: windows implementation ignores "out" argument, always
    ### writing last command's output to standard out

    if debug.SHOW_CHILD_PROCESSES:
      dbgIn = StringIO.StringIO()
      hStdIn, handle = win32popen.MakeSpyPipe(1, 0, (dbgIn,))

      i = 0
      for cmd in cmds:
        i = i + 1

        dbgOut, dbgErr = StringIO.StringIO(), StringIO.StringIO()

        if i < len(cmds):
          nextStdIn, hStdOut = win32popen.MakeSpyPipe(1, 1, (dbgOut,))
          x, hStdErr = win32popen.MakeSpyPipe(None, 1, (dbgErr,))
        else:
          ehandle = win32event.CreateEvent(None, 1, 0, None)
          nextStdIn, hStdOut = win32popen.MakeSpyPipe(None, 1, (dbgOut, sapi.server.file()), ehandle)
          x, hStdErr = win32popen.MakeSpyPipe(None, 1, (dbgErr,))

        command = win32popen.CommandLine(cmd[0], cmd[1:])
        phandle, pid, thandle, tid = win32popen.CreateProcess(command, hStdIn, hStdOut, hStdErr)
        if debug.SHOW_CHILD_PROCESSES:
          debug.Process(command, dbgIn, dbgOut, dbgErr)

        dbgIn = dbgOut
        hStdIn = nextStdIn


    else:

      hStdIn, handle = win32popen.CreatePipe(1, 0)
      spool = None

      i = 0
      for cmd in cmds:
        i = i + 1
        if i < len(cmds):
          nextStdIn, hStdOut = win32popen.CreatePipe(1, 1)
        else:
          # very last process
          nextStdIn = None

          if sapi.server.inheritableOut:
            # send child output to standard out
            hStdOut = win32popen.MakeInheritedHandle(win32popen.FileObject2File(sys.stdout),0)
            ehandle = None
          else:
            ehandle = win32event.CreateEvent(None, 1, 0, None)
            x, hStdOut = win32popen.MakeSpyPipe(None, 1, (sapi.server.file(),), ehandle)

        command = win32popen.CommandLine(cmd[0], cmd[1:])
        phandle, pid, thandle, tid = win32popen.CreateProcess(command, hStdIn, hStdOut, None)
        hStdIn = nextStdIn

    return _pipe(win32popen.File2FileObject(handle, 'wb'), phandle, ehandle)

  # flush the stdio buffers since we are about to change the FD under them
  sys.stdout.flush()
  sys.stderr.flush()

  prev_r, parent_w = os.pipe()

  null = os.open('/dev/null', os.O_RDWR)

  child_pids = []

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
    child_pids.append(pid)

    # we don't need these any more
    os.close(prev_r)
    os.close(w)

    # the read channel of this pipe will feed into to the next command
    prev_r = r

  # no longer needed
  os.close(null)

  # done with most of the commands. set up the last command to write to "out"
  if not hasattr(out, 'fileno'):
    r, w = os.pipe()

  pid = os.fork()
  if not pid:
    # in the child (the last command)

    # hook up stdin to the "read" channel
    os.dup2(prev_r, 0)

    # hook up stdout to "out"
    if hasattr(out, 'fileno'):
      if out.fileno() != 1:
        os.dup2(out.fileno(), 1)
        out.close()

    else:
      # "out" can't be hooked up directly, so use a pipe and a thread
      os.dup2(w, 1)
      os.close(r)
      os.close(w)

    # close these extra descriptors
    os.close(prev_r)
    os.close(parent_w)

    # run the last command
    try:
      os.execvp(cmds[-1][0], cmds[-1])
    except:
      pass

    sys.exit(127)

  child_pids.append(pid)
  # not needed any more
  os.close(prev_r)

  if not hasattr(out, 'fileno'):
    os.close(w)
    thread = _copy(r, out)
    thread.start()
  else:
    thread = None

  # write into the first pipe, wait on the final process
  return _pipe(os.fdopen(parent_w, 'w'), child_pids, thread=thread)

class _copy(threading.Thread):
  def __init__(self, srcfd, destfile):
    self.srcfd = srcfd
    self.destfile = destfile
    threading.Thread.__init__(self)

  def run(self):
    try:
      while 1:
        s = os.read(self.srcfd, 1024)
        if not s:
          break
        self.destfile.write(s)
    finally:
      os.close(self.srcfd)

class _pipe:
  "Wrapper for a file which can wait() on a child process at close time."

  def __init__(self, file, child_pid, done_event = None, thread = None):
    self.file = file
    self.child_pid = child_pid
    if sys.platform == "win32":
      if done_event:
        self.wait_for = (child_pid, done_event)
      else:
        self.wait_for = (child_pid,)
    else:
      self.thread = thread

  def eof(self):
    ### should be calling file.eof() here instead of file.close(), there
    ### may be data in the pipe or buffer after the process exits
    if sys.platform == "win32":
      r = win32event.WaitForMultipleObjects(self.wait_for, 1, 0)
      if r == win32event.WAIT_OBJECT_0:
        self.file.close()
        self.file = None
        return win32process.GetExitCodeProcess(self.child_pid)
      return None

    if self.thread and self.thread.isAlive():
      return None

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
      if sys.platform == "win32":
        win32event.WaitForMultipleObjects(self.wait_for, 1, win32event.INFINITE)
        return win32process.GetExitCodeProcess(self.child_pid)
      else:
        if self.thread:
          self.thread.join()
	if type(self.child_pid) == type([]):
          for pid in self.child_pid:
            exit = os.waitpid(pid, 0)[1]
          return exit
	else:
            return os.waitpid(self.child_pid, 0)[1]
    return None

  def __getattr__(self, name):
    return getattr(self.file, name)

  def __del__(self):
    self.close()
