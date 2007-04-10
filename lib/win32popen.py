# -*-python-*-
#
# Copyright (C) 1999-2007 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# Utilities for controlling processes and pipes on win32
#
# -----------------------------------------------------------------------

import os, sys, traceback, string, thread
try:
  import win32api
except ImportError, e:
  raise ImportError, str(e) + """

Did you install the Python for Windows Extensions?

   http://sourceforge.net/projects/pywin32/
"""

import win32process, win32pipe, win32con
import win32event, win32file, winerror
import pywintypes, msvcrt

# Buffer size for spooling
SPOOL_BYTES = 4096

# File object to write error messages
SPOOL_ERROR = sys.stderr
#SPOOL_ERROR = open("m:/temp/error.txt", "wt")

def CommandLine(command, args):
  """Convert an executable path and a sequence of arguments into a command
  line that can be passed to CreateProcess"""

  cmd = "\"" + string.replace(command, "\"", "\"\"") + "\""
  for arg in args:
    cmd = cmd + " \"" + string.replace(arg, "\"", "\"\"") + "\""
  return cmd

def CreateProcess(cmd, hStdInput, hStdOutput, hStdError):
  """Creates a new process which uses the specified handles for its standard
  input, output, and error. The handles must be inheritable. 0 can be passed
  as a special handle indicating that the process should inherit the current
  process's input, output, or error streams, and None can be passed to discard
  the child process's output or to prevent it from reading any input."""

  # initialize new process's startup info
  si = win32process.STARTUPINFO()
  si.dwFlags = win32process.STARTF_USESTDHANDLES

  if hStdInput == 0:
    si.hStdInput = win32api.GetStdHandle(win32api.STD_INPUT_HANDLE)
  else:
    si.hStdInput = hStdInput

  if hStdOutput == 0:
    si.hStdOutput = win32api.GetStdHandle(win32api.STD_OUTPUT_HANDLE)
  else:
    si.hStdOutput = hStdOutput

  if hStdError == 0:
    si.hStdError = win32api.GetStdHandle(win32api.STD_ERROR_HANDLE)
  else:
    si.hStdError = hStdError

  # create the process
  phandle, pid, thandle, tid = win32process.CreateProcess \
  ( None,                            # appName
    cmd,                             # commandLine
    None,                            # processAttributes
    None,                            # threadAttributes
    1,                               # bInheritHandles
    win32con.NORMAL_PRIORITY_CLASS,  # dwCreationFlags
    None,                            # newEnvironment
    None,                            # currentDirectory
    si                               # startupinfo
  )

  if hStdInput and hasattr(hStdInput, 'Close'):
    hStdInput.Close()

  if hStdOutput and hasattr(hStdOutput, 'Close'):
    hStdOutput.Close()

  if hStdError and hasattr(hStdError, 'Close'):
    hStdError.Close()

  return phandle, pid, thandle, tid

def CreatePipe(readInheritable, writeInheritable):
  """Create a new pipe specifying whether the read and write ends are
  inheritable and whether they should be created for blocking or nonblocking
  I/O."""

  r, w = win32pipe.CreatePipe(None, SPOOL_BYTES)
  if readInheritable:
    r = MakeInheritedHandle(r)
  if writeInheritable:
    w = MakeInheritedHandle(w)
  return r, w

def File2FileObject(pipe, mode):
  """Make a C stdio file object out of a win32 file handle"""
  if string.find(mode, 'r') >= 0:
    wmode = os.O_RDONLY
  elif string.find(mode, 'w') >= 0:
    wmode = os.O_WRONLY
  if string.find(mode, 'b') >= 0:
    wmode = wmode | os.O_BINARY
  if string.find(mode, 't') >= 0:
    wmode = wmode | os.O_TEXT
  return os.fdopen(msvcrt.open_osfhandle(pipe.Detach(),wmode),mode)

def FileObject2File(fileObject):
  """Get the win32 file handle from a C stdio file object"""
  return win32file._get_osfhandle(fileObject.fileno())

def DuplicateHandle(handle):
  """Duplicates a win32 handle."""
  proc = win32api.GetCurrentProcess()
  return win32api.DuplicateHandle(proc,handle,proc,0,0,win32con.DUPLICATE_SAME_ACCESS)

