
import time
import string
import profile

from vclib.ccvs import rcsparse
import viewvc

try:
  import tparse
except ImportError:
  tparse = None

def lines_changed(delta):
  idx = 0
  added = deleted = 0
  while idx < len(delta):
    op = delta[idx]
    i = string.find(delta, ' ', idx + 1)
    j = string.find(delta, '\n', i + 1)
    line = int(delta[idx+1:i])
    count = int(delta[i+1:j])
    idx = j + 1
    if op == 'd':
      deleted = deleted + count
    else: # 'a' for adding text
      added = added + count
      # skip new text
      while count > 0:
        nl = string.find(delta, '\n', idx)
        assert nl > 0, 'missing a newline in the delta in the RCS file'
        idx = nl + 1
        count = count - 1
  return added, deleted

class FetchSink(rcsparse.Sink):
  def __init__(self, which_rev=None):
    self.head = self.branch = ''
    self.tags = { }
    self.meta = { }
    self.revs = [ ]
    self.base = { }
    self.entries = { }
    self.which = which_rev

  def set_head_revision(self, revision):
    self.head = revision

  def set_principal_branch(self, branch_name):
    self.branch = branch_name

  def define_tag(self, name, revision):
    self.tags[name] = revision

  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    self.meta[revision] = (timestamp, author, state)
    self.base[next] = revision
    for b in branches:
      self.base[b] = revision

  def set_revision_info(self, revision, log, text):
    timestamp, author, state = self.meta[revision]
    entry = viewvc.LogEntry(revision, int(timestamp) - time.timezone, author,
                             state, None, log)

    # .revs is "order seen" and .entries is for random access
    self.revs.append(entry)
    self.entries[revision] = entry

    if revision != self.head:
      added, deleted = lines_changed(text)
      if string.count(revision, '.') == 1:
        # on the trunk. reverse delta.
        changed = '+%d -%d' % (deleted, added)
        self.entries[self.base[revision]].changed = changed
      else:
        # on a branch. forward delta.
        changed = '+%d -%d' % (added, deleted)
        self.entries[revision].changed = changed

  def parse_completed(self):
    if self.which:
      self.revs = [ self.entries[self.which] ]

def fetch_log2(full_name, which_rev=None):
  sink = FetchSink(which_rev)
  rcsparse.parse(open(full_name, 'rb'), sink)
  return sink.head, sink.branch, sink.tags, sink.revs

def fetch_log3(full_name, which_rev=None):
  sink = FetchSink(which_rev)
  tparse.parse(full_name, sink)
  return sink.head, sink.branch, sink.tags, sink.revs

def compare_data(d1, d2):
  if d1[:3] != d2[:3]:
    print 'd1:', d1[:3]
    print 'd2:', d2[:3]
    return
  if len(d1[3]) != len(d2[3]):
    print 'len(d1[3])=%d  len(d2[3])=%d' % (len(d1[3]), len(d2[3]))
    return
  def sort_func(e, f):
    return cmp(e.rev, f.rev)
  d1[3].sort(sort_func)
  d2[3].sort(sort_func)
  import pprint
  for i in range(len(d1[3])):
    if vars(d1[3][i]) != vars(d2[3][i]):
      pprint.pprint((i, vars(d1[3][i]), vars(d2[3][i])))

def compare_fetch(full_name, which_rev=None):
  # d1 and d2 are:
  #   ( HEAD revision, branch name, TAGS { name : revision }, [ LogEntry ] )
  d1 = viewvc.fetch_log(full_name, which_rev)
  d2 = fetch_log2(full_name, which_rev)

  print 'comparing external tools vs a parser module:'
  compare_data(d1, d2)

  if tparse:
    d2 = fetch_log3(full_name, which_rev)
    print 'comparing external tools vs the tparse module:'
    compare_data(d1, d2)

def compare_many(files):
  for file in files:
    print file, '...'
    compare_fetch(file)

def time_stream(stream_class, filename, n=10):
  d1 = d2 = d3 = d4 = 0
  t = time.time()
  for i in range(n):
    ts = stream_class(open(filename, 'rb'))
    while ts.get() is not None:
      pass
  t = time.time() - t
  print t/n

def time_fetch(full_name, which_rev=None, n=1):
  times1 = [ None ] * n
  times2 = [ None ] * n
  for i in range(n):
    t = time.time()
    viewvc.fetch_log(full_name, which_rev)
    times1[i] = time.time() - t
  for i in range(n):
    t = time.time()
    fetch_log2(full_name, which_rev)
    times2[i] = time.time() - t
  times1.sort()
  times2.sort()
  i1 = int(n*.05)
  i2 = int(n*.95)+1
  times1 = times1[i1:i2]
  times2 = times2[i1:i2]
  t1 = reduce(lambda x,y: x+y, times1, 0) / len(times1)
  t2 = reduce(lambda x,y: x+y, times2, 0) / len(times2)
  print "t1=%.4f (%.4f .. %.4f)    t2=%.4f (%.4f .. %.4f)" % \
        (t1, times1[0], times1[-1], t2, times2[0], times2[-1])

def profile_stream(stream_class, filename, n=20):
  p = profile.Profile()
  def many_calls(filename, n):
    for i in xrange(n):
      ts = stream_class(open(filename, 'rb'))
      while ts.get() is not None:
        pass
  p.runcall(many_calls, filename, n)
  p.print_stats()

def profile_fetch(full_name, which_rev=None, n=10):
  p = profile.Profile()
  def many_calls(full_name, which_rev, n):
    for i in xrange(n):
      fetch_log2(full_name, which_rev)
  p.runcall(many_calls, full_name, which_rev, n)
  p.print_stats()
