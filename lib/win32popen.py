# Utilities for controlling processes and pipes on win32
# Russ Yanofsky (rey4@columbia.edu)

import os, sys, traceback, string, thread
import win32process, win32security, win32pipe, win32con
import win32event, win32file, win32api, winerror
import pywintypes, msvcrt

# Buffer size for spooling
SPOOL_BYTES = 4096

# Use non-blocking IO for spooling?
NBIO = 0

# Number of worker threads to use for non-blocking I/O
NBIO_THREADS = 5

# File object to write error messages
SPOOL_ERROR = sys.stderr 
#SPOOL_ERROR = open("m:/temp/error.txt", "wt")

def CommandLine(command, args):
  """Convert an executable path and a sequence of arguments into a command
  line that can be passed to CreateProcess"""
  
  cmd = "\"" + string.replace(command, "\"", "\"\"") + "\"";
  for arg in args:
    cmd += " \"" + string.replace(arg, "\"", "\"\"") + "\""
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
       
def CreatePipe(readInheritable, readBlocks, writeInheritable, writeBlocks):
  """Create a new pipe specifying whether the read and write ends are
  inheritable and whether they should be created for blocking or nonblocking
  I/O."""
  
  # This special case is not strictly neccessary under NT, but it allows the
  # function to be at least semi-functional on Win9x, which does not implement
  # CreateNamedPipe
  if readBlocks and writeBlocks:
    r, w = win32pipe.CreatePipe(None, SPOOL_BYTES)
    if readInheritable:
      r = MakeInheritedHandle(r)
    if writeInheritable:
      w = MakeInheritedHandle(w)
    return r, w

  name = "\\\\.\\pipe\\" + "win32popen_" + str(thread.get_ident()) + "_" + str(UniqueNum())

  if readBlocks:
    pb = 0
  else:
    pb = win32file.FILE_FLAG_OVERLAPPED

  if writeBlocks:
    fb = 0
  else:
    fb = win32file.FILE_FLAG_OVERLAPPED

  sa = win32security.SECURITY_ATTRIBUTES()
  sa.bInheritHandle = 1
  
  if readInheritable:
    readSa = sa
  else:
    readSa = None
    
  if writeInheritable:
    writeSa = sa
  else:
    writeSa = None

  r = win32pipe.CreateNamedPipe(name,
    win32pipe.PIPE_ACCESS_INBOUND | pb,
    win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_WAIT,
    1, SPOOL_BYTES, SPOOL_BYTES, win32event.INFINITE, readSa);

  w = win32file.CreateFile(name, win32file.GENERIC_WRITE,
    0, writeSa, win32file.OPEN_EXISTING, 
    win32file.FILE_FLAG_SEQUENTIAL_SCAN | fb, None);

  return r, w

def File2FileObject(pipe, mode):
  """Make a C stdio file object out of a win32 file handle"""
  if mode.find('r') >= 0:
    wmode = os.O_RDONLY
  elif mode.find('w') >= 0:
    wmode = os.O_WRONLY
  if mode.find('b') >= 0:
    wmode = wmode | os.O_BINARY
  if mode.find('t') >= 0:
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
  flags = win32con.DUPLICATE_SAME_ACCESS;
  proc = win32api.GetCurrentProcess()
  if replace: flags |= win32con.DUPLICATE_CLOSE_SOURCE
  newhandle = win32api.DuplicateHandle(proc,handle,proc,0,0,flags)
  if replace: handle.Detach() # handle was already deleted by the last call
  return newhandle

def MakeInheritedHandle(handle, replace = 1):
  """Turn a private handle into an inherited one."""
  flags = win32con.DUPLICATE_SAME_ACCESS;
  proc = win32api.GetCurrentProcess()
  if replace: flags |= win32con.DUPLICATE_CLOSE_SOURCE
  newhandle = win32api.DuplicateHandle(proc,handle,proc,0,1,flags)
  if replace: handle.Detach() # handle was deleted by the last call
  return newhandle

def MakeSpyPipe(readInheritable, writeInheritable, outFiles = None, doneEvent = None):
  """Return read and write handles to a pipe that asynchronously writes all of
  its input to the files in the outFiles sequence. doneEvent can be None, or a
  a win32 event handle that will be set when the write end of pipe is closed.
  """

  if outFiles is None:
    return CreatePipe(readInheritable, 1, writeInheritable, 1)

  r, writeHandle = CreatePipe(0, not NBIO, writeInheritable, 1)
  if readInheritable is None:
    readHandle, w = None, None
  else:
    readHandle, w = CreatePipe(readInheritable, 1, 0, not NBIO)
  
  if NBIO:
    NbSpool(r, w, outFiles, doneEvent)
  else:
    thread.start_new_thread(SpoolWorker, (r, w, outFiles, doneEvent))

  return readHandle, writeHandle

