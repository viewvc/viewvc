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

from vclib import Repository, Versfile, Revision
import os
import os.path
import string
import re
import exceptions
import rcsparse
import cStringIO
class InfoSink(rcsparse.Sink):

  def __init__(self,target):
    self.target=target
    self.updr=0
    self.upri=0

  def set_head_revision(self, revision):
    self.target.__dict__["head"]=revision

  def set_principal_branch(self, branch_name):
    self.target.__dict__["branch"]=revision

  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    if self.target.__dict__["head"]==revision:
      self.target.__dict__["age"]=timestamp
      self.target.__dict__["author"]=author
      self.updr=1
      if self.upri:
        raise RCSStopParser()
        
  def set_revision_info(self, revision, log, text):
    if self.target.__dict__["head"]==revision:
      self.target.__dict__["log"]=log
      self.upri=1
      if self.updr:
        raise RCSStopParser()
        
class TreeSink(rcsparse.Sink):
  d_command   = re.compile('^d(\d+)\\s(\\d+)')
  a_command   = re.compile('^a(\d+)\\s(\\d+)')
  
  def __init__(self,target):
    self.target=target
    self.tree={}
    self.tags={}
  
  def set_head_revision(self, revision):
    self.target.__dict__["head"]=revision
  
  def set_principal_branch(self, branch_name):
    self.target.__dict__["branch"]=revision
  
  def define_tag(self, name, revision):
    if self.tree.has_key(revision):
      self.tree[revision].__dict__["tags"].append(name)
    else:
      if revision in self.tags:
        self.tags[revision].append(name)
      else:
        self.tags[revision]=[name]
#      self.tree[revision]=Revision(self.target,revision)
#      self.tree[revision].__dict__["tags"]=[name]
    
  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    if self.target.__dict__["head"]==revision:
      self.target.__dict__["age"]=timestamp
      self.target.__dict__["author"]=author
    if self.tree.has_key(revision):
      rev=self.tree[revision]
    else:
      rev=Revision(self.target,revision)
      self.tree[revision]=rev
    rev.__dict__["date"]=timestamp
    rev.__dict__["author"]=author
    rev.__dict__["branches"]=branches
    rev.__dict__["state"]=state
    rev.__dict__["previous"]=next
    if revision in self.tags:
      rev.__dict__["tags"]=self.tags[revision]
      del self.tags[revision]
    else:
      rev.__dict__["tags"]=[]
    
  def set_revision_info(self, revision, log, text):
    if self.tree.has_key(revision):
      rev=self.tree[revision]
    else:
      rev=Revision(self.target,revision)
      self.tree[revision]=rev
    rev.__dict__["log"]=log
    if self.target.__dict__["head"]==revision:
      self.target.__dict__["log"]=log
    else:
      lines=text.splitlines()
      idx=0
      added=0
      deled=0
      while idx < len(lines):
        command=lines[idx]
        dmatch = self.d_command.match(command)
        idx = idx +1
        if dmatch:
          deled=deled+string.atoi(dmatch.group(2))
        else:
          amatch = self.a_command.match(command)
          if amatch:
            count  = string.atoi(amatch.group(2))
            added = added+ count
            idx = idx +count
          else:
            raise "error while parsing deltatext: %s" % command
      rev.__dict__["changes"]= (deled,added)
  def gobranch(self,rev):
    rev.__dict__["changes"]="+%d -%d lines" % (rev.__dict__["changes"][1],rev.__dict__["changes"][0])
    if rev.__dict__["previous"]!=None:
      self.gobranch(self.tree[rev.__dict__["previous"]])
    for x in rev.__dict__["branches"]:
      self.gobranch(self.tree[x])
  def gotree(self,rev):
    if rev.__dict__["previous"]!=None:
      rev.__dict__["changes"]="+%d -%d lines" % self.tree[rev.__dict__["previous"]].__dict__["changes"]
      self.gotree(self.tree[rev.__dict__["previous"]])
    else:
      rev.__dict__["changes"]=""
    for x in rev.__dict__["branches"]:
      self.gobranch(self.tree[x])    
  def parse_completed(self):
    self.gotree(self.tree[self.target.__dict__["head"]])    
