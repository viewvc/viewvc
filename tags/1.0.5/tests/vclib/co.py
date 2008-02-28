#!/usr/local/bin/python
import sys, os.path
sys.path.append( os.path.normpath(os.path.join(sys.path[0],"..","..","lib")) )
import vclib.ccvs
import popen
def usage():
  print """
  co simulation using vclib!!!
  python co.py <Path to repository> <(relative) Path to file> <revision>
  """
  sys.exit()
def convertpath(s):
  a=(s,'')
  res=[]
  while (a[0]!=''):
    a=os.path.split(a[0])
    res= [a[1]]+res
  return res

def compareco(repo,file,rev):
  a=vclib.ccvs.CVSRepository("lucas",repo)
  f=a.getfile(convertpath(file)) # example: ["kdelibs","po","Attic","nl.po"]
  r=f.tree[rev]
  fp1 = r.checkout()
  fp2 = popen.popen('co',
                    ('-p'+rev, os.path.join(repo,file) ), 'r')
  l1 = fp1.readlines()
  l2 = fp2.readlines()
  ok=1
  for i in range(0,len(l1)-1):
    if l1[i] != l2[i+2]:
      print " Difference in line %d"% i
      print " line from CCVS %s" % l1[i]
      print " line from RCS %s" % l2[i+2] 
      ok=0
  return ok

if len(sys.argv)==4:
  compareco(sys.argv[1],sys.argv[2],sys.argv[3])
elif len(sys.argv)==3:
  a=vclib.ccvs.CVSRepository("lucas",sys.argv[1])
  f=a.getfile(convertpath(sys.argv[2])) # example: ["kdelibs","po","Attic","nl.po"] 
  for rev in f.tree.keys():
    print ("revision: %s" % rev),
    if compareco(sys.argv[1],sys.argv[2],rev):
      print "ok"
    else:
      print "fail"
    
else:
  usage()

  