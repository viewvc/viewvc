#
# Copyright (C) 2000 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://www.lyra.org/viewcvs/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://www.lyra.org/viewcvs/
#
# -----------------------------------------------------------------------
#
# This software is being maintained as part of the ViewCVS project.
# Information is available at:
#    http://viewcvs.sourceforge.net/
#
# This file was originally based on portions of the blame.py script by
# Curt Hagenlocher.
#
# -----------------------------------------------------------------------

import re
import string
import time


class _TokenStream:
  # Precompiled regular expressions
  find_token  = re.compile('^\\s*(;|@|.([^;\\s]*))(?P<ws>\\s*)')
  rest_token  = re.compile('^([^;\\s]*)(?P<ws>\\s*)')
  odd_at      = re.compile('(([^@]|^)(@@)*)@([^@]|$)')
  undo_escape = re.compile('@@')

  CHUNK_SIZE  = 16384

  def __init__(self, file):
    self.rcsfile = file
    self.save_token = None
    self.buf = ''

  def get(self):
    "Get the next token from the RCS file."

    # if one was pushed back, then return it
    if self.save_token:
      token = self.save_token
      self.save_token = None
      return token

    while 1:
      match = self.find_token.match(self.buf)
      if match:
        break
      # if we didn't find something, then it is all white space (note that
      # the pattern will match a non-white because of the "."). we can just
      # toss the whole buffer and go for more.
      self.buf = self.rcsfile.read(self.CHUNK_SIZE)
      if self.buf == '':
        # signal EOF by returning None as the token
        return None

    # retrieve the match and trim it from the buffer
    token = match.group(1)
    self.buf = self.buf[match.end():]

    if token == ';':
      return ';'

    if token != '@':
      # got a string of non-whitespace characters. if we recognized the rest
      # of the buffer (and we didn't see trailing white space), then we may
      # not have the whole token.
      while self.buf == '' and match.group('ws') == 0:
        # hit the end (and trimmed it). get more data, and append the results
        self.buf = self.rcsfile.read(self.CHUNK_SIZE)
        match = self.rest_token.match(self.buf)
        if not match.group(1):
          # first character (';' or '\\s') terminates the token
          break
        token = token + match.group(1)
        self.buf = self.buf[match.end():]

      # done piecing together tokens; return the bugger
      return token

    # a "string" which starts with the "@" character. the white space that
    # we may have sucked up is the initial token.
    token = match.group(3)

    # start scanning blocks looking for the odd @ character which closes
    # the RCS "string"
    while 1:
      match = self.odd_at.search(self.buf)
      if match:
        break

      # nothing in the whole chunk. append it all and go for more.
      token = token + self.buf
      self.buf = self.rcsfile.read(self.CHUNK_SIZE)
      if self.buf == '':
        raise RuntimeError, 'EOF'

    # split up the chunk into "token" and "the rest"
    token = token + self.buf[:match.end(1)]
    self.buf = self.buf[match.end(1)+1:]

    # undo the escape-encoding of @ characters
    token = self.undo_escape.sub('@', token)

    return token

  def match(self, match):
    "Try to match the next token from the input buffer."

    token = self.get()
    if token != match:
      raise RuntimeError, ('Unexpected parsing error in RCS file.\n' +
                           'Expected token: %s, but saw: %s' % (match, token))

  def unget(self, token):
    "Put this token back, for the next get() to return."

    # note: we don't put this into the input buffer because it may have been
    # @-unescaped already.
    self.save_token = token