def SpoolWorker(srcHandle, destHandle, outFiles, doneEvent):
  """Thread entry point for blocking implementation of MakeSpyPipe"""
  try:
    buffer = win32file.AllocateReadBuffer(SPOOL_BYTES)
  
    while 1:
      try:
        hr, data = win32file.ReadFile(srcHandle, buffer)
        if hr != 0:
          raise "win32file.ReadFile returned %i, '%s'" % (hr, data)
        elif len(data) == 0:
          break
      except pywintypes.error, e:
        if e.args[0] == winerror.ERROR_BROKEN_PIPE:      
          break
        else:
          raise e
  
      for f in outFiles:
        f.write(data)
  
      if destHandle:
        hr, bytes = win32file.WriteFile(destHandle, data)
        if hr != 0 or bytes != len(data):
          raise "win32file.WriteFile() passed %i bytes and returned %i, %i" % (len(data), hr, bytes)
  
    srcHandle.Close()
  
    if doneEvent:
      win32event.SetEvent(doneEvent)
  
    if destHandle:
      destHandle.Close()   
      
  except:
    info = sys.exc_info()
    print >> SPOOL_ERROR, string.join(apply(traceback.format_exception, info), ''); SPOOL_ERROR.flush()
    del info  

class NbSpool:
  """Spooler class which copies data from a nonblocking source handle
  (srcHandle) to a non blocking destination handle (destHandle),
  writes the data to 0 or more file objects (outFiles), and sets an
  event (eofEvent) when there is no more data at the source.""" 

  def __init__(self, srcHandle, destHandle, outFiles = (), eofEvent = None):
    self.src = NbSpool.Operation(self, srcHandle, 1)
    self.readBuffer = win32file.AllocateReadBuffer(SPOOL_BYTES)
        
    if destHandle:
      self.dest = NbSpool.Operation(self, destHandle, 0)
      self.writeBuffer = win32file.AllocateReadBuffer(SPOOL_BYTES)

    self.outFiles = outFiles
    self.eofEvent = eofEvent

    AddRef(self)
    self.lock = win32event.CreateMutex(None, 0, None)
    self.src.read(self.readBuffer)
   
  def onComplete(self):
    r = win32event.WaitForSingleObject(uniqueLock, win32event.INFINITE)
    if r != win32event.WAIT_OBJECT_0:
      raise "WaitForSingleObject() returned " + str(r)
  
    try:
      src, dest = self.getOp('src'), self.getOp('dest')

      #print >> SPOOL_ERROR, "  read ", src,  "| write ", dest; SPOOL_ERROR.flush()
      #print >> SPOOL_ERROR, "  read pending:", src and src.pending, "| write pending:", dest and dest.pending; SPOOL_ERROR.flush()

      if src:
        if not (src.pending or (dest and dest.pending)):
          if dest:
            self.readBuffer, self.writeBuffer = self.writeBuffer, self.readBuffer
            dest.write(self.writeBuffer[:src.bytes])
          src.read(self.readBuffer)
      elif dest and not dest.pending:
        self.dest.close()
      
      src, dest = self.getOp('src'), self.getOp('dest')
      if not (src or dest):
        RemoveRef(self)
    
    finally:
      win32event.ReleaseMutex(uniqueLock)

  def getOp(self, name):
    x = getattr(self, name, None)
    if x is None or hasattr(x, 'handle'):
      return x
    del x.parent, x
    delattr(self, name)
    return None

  def __del__(self):
    #print >> SPOOL_ERROR, "Delteating Spool"; SPOOL_ERROR.flush()
    pass

  class Operation:
    """Inner class which handles IO completion events and performs reads and
    writes"""
    
    def __init__(self, parent, handle, readOp):
      global NbPort
      self.parent = parent
      self.handle = handle
      self.readOp = readOp
      self.ol = pywintypes.OVERLAPPED()
      self.ol.object = self
      self.pending = 0
      
      if not win32file.CreateIoCompletionPort(handle, NbPort, 0, 1):
        raise "CreateIoCompletionPort failed"
      
    def onIo(self, rc, bytes):
      if rc == winerror.ERROR_BROKEN_PIPE:
        self.close()
      elif rc != 1:
        raise "GetQueuedCompletionStatus returned unknown value", rc
  
      self.bytes = bytes
      self.pending = 0
  
      if self.readOp:
        for o in self.parent.outFiles:
          o.write(str(self.parent.readBuffer[:bytes]))

      self.parent.onComplete()
      
    def read(self, buffer):
      try:
        hr, buffer = win32file.ReadFile(self.handle, buffer, self.ol)
        self.pending = 1
        #print >> SPOOL_ERROR, "ReadFile", id(self), "returned", hr; SPOOL_ERROR.flush()
      except pywintypes.error, e:
        #print >> SPOOL_ERROR, "ReadFile", id(self), "threw", e; SPOOL_ERROR.flush()
        self.close()
        if e.args[0] != winerror.ERROR_BROKEN_PIPE:
          raise e
  
    def write(self, buffer):    
      hr, bytes = win32file.WriteFile(self.handle, buffer, self.ol)
      self.pending = 1
      #print >> SPOOL_ERROR, "WriteFile()", id(self), "returned (%i,%i)" % (hr, bytes); SPOOL_ERROR.flush()
  
    def close(self):
      #print >> SPOOL_ERROR, "Closing NbSpool.Operation %i" % id(self); SPOOL_ERROR.flush()
      
      if self.readOp and self.parent.eofEvent:
        win32event.SetEvent(self.parent.eofEvent)
        
      self.handle.Close()
      del self.handle, self.ol
    
    def __del__(self):
      #print >> SPOOL_ERROR, "Delteating NbSpool.Operation %i" % id(self); SPOOL_ERROR.flush()
      pass
      
