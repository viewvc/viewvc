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
#
# This is a Version Control lib driver for locally accessible cvs-repositories.
#
# -----------------------------------------------------------------------
"""
This is a Version Control library driver for locally accessible cvs-repositories.
"""

from vclib import Repository, Versfile, Versdir, Revision, ReposNotFound, ItemNotFound, DIR , FILE
import os
import os.path
import string
import re
import exceptions
import rcsparse
import cStringIO


class InfoSink(rcsparse.Sink):

  def __init__(self, target):
    self.target = target
    self.updr = 0
    self.upri = 0

  def set_head_revision(self, revision):
    self.target.head = revision

  def set_principal_branch(self, branch_name):
    self.target.branch = revision

  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    if self.target.head == revision:
      self.target.age = timestamp
      self.target.author = author
      self.updr = 1
      if self.upri:
        raise RCSStopParser()
        
  def set_revision_info(self, revision, log, text):
    if self.target.head == revision:
      self.target.log = log
      self.upri = 1
      if self.updr:
        raise RCSStopParser()
        
class TreeSink(rcsparse.Sink):
  d_command = re.compile('^d(\d+)\\s(\\d+)')
  a_command = re.compile('^a(\d+)\\s(\\d+)')
  
  def __init__(self, target):
    self.target = target
    self.tree = { }
    self.tags = { }
  
  def set_head_revision(self, revision):
    self.target.head = revision
  
  def set_principal_branch(self, branch_name):
    self.target.branch = revision
  
  def define_tag(self, name, revision):
    if self.tree.has_key(revision):
      self.tree[revision].tags.append(name)
    else:
      if revision in self.tags:
        self.tags[revision].append(name)
      else:
        self.tags[revision] = [name]
#      self.tree[revision] = Revision(self.target, revision)
#      self.tree[revision].tags = [name]
    
  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    if self.target.head == revision:
      self.target.age = timestamp
      self.target.author = author
    if self.tree.has_key(revision):
      rev = self.tree[revision]
    else:
      rev = Revision(self.target, revision)
      self.tree[revision] = rev
    rev.date = timestamp
    rev.author = author
    rev.branches = branches
    rev.state = state
    rev.previous = next
    if revision in self.tags:
      rev.tags = self.tags[revision]
      del self.tags[revision]
    else:
      rev.tags = []
    
  def set_revision_info(self, revision, log, text):
    if self.tree.has_key(revision):
      rev = self.tree[revision]
    else:
      rev = Revision(self.target, revision)
      self.tree[revision] = rev
    rev.log = log
    if self.target.head == revision:
      self.target.log = log
    else:
      lines = text.splitlines()
      idx = 0
      added = 0
      deled = 0
      while idx < len(lines):
        command = lines[idx]
        dmatch = self.d_command.match(command)
        idx = idx + 1
        if dmatch:
          deled = deled + string.atoi(dmatch.group(2))
        else:
          amatch = self.a_command.match(command)
          if amatch:
            count = string.atoi(amatch.group(2))
            added = added + count
            idx = idx + count
          else:
            raise "error while parsing deltatext: %s" % command
      rev.changes = (deled, added)

  def gobranch(self, rev):
    rev.changes = "+%d -%d lines" % (rev.changes[1], rev.changes[0])
    if rev.previous != None:
      self.gobranch(self.tree[rev.previous])
    for x in rev.branches:
      self.gobranch(self.tree[x])

  def gotree(self, rev):
    if rev.previous != None:
      rev.changes = "+%d -%d lines" % self.tree[rev.previous].changes
      self.gotree(self.tree[rev.previous])
    else:
      rev.changes = ""
    for x in rev.branches:
      self.gobranch(self.tree[x])    

  def parse_completed(self):
    self.gotree(self.tree[self.target.head])    


class StreamText:
  d_command = re.compile('^d(\d+)\\s(\\d+)')
  a_command = re.compile('^a(\d+)\\s(\\d+)')

  def __init__(self, text, head):
    self.next_revision(head)
    self.text = string.split(text, "\n")

  def command(self, cmd):
    adjust = 0
    add_lines_remaining = 0
    diffs = string.split(cmd, "\n")
    if diffs[-1] == "":
      del diffs[-1]
    if len(diffs) == 0:
      return
    if diffs[0] == "":
      del diffs[0]
    for command in diffs:
      if add_lines_remaining > 0:
        # Insertion lines from a prior "a" command
        self.text.insert(start_line + adjust, command)
        add_lines_remaining = add_lines_remaining - 1
        adjust = adjust + 1
        continue
      dmatch = self.d_command.match(command)
      amatch = self.a_command.match(command)
      if dmatch:
        # "d" - Delete command
        start_line = string.atoi(dmatch.group(1))
        count      = string.atoi(dmatch.group(2))
        begin = start_line + adjust - 1
        del self.text[begin:begin + count]
        adjust = adjust - count
      elif amatch:
        # "a" - Add command
        start_line = string.atoi(amatch.group(1))
        count      = string.atoi(amatch.group(2))
        add_lines_remaining = count
      else:
        raise RuntimeError, 'Error parsing diff commands'
  
  def next_revision(self, revision):
    #print "Revision: %s"% revision
    pass

def secondnextdot(s, start):
  # find the position the second dot after the start index.
  return string.find(s, '.', string.find(s, '.', start) + 1)


