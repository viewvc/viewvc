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
from versionlib import Repository, Versfile, Revision
import os
import os.path
import string
import re
import exceptions
import rcsparse

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
  
  def set_head_revision(self, revision):
    self.target.__dict__["head"]=revision
  
  def set_principal_branch(self, branch_name):
    self.target.__dict__["branch"]=revision
  
  def define_tag(self, name, revision):
    if self.tree.has_key(revision):
      self.tree[revision].__dict__["tags"].append(name)
    else:
      self.tree[revision]=Revision(self.target,revision)
      self.tree[revision].__dict__["tags"]=[name]
    
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
      #rev.getprevious().__dict__["changes"]= "+%d -%d lines" %(deled,added)

class COSink(rcsparse.Sink):
  
  def __init__(self,target):
    self.target=target
  
  def set_head_revision(self, revision):
    self.head=revision
    self.path=[revision]
    self.pathover=0
  
  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    if self.target.rev==revision:
      self.target.__dict__["date"]=timestamp
      self.target.__dict__["author"]=author
      self.target.__dict__["branches"]=branches
      self.target.__dict__["state"]=state
      self.target.__dict__["previous"]=next
      #self.path.append
      
  def set_revision_info(self, revision, log, text):
    pass

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
    try:
      rcsparse.Parser().parse(open(versfile.path),sink)
    except RCSStopParser:
      pass
    return sink.tree

  def _getvf_co(self, target, path):
    if not os.path.isfile(path):
      raise "Unknown file: %s " % versfile.path
    sink=COSink(target)
    try:
      rcsparse.Parser().parse(open(versfile.path),sink)
    except RCSStopParser:
      pass
    return sink.tree