def NbSpoolWorker(i):
  global NbPort
  try:
    while 1:
      rc, bytesRead, key, overlapped = win32file.GetQueuedCompletionStatus(NbPort, win32event.INFINITE)
      #print >> SPOOL_ERROR, "RECEIVED EVENT rc =", rc, "bytesRead =", bytesRead, "handler =", id(overlapped.object); SPOOL_ERROR.flush()
      # defensively keep loop going even if an io handler throws an exception
      try:
        overlapped.object.onIo(rc, bytesRead)
      except:
        info = sys.exc_info()
        print >> SPOOL_ERROR, string.join(apply(traceback.format_exception, info), ''); SPOOL_ERROR.flush()
        del info
  except:
    info = sys.exc_info()
    print >> SPOOL_ERROR, "Worker %i is dead!" % i; SPOOL_ERROR.flush()
    print >> SPOOL_ERROR, string.join(apply(traceback.format_exception, info), ''); SPOOL_ERROR.flush()
    del info

if NBIO:
  NbPort = win32file.CreateIoCompletionPort(win32file.INVALID_HANDLE_VALUE, None, 0, 1)
  for i in range(NBIO_THREADS):
    thread.start_new_thread(NbSpoolWorker, (i,))

# AddRef and RemoveRef can be used to momentarily increment and decrement
# the reference count on a python object to prevent it from being garbage
# collected. This can be needed when the only reference to a python object
# is passed to some non-python API, for example through a PyOVERLAPPED
# object's "object" member.

refCollection = {}

def AddRef(o):
  global refLock, refNextIndex, refCollection

  if hasattr(o, 'refIndex'):
    raise 'Object already has reference set'

  o.refIndex = UniqueNum()
  refCollection[o.refIndex] = o

  #print >> SPOOL_ERROR, "Adding reference", o.refIndex, "to object", id(o); SPOOL_ERROR.flush()
    
def RemoveRef(o):
  global refCollection
  del refCollection[o.refIndex]
  #print >> SPOOL_ERROR, "Removing reference from object", id(0), "index", o.refIndex; SPOOL_ERROR.flush()
  del o.refIndex

# UniqueNum provides an integer guaranteed to be unique within this possibly
# multithreaded python environment. It would be more efficient if it were
# implemented with the Win32 InterlockedIncrement() function, but for some
# reason that function is not exposed by the python win32 extensions

uniqueLock = win32event.CreateMutex(None, 0, None)
uniqueNext = 0;

def UniqueNum():
  global uniqueLock, uniqueNext

  r = win32event.WaitForSingleObject(uniqueLock, win32event.INFINITE)
  if r <> win32event.WAIT_OBJECT_0:
    raise "WaitForSingleObject returned " + str(r)
    
  try:
    i = uniqueNext
    uniqueNext += 1
    return i
   
  finally:
    win32event.ReleaseMutex(uniqueLock)