class StreamText:
  d_command   = re.compile('^d(\d+)\\s(\\d+)')
  a_command   = re.compile('^a(\d+)\\s(\\d+)')
  def __init__(self,text,head):
    self.next_revision(head)
    self.text=string.split(text,"\n")
  def command(self,cmd):
    adjust = 0
    add_lines_remaining = 0
    diffs = string.split(cmd,"\n")
    if diffs[-1]=="":
      del diffs[-1]
    if len(diffs)==0:
      return
    if diffs[0]=="":
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
  
  def next_revision(self,revision):
    #print "Revision: %s"% revision
    pass

def secondnextdot(s,start):
  # find the position the second dot after the start index.
  return string.find(s,'.',string.find(s, '.', start)+1)

class COSink(rcsparse.Sink):
  
  def __init__(self,target):
    self.target=target
  
  def set_head_revision(self, revision):
    self.head=revision
    self.position=0
    self.path=[revision]
    self.buffer={}
    self.sstext=None
  
  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    if self.target.rev==revision:
      self.target.__dict__["date"]=timestamp
      self.target.__dict__["author"]=author
      self.target.__dict__["branches"]=branches
      self.target.__dict__["state"]=state
      self.target.__dict__["previous"]=next
    if self.path[-1]==self.target.rev:
      return
    if revision==self.path[-1]:
      if self.target.rev[:len(revision)+1]==revision+'.':
        # Branch ?
        for x in branches:
          if self.target.rev[:secondnextdot(self.target.rev,len(revision))]==x[:secondnextdot(self.target.rev,len(revision))]:
            self.path.append(x)
            if x in self.buffer:
              i=self.buffer[x]
              del self.buffer[x]
              self.define_revision(x,0,"","",i[0],i[1])  
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
            i=self.buffer[next]
            del self.buffer[next]
            self.define_revision(next,0,"","",i[0],i[1])
    else:
      self.buffer[revision]=(branches,next)
      
        
  def tree_completed(self):
    if self.path[-1]!=self.target.rev:
      raise "Error Incomplete path"
    #print self.path
    self.buffer={}      

  def set_revision_info(self, revision, log, text):
    if revision==self.target.rev:
      self.target.__dict__["log"]=log
    if revision in self.path:
      if self.path[self.position]==revision:
        if revision==self.head:
          self.sstext=StreamText(text,self.head)
        else:
          self.sstext.next_revision(revision)
          self.sstext.command(text)
        while self.position+1<len(self.path):
          self.position = self.position+1
          x= self.path[self.position]
          if x not in self.buffer:
            break
          self.sstext.next_revision(x)
          self.sstext.command(self.buffer[x])
          del self.buffer[x]
      else:
        self.buffer[revision]=text

  def parse_completed(self):
    if self.buffer!={}:
      raise "Error buffer not emptied"
    
class CVSRepository(Repository):
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
  
  # Private methods
  def _getvf_info(self,target, path):
    if not os.path.isfile(path):
      raise "Unknown file: %s " % path
    try:
      rcsparse.Parser().parse(open(path),InfoSink(target))
    except RCSStopParser:
      pass

  def _getvf_tree(self,versfile):
    if not os.path.isfile(versfile.path):
      raise "Unknown file: %s " % versfile.path
    sink=TreeSink(versfile)
    rcsparse.Parser().parse(open(versfile.path),sink)
    return sink.tree

  def _getvf_cofile(self, target, path):
    if not os.path.isfile(path):
      raise "Unknown file: %s " % path
    sink=COSink(target)
    rcsparse.Parser().parse(open(path),sink)
    return cStringIO.StringIO(string.join(sink.sstext.text,"\n"))