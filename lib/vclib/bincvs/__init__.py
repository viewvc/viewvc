# -*-python-*-
#
#
# Copyright (C) 1999-2002 The ViewCVS Group. All Rights Reserved.
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

"""Version Control lib driver for locally accessible cvs-repositories.
"""



# ======================================================================
from vclib import Repository, Versfile, Revision
import os
import os.path
import string
import re
import exceptions
import popen

class LogHeader:
  "Hold state from the header portion of an 'rlog' output."
  def __init__(self, filename, head=None, branch=None, taginfo=None):
    self.filename = filename
    self.head = head
    self.branch = branch
    self.taginfo = taginfo


class LogEntry:
  "Hold state for each revision entry in an 'rlog' output."
  def __init__(self, rev, date, author, state, changed, log):
    self.rev = rev
    self.date = date
    self.author = author
    self.state = state
    self.changed = changed
    self.log = log

def parse_log_header(fp):
  """Parse and RCS/CVS log header.

  fp is a file (pipe) opened for reading the log information.

  On entry, fp should point to the start of a log entry.
  On exit, fp will have consumed the separator line between the header and
  the first revision log.

  If there is no revision information (e.g. the "-h" switch was passed to
  rlog), then fp will consumed the file separator line on exit.
  """
  filename = head = branch = None
  taginfo = { }         # tag name => revision

  parsing_tags = 0
  eof = None

  while 1:
    line = fp.readline()
    if not line:
      # the true end-of-file
      eof = _EOF_LOG
      break

    if parsing_tags:
      if line[0] == '\t':
        [ tag, rev ] = map(string.strip, string.split(line, ':'))
        taginfo[tag] = rev
      else:
        # oops. this line isn't tag info. stop parsing tags.
        parsing_tags = 0

    if not parsing_tags:
      if line[:9] == 'RCS file:':
        # remove the trailing ,v
        filename = line[10:-3]
      elif line[:5] == 'head:':
        head = line[6:-1]
      elif line[:7] == 'branch:':
        branch = line[8:-1]
      elif line[:14] == 'symbolic names':
        # start parsing the tag information
        parsing_tags = 1
      elif line == ENTRY_END_MARKER:
        # end of the headers
        break
      elif line == LOG_END_MARKER:
        # end of this file's log information
        eof = _EOF_FILE
        break
      elif line[:6] == 'rlog: ':
        # rlog: filename/goes/here,v: error message
        idx = string.find(line, ':', 6)
        if idx != -1:
          if line[idx:idx+32] == ': warning: Unknown phrases like ':
            # don't worry about this warning. it can happen with some RCS
            # files that have unknown fields in them (e.g. "permissions 644;"
            continue

          # looks like a filename
          filename = line[6:idx]
          if filename[-2:] == ',v':
            filename = filename[:-2]
          return LogHeader(filename), _EOF_ERROR
        # dunno what this is

  return LogHeader(filename, head, branch, taginfo), eof

_re_log_info = re.compile(r'^date:\s+([^;]+);'
                          r'\s+author:\s+([^;]+);'
                          r'\s+state:\s+([^;]+);'
                          r'(\s+lines:\s+([0-9\s+-]+))?\n$')