class Parser:
  rcs_tree = re.compile('^\\d')

  def parse_rcs_admin(self):
    while 1:
      # Read initial token at beginning of line
      token = self.ts.get()

      # We're done once we reach the description of the RCS tree
      if self.rcs_tree.match(token):
        self.ts.unget(token)
        return

      # print "token:", token

      if token == "head":
        self.sink.set_head_revision(self.ts.get())
        self.ts.match(';')
      elif token == "branch":
        self.sink.set_principal_branch(self.ts.get())
        self.ts.match(';')
      elif token == "symbols":
        while 1:
          tag = self.ts.get()
          if tag == ';':
            break
          (tag_name, tag_rev) = string.split(tag, ':')
          self.sink.define_tag(tag_name, tag_rev)
      elif token == "comment":
        self.sink.set_comment(self.ts.get())
        self.ts.match(';')

      # Ignore all these other fields - We don't care about them. Also chews
      # up "newphrase".
      elif token in ("locks", "strict", "expand", "access"):
        while 1:
          tag = self.ts.get()
          if tag == ';':
            break
      else:
        pass
        # warn("Unexpected RCS token: $token\n")

    raise RuntimeError, "Unexpected EOF";

  def parse_rcs_tree(self):
    while 1:
      revision = self.ts.get()

      # End of RCS tree description ?
      if revision == 'desc':
        self.ts.unget(revision)
        return

      # Parse date
      self.ts.match('date')
      date = self.ts.get()
      self.ts.match(';')

      # Convert date into timestamp
      date_fields = string.split(date, '.') + ['0', '0', '0']
      date_fields = map(string.atoi, date_fields)
      if date_fields[0] < 100:
        date_fields[0] = date_fields[0] + 1900
      timestamp = time.mktime(date_fields)

      # Parse author
      self.ts.match('author')
      author = self.ts.get()
      self.ts.match(';')

      # Parse state
      self.ts.match('state')
      state = ''
      while 1:
        token = self.ts.get()
        if token == ';':
          break
        state = state + token + ' '
      state = state[:-1]	# toss the trailing space

      # Parse branches
      self.ts.match('branches')
      branches = [ ]
      while 1:
        token = self.ts.get()
        if token == ';':
          break
        branches.append(token)

      # Parse revision of next delta in chain
      self.ts.match('next')
      next = self.ts.get()
      if next == ';':
        next = None
      else:
        self.ts.match(';')

      # there are some files with extra tags in them. for example:
      #    owner	640;
      #    group	15;
      #    permissions	644;
      #    hardlinks	@configure.in@;
      # this is "newphrase" in RCSFILE(5). we just want to skip over these.
      while 1:
        token = self.ts.get()
        if token == 'desc' or self.rcs_tree.match(token):
          self.ts.unget(token)
          break
        # consume everything up to the semicolon
        while self.ts.get() != ';':
          pass

      self.sink.define_revision(revision, timestamp, author, state, branches,
                                next)

  def parse_rcs_description(self):
    self.ts.match('desc')
    self.sink.set_description(self.ts.get())

  def parse_rcs_deltatext(self):
    while 1:
      revision = self.ts.get()
      if revision is None:
        # EOF
        break
      self.ts.match('log')
      log = self.ts.get()
      ### need to add code to chew up "newphrase"
      self.ts.match('text')
      text = self.ts.get()
      self.sink.set_revision_info(revision, log, text)

  def parse(self, file, sink):
    self.ts = _TokenStream(file)
    self.sink = sink

    self.parse_rcs_admin()
    self.parse_rcs_tree()

    # many sinks want to know when the tree has been completed so they can
    # do some work to prep for the arrival of the deltatext
    self.sink.tree_completed()

    self.parse_rcs_description()
    self.parse_rcs_deltatext()

    # easiest for us to tell the sink it is done, rather than worry about
    # higher level software doing it.
    self.sink.parse_completed()

    self.ts = self.sink = None


class Sink:
  def set_head_revision(self, revision):
    pass
  def set_principal_branch(self, branch_name):
    pass
  def define_tag(self, name, revision):
    pass
  def set_comment(self, comment):
    pass
  def set_description(self, description):
    pass
  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    pass
  def set_revision_info(self, revision, log, text):
    pass
  def tree_completed(self):
    pass
  def parse_completed(self):
    pass

# --------------------------------------------------------------------------
#
# TESTING AND DEBUGGING TOOLS
#

class DebugSink:
  def set_head_revision(self, revision):
    print 'head:', revision

  def set_principal_branch(self, branch_name):
    print 'branch:', branch_name

  def define_tag(self, name, revision):
    print 'tag:', name, '=', revision

  def set_comment(self, comment):
    print 'comment:', comment

  def set_description(self, description):
    print 'description:', description

  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    print 'revision:', revision
    print '    timestamp:', timestamp
    print '    author:', author
    print '    state:', state
    print '    branches:', branches
    print '    next:', next

  def set_revision_info(self, revision, log, text):
    print 'revision:', revision
    print '    log:', log
    print '    text:', text[:100], '...'

class DumpSink:
  """Dump all the parse information directly to stdout.

  The output is relatively unformatted and untagged. It is intended as a
  raw dump of the data in the RCS file. A copy can be saved, then changes
  made to the parsing engine, then a comparison of the new output against
  the old output.
  """
  def __init__(self):
    global sha
    import sha

  def set_head_revision(self, revision):
    print revision

  def set_principal_branch(self, branch_name):
    print branch_name

  def define_tag(self, name, revision):
    print name, revision

  def set_comment(self, comment):
    print comment

  def set_description(self, description):
    print description

  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    print revision, timestamp, author, state, branches, next

  def set_revision_info(self, revision, log, text):
    print revision, sha.new(log).hexdigest(), sha.new(text).hexdigest()

  def tree_completed(self):
    print 'tree_completed'

  def parse_completed(self):
    print 'parse_completed'

def dump_file(fname):
  Parser().parse(open(fname), DumpSink())

def time_file(fname):
  import time
  p = Parser().parse
  f = open(fname)
  s = Sink()
  t = time.time()
  p(f, s)
  t = time.time() - t
  print t

def _usage():
  print 'This is normally a module for importing, but it has a couple'
  print 'features for testing as an executable script.'
  print 'USAGE: %s COMMAND filename,v' % sys.argv[0]
  print '  where COMMAND is one of:'
  print '    dump: filename is "dumped" to stdout'
  print '    time: filename is parsed with the time written to stdout'
  sys.exit(1)

if __name__ == '__main__':
  import sys
  if len(sys.argv) != 3:
    usage()
  if sys.argv[1] == 'dump':
    dump_file(sys.argv[2])
  elif sys.argv[1] == 'time':
    time_file(sys.argv[2])
  else:
    usage()