def MakePrivateHandle(handle, replace = 1):
  """Turn an inherited handle into a non inherited one. This avoids the
  handle duplication that occurs on CreateProcess calls which can create
  uncloseable pipes."""

  ### Could change implementation to use SetHandleInformation()...

  flags = win32con.DUPLICATE_SAME_ACCESS
  proc = win32api.GetCurrentProcess()
  if replace: flags = flags | win32con.DUPLICATE_CLOSE_SOURCE
  newhandle = win32api.DuplicateHandle(proc,handle,proc,0,0,flags)
  if replace: handle.Detach() # handle was already deleted by the last call
  return newhandle

def MakeInheritedHandle(handle, replace = 1):
  """Turn a private handle into an inherited one."""

  ### Could change implementation to use SetHandleInformation()...

  flags = win32con.DUPLICATE_SAME_ACCESS
  proc = win32api.GetCurrentProcess()
  if replace: flags = flags | win32con.DUPLICATE_CLOSE_SOURCE
  newhandle = win32api.DuplicateHandle(proc,handle,proc,0,1,flags)
  if replace: handle.Detach() # handle was deleted by the last call
  return newhandle

def MakeSpyPipe(readInheritable, writeInheritable, outFiles = None, doneEvent = None):
  """Return read and write handles to a pipe that asynchronously writes all of
  its input to the files in the outFiles sequence. doneEvent can be None, or a
  a win32 event handle that will be set when the write end of pipe is closed.
  """

  if outFiles is None:
    return CreatePipe(readInheritable, writeInheritable)

  r, writeHandle = CreatePipe(0, writeInheritable)
  if readInheritable is None:
    readHandle, w = None, None
  else:
    readHandle, w = CreatePipe(readInheritable, 0)

  thread.start_new_thread(SpoolWorker, (r, w, outFiles, doneEvent))

  return readHandle, writeHandle

def SpoolWorker(srcHandle, destHandle, outFiles, doneEvent):
  """Thread entry point for implementation of MakeSpyPipe"""
  try:
    buffer = win32file.AllocateReadBuffer(SPOOL_BYTES)

    while 1:
      try:
        #print >> SPOOL_ERROR, "Calling ReadFile..."; SPOOL_ERROR.flush()
        hr, data = win32file.ReadFile(srcHandle, buffer)
        #print >> SPOOL_ERROR, "ReadFile returned '%s', '%s'" % (str(hr), str(data)); SPOOL_ERROR.flush()
        if hr != 0:
          raise "win32file.ReadFile returned %i, '%s'" % (hr, data)
        elif len(data) == 0:
          break
      except pywintypes.error, e:
        #print >> SPOOL_ERROR, "ReadFile threw '%s'" % str(e); SPOOL_ERROR.flush()
        if e.args[0] == winerror.ERROR_BROKEN_PIPE:
          break
        else:
          raise e

      #print >> SPOOL_ERROR, "Writing to %i file objects..." % len(outFiles); SPOOL_ERROR.flush()
      for f in outFiles:
        f.write(data)
      #print >> SPOOL_ERROR, "Done writing to file objects."; SPOOL_ERROR.flush()

      #print >> SPOOL_ERROR, "Writing to destination %s" % str(destHandle); SPOOL_ERROR.flush()
      if destHandle:
        #print >> SPOOL_ERROR, "Calling WriteFile..."; SPOOL_ERROR.flush()
        hr, bytes = win32file.WriteFile(destHandle, data)
        #print >> SPOOL_ERROR, "WriteFile() passed %i bytes and returned %i, %i" % (len(data), hr, bytes); SPOOL_ERROR.flush()
        if hr != 0 or bytes != len(data):
          raise "win32file.WriteFile() passed %i bytes and returned %i, %i" % (len(data), hr, bytes)

    srcHandle.Close()

    if doneEvent:
      win32event.SetEvent(doneEvent)

    if destHandle:
      destHandle.Close()

  except:
    info = sys.exc_info()
    SPOOL_ERROR.writelines(apply(traceback.format_exception, info), '')
    SPOOL_ERROR.flush()
    del info

def NullFile(inheritable):
  """Create a null file handle."""
  if inheritable:
    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.bInheritHandle = 1
  else:
    sa = None

  return win32file.CreateFile("nul",
    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
    win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
    sa, win32file.OPEN_EXISTING, 0, None)