### _re_rev should be updated to extract the "locked" flag
_re_rev = re.compile(r'^revision\s+([0-9.]+).*')
def parse_log_entry(fp):
  """Parse a single log entry.

  On entry, fp should point to the first line of the entry (the "revision"
  line).
  On exit, fp will have consumed the log separator line (dashes) or the
  end-of-file marker (equals).

  Returns: revision, date (time_t secs), author, state, lines changed,
  the log text, and eof flag (see _EOF_*)
  """
  rev = None
  line = fp.readline()
  if not line:
    return None, _EOF_LOG
  if line[:8] == 'revision':
    match = _re_rev.match(line)
    if not match:
      return None, _EOF_LOG
    rev = match.group(1)

    line = fp.readline()
    if not line:
      return None, _EOF_LOG
    match = _re_log_info.match(line)

  eof = None
  log = ''
  while 1:
    line = fp.readline()
    if not line:
      # true end-of-file
      eof = _EOF_LOG
      break
    if line[:9] == 'branches:':
      continue
    if line == ENTRY_END_MARKER:
      break
    if line == LOG_END_MARKER:
      # end of this file's log information
      eof = _EOF_FILE
      break

    log = log + line

  if not rev or not match:
    # there was a parsing error
    return None, eof

  # parse out a time tuple for the local time
  tm = compat.cvs_strptime(match.group(1))
  try:
   date = int(time.mktime(tm)) - time.timezone
  except OverflowError:
    # it is possible that CVS recorded an "illegal" time, such as those
    # which occur during a Daylight Savings Time switchover (there is a
    # gap in the time continuum). Let's advance one hour and try again.
    # While the time isn't necessarily "correct", recall that the gap means
    # that times *should* be an hour forward. This is certainly close enough
    # for our needs.
    #
    # Note: a true overflow will simply raise an error again, which we won't
    # try to catch a second time.
    tm = tm[:3] + (tm[3] + 1,) + tm[4:]
    date = int(time.mktime(tm)) - time.timezone

  return LogEntry(rev, date,
                  # author, state, lines changed
                  match.group(2), match.group(3), match.group(5),
                  log), eof

def skip_file(fp):
  "Skip the rest of a file's log information."
  while 1:
    line = fp.readline()
    if not line:
      break
    if line == LOG_END_MARKER:
      break

def process_rlog_output(rlog, full_name, view_tag, fileinfo, alltags):
  "Fill in fileinfo and alltags with info from the rlog output."

  # consume each file found in the resulting log
  while 1:

    revwanted = None
    branch = None
    branchpoint = None

    header, eof = parse_log_header(rlog)
    filename = header.filename
    head = header.head
    branch = header.branch
    symrev = header.taginfo

    # the rlog output is done
    if eof == _EOF_LOG:
      break

    if filename:
      # convert from absolute to relative
      if filename[:len(full_name)] == full_name:
        filename = filename[len(full_name)+1:]

      # for a subdir (not Attic files!), use the subdir for a key
      idx = string.find(filename, '/')
      if idx != -1 and filename[:6] != 'Attic/':
        info_key = filename[:idx]
      else:
        info_key = filename

    # an error was found regarding this file
    if eof == _EOF_ERROR:
      fileinfo[info_key] = _FILE_HAD_ERROR
      continue

    # if we hit the end of the log information (already!), then there is
    # nothing we can do with this file
    if eof:
      continue

    if not filename or not head:
      # parsing error. skip the rest of this file.
      skip_file(rlog)
      continue

    if not branch:
      idx = string.rfind(head, '.')
      branch = head[:idx]
    idx = string.rfind(branch, '.')
    if idx == -1:
      branch = '0.' + branch
    else:
      branch = branch[:idx] + '.0' + branch[idx:]

    symrev['MAIN'] = symrev['HEAD'] = branch

    if symrev.has_key(view_tag):
      revwanted = symrev[view_tag]
      if revwanted[:2] == '0.': ### possible?
        branch = revwanted[2:]
      else:
        idx = string.find(revwanted, '.0.')
        if idx == -1:
          branch = revwanted
        else:
          branch = revwanted[:idx] + revwanted[idx+2:]
      if revwanted != branch:
        revwanted = None

      idx = string.rfind(branch, '.')
      if idx == -1:
        branchpoint = ''
      else:
        branchpoint = branch[:idx]

    elif view_tag:
      # the tag wasn't found, so skip this file
      skip_file(rlog)
      continue

    # we don't care about the values -- just the keys. this the fastest
    # way to merge the set of keys
    alltags.update(symrev)

    # read all of the log entries until we find the revision we want
    while 1:

      # fetch one of the log entries
      entry, eof = parse_log_entry(rlog)

      if not entry:
        # parsing error
        if not eof:
          skip_file(rlog)
        break

      rev = entry.rev

      idx = string.rfind(rev, '.')
      revbranch = rev[:idx]

      if not view_tag or (not revwanted and branch == revbranch):
        revwanted = rev

      if rev == revwanted or rev == branchpoint:
        fileinfo[info_key] = (rev, entry.date, entry.log, entry.author,
                              filename, entry.state)

        if rev == revwanted:
          # done with this file now
          if not eof:
            skip_file(rlog)
          break

      # if we hit the true EOF, or just this file's end-of-info, then we are
      # done collecting log entries.
      if eof:
        break

def get_logs(full_name, files, view_tag):

  if len(files) == 0:
    return { }, { }

  fileinfo = { }
  alltags = {           # all the tags seen in the files of this dir
    'MAIN' : '1',
    'HEAD' : '1',
    }

  chunk_size = 100
  while files:
    chunk = files[:chunk_size]
    del files[:chunk_size]

    # prepend the full pathname for each file
    for i in range(len(chunk)):
      chunk[i] = full_name + '/' + chunk[i]

    if not view_tag:
      # NOTE: can't pass tag on command line since a tag may contain "-"
      #       we'll search the output for the appropriate revision
      # fetch the latest revision on the default branch
      chunk = ('-r',) + tuple(chunk)

    rlog = popen.popen(os.path.normpath(os.path.join(cfg.general.rcs_path,'rlog')), chunk, 'r')

    process_rlog_output(rlog, full_name, view_tag, fileinfo, alltags)

    ### it would be nice to verify that we got SOMETHING from rlog about
    ### each file. if we didn't, then it could be that the chunk is still
    ### too large, so we want to cut the chunk_size in half and try again.
    ###
    ### BUT: if we didn't get feedback for some *other* reason, then halving
    ### the chunk size could merely send us into a needless retry loop.
    ###
    ### more work for later...

    status = rlog.close()
    if status:
      raise 'error during rlog: '+hex(status)

  return fileinfo, alltags



class BinCVSRepository:
  def __init__(self,name,basepath):
    self.name=name
    self.basepath=basepath
    if self.basepath[-1:]!=os.sep:
      self.basepath=self.basepath+os.sep
      
  def _getpath(self,pathname):
    return self.basepath+string.join(pathname,os.sep)

  def _getrcsname(self,filename):
    if filename[-2:]==',v':
      return filename
    else:
      return filename+',v'  

  def getfile(self,pathname):
    if os.path.isfile(self._getrcsname(self._getpath(pathname))):
      return Versfile(self,self._getrcsname(self._getpath(pathname)) )
    raise exceptions.IOError("File not found %s in repository %s"% (self._getpath(pathname),self.name) ) 

  def getsubdirs(self,path):
    h=os.listdir(self._getpath(path))
    g=[]
    for i in h:
      if os.path.isdir(self._getpath(path+[i])):
      	g.append(i)
    return g
    
  def getfiles(self,path):
    h=os.listdir(self._getpath(path))
    g={}
    for i in h:
      ci=self._getrcsname(self._getpath(path+[i]))
      if os.path.isfile(ci):
      	g[i]=Versfile(self,ci)
    return g  
  # Private methods ( accessed by Versfile and Revision )
  
  def _getvf_info(self,target, path):
    """
    This method will had to <target> (expect to be an instance of Versfile)
    a certain number of attributes:
    head (string)
    age (int timestamp)
    author (string)
    log
    branch
    ... ( there can be other stuff here)
    
    Developers: method to be overloaded.
    """
    if not os.path.isfile(path):
      raise "Unknown file: %s " % path
    
  def _getvf_tree(self,versfile):
    """
    should return a dictionary of Revisions
    Developers: method to be overloaded.
    """

  def _getvf_properties(self,target,path,revisionnumber):
    """
    Add/update into target's attributes (expected to be an instance of
    Revision) a certain number of attributes:
    rev
    date
    author
    state
    log
    previous revision number
    branches ( a list of revision numbers )
    changes ( string of the form: e.g. "+1 -0 lines" )
    tags
    ... ( there can be other stuff here)
    
    Developers: in the cvs implementation, the method will never be called.
    There is no point in developping this method as  _getvf_tree already
    gets the properties.
    """

  def _getvf_cofile(self, target, path):
    """
    should return a file object representing the checked out revision.
    Notice that _getvf_co can also add the properties in <target> the
    way _getvf_properties does.  

    Developers: method to be overloaded.
    """
    fp = popen.popen('co',
                    ('-p'+rev, os.path.join(repo,file) ), 'r')
    fp.readline()
    fp.readline()
    return fp


