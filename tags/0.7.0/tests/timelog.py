
import time
import string
import profile

import rcsparse
import viewcvs

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
    entry = viewcvs.LogEntry(revision, int(timestamp) - time.timezone, author,
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
  rcsparse.Parser().parse(open(full_name), sink)
  return sink.head, sink.branch, sink.tags, sink.revs

def compare_fetch(full_name, which_rev=None):
  d1 = viewcvs.fetch_log(full_name, which_rev)
  d2 = fetch_log2(full_name, which_rev)
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

def time_fetch(full_name, which_rev=None):
  t = time.time()
  viewcvs.fetch_log(full_name, which_rev)
  t1 = time.time() - t
  t = time.time()
  fetch_log2(full_name, which_rev)
  t2 = time.time() - t
  print t1, t2

def profile_fetch(full_name, which_rev=None):
  p = profile.Profile()
  def many_calls(*args):
    for i in xrange(10):
      apply(fetch_log2, args)
  p.runcall(many_calls, full_name, which_rev)
  p.print_stats()

def varysize(full_name, which_rev=None):
  def one_run(n, *args):
    rcsparse._TokenStream.CHUNK_SIZE = n
    t = time.time()
    for i in xrange(5):
      apply(fetch_log2, args)
    print n, time.time() - t

  #one_run(2020, full_name, which_rev)
  #one_run(4070, full_name, which_rev)
  #one_run(8170, full_name, which_rev)
  #one_run(8192, full_name, which_rev)
  #one_run(16384, full_name, which_rev)
  one_run(32740, full_name, which_rev)
  one_run(65500, full_name, which_rev)
  one_run(100000, full_name, which_rev)
  one_run(200000, full_name, which_rev)
  one_run(500000, full_name, which_rev)