class COSink(rcsparse.Sink):
  
  def __init__(self, target):
    self.target = target
  
  def set_head_revision(self, revision):
    self.head = revision
    self.position = 0
    self.path = [revision]
    self.buffer = { }
    self.sstext = None
  
  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    if self.target.rev==revision:
      self.target.date = timestamp
      self.target.author = author
      self.target.branches = branches
      self.target.state = state
      self.target.previous = next
    if self.path[-1] == self.target.rev:
      return
    if revision == self.path[-1]:
      if self.target.rev[:len(revision)+1] == revision + '.':
        # Branch ?
        for x in branches:
          if self.target.rev[:secondnextdot(self.target.rev, len(revision))] \
             == x[:secondnextdot(self.target.rev, len(revision))]:
            self.path.append(x)
            if x in self.buffer:
              i = self.buffer[x]
              del self.buffer[x]
              self.define_revision(x, 0, "", "", i[0], i[1])  
            return
        else:
          print revision
          print branches
          print next
          raise " %s revision doesn't exist " % self.target.rev
      else:
        # no => next 
        self.path.append(next)
        if self.buffer.has_key(next):
          self.path.append(next)
          if x in self.buffer:
            i = self.buffer[next]
            del self.buffer[next]
            self.define_revision(next, 0, "", "", i[0], i[1])
    else:
      self.buffer[revision] = (branches, next)
        
  def tree_completed(self):
    if self.path[-1] != self.target.rev:
      raise "Error Incomplete path"
    #print self.path
    self.buffer = { }

  def set_revision_info(self, revision, log, text):
    if revision == self.target.rev:
      self.target.log = log
    if revision in self.path:
      if self.path[self.position] == revision:
        if revision == self.head:
          self.sstext = StreamText(text, self.head)
        else:
          self.sstext.next_revision(revision)
          self.sstext.command(text)
        while self.position + 1 < len(self.path):
          self.position = self.position + 1
          x= self.path[self.position]
          if x not in self.buffer:
            break
          self.sstext.next_revision(x)
          self.sstext.command(self.buffer[x])
          del self.buffer[x]
      else:
        self.buffer[revision] = text

  def parse_completed(self):
    if self.buffer != {}:
      raise "Error buffer not emptied"


class CVSRepository(Repository):
  def __init__(self, name, basepath, show_CVSROOT=0 ):
    self.name = name
    self.basepath = basepath
    self.show_CVSROOT = show_CVSROOT
    if self.basepath[-1:] != os.sep:
      self.basepath = self.basepath + os.sep
    # Some checking:
    # Is the basepath a real directory ?
    if not os.path.isdir(self.basepath):
      raise ReposNotFound(self.basepath)
    # do we have a CVSROOT as an immediat subdirectory ?
    if not os.path.isdir(self.basepath + "CVSROOT/"):
      raise ReposNotFound(self.basepath)
      
  def _getpath(self, pathname):
    if pathname != []:
      if (pathname[0] == "CVSROOT") and( self.show_CVSROOT == 0):
        raise ItemNotFound(pathname)
    return self.basepath + string.join(pathname, os.sep)

  def _getrcsname(self, filename):
    if filename[-2:] == ',v':
      return filename
    else:
      return filename + ',v'  

# API as of revision 1.5 

  def getitem(self, path_parts):
    path = self._getpath(path_parts)
    if os.path.isdir(path):
      return Versdir(self, path_parts)
    if os.path.isfile(self._getrcsname(path)):
      return Versfile(self, path_parts)
    raise ItemNotFound(path) 
    
  def getitemtype(self, path_parts):
    path = self._getpath(path_parts)
    if os.path.isdir(path):
      return DIR
    if os.path.isfile(path):
      return FILE
    raise ItemNotFound(path)
  
  # Private methods ( accessed by Versfile and Revision )

  def _getvf_files(self, path_parts):
    "Return a dictionary of versioned files. (name : Versfile)"
    h = os.listdir(self._getpath(path_parts))
    g = { }
    for i in h:
      if os.path.isfile(self._getrcsname(self._getpath(path_parts + [i]))):
      	g[i] = Versfile(self, path_parts + [i])
    return g

  def _getvf_subdirs(self, path_parts):
    "Return a dictionary of subdirectories. (name : Versdir)"
    h = os.listdir(self._getpath(path_parts))
    if ( not self.show_CVSROOT ):
      if (path_parts == []):
        del h[h.index("CVSROOT")]
    g = { }
    for i in h:
      
      p = self._getpath(path_parts + [i])
      if os.path.isdir(p):
    	  g[i] = Versdir(self, path_parts + [i]) 
    return g
  
  # Private methods
  def _getvf_info(self, target, path_parts):
    path = self._getrcsname(self._getpath(path_parts))
    if not os.path.isfile(path):
      raise "Unknown file: %s " % path
    try:
      rcsparse.Parser().parse(open(path), InfoSink(target))
    except RCSStopParser:
      pass

  def _getvf_tree(self,versfile):
    path = self._getrcsname(self._getpath(versfile.path))
    if not os.path.isfile(path):
      raise "Unknown file: %s " % path
    sink = TreeSink(versfile)
    rcsparse.Parser().parse(open(path), sink)
    return sink.tree

  def _getvf_cofile(self, target, path_parts):
    path = self._getrcsname(self._getpath(path_parts))
    if not os.path.isfile(path):
      raise "Unknown file: %s " % path
    sink = COSink(target)
    rcsparse.Parser().parse(open(path), sink)
    return cStringIO.StringIO(string.join(sink.sstext.text, "\n"))
