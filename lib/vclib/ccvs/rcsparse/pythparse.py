#
# Copyright (C) 2000-2001 The ViewCVS Group. All Rights Reserved.
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
# This software is being maintained as part of the ViewCVS project.
# Information is available at:
#    http://viewcvs.sourceforge.net/
#
# This file was originally based on portions of the blame.py script by
# Curt Hagenlocher.
#
# -----------------------------------------------------------------------

import string
import time
from common import *

class _TokenStream:
  token_term = string.whitespace + ';'

  # the algorithm is about the same speed for any CHUNK_SIZE chosen.
  # grab a good-sized chunk, but not too large to overwhelm memory.
  CHUNK_SIZE  = 98304

#  CHUNK_SIZE  = 5	# for debugging, make the function grind...

  def __init__(self, file):
    self.rcsfile = file
    self.idx = 0
    self.buf = self.rcsfile.read(self.CHUNK_SIZE)
    if self.buf == '':
      raise RuntimeError, 'EOF'

  def get(self):
    "Get the next token from the RCS file."

    # Note: we can afford to loop within Python, examining individual
    # characters. For the whitespace and tokens, the number of iterations
    # is typically quite small. Thus, a simple iterative loop will beat
    # out more complex solutions.

    buf = self.buf
    idx = self.idx

    while 1:
      if idx == len(buf):
        buf = self.rcsfile.read(self.CHUNK_SIZE)
        if buf == '':
          # signal EOF by returning None as the token
          del self.buf	# so we fail if get() is called again
          return None
        idx = 0

      if buf[idx] not in string.whitespace:
        break

      idx = idx + 1

    if buf[idx] == ';':
      self.buf = buf
      self.idx = idx + 1
      return ';'

    if buf[idx] != '@':
      end = idx + 1
      token = ''
      while 1:
        # find token characters in the current buffer
        while end < len(buf) and buf[end] not in self.token_term:
          end = end + 1
        token = token + buf[idx:end]

        if end < len(buf):
          # we stopped before the end, so we have a full token
          idx = end
          break

        # we stopped at the end of the buffer, so we may have a partial token
        buf = self.rcsfile.read(self.CHUNK_SIZE)
        idx = end = 0

      self.buf = buf
      self.idx = idx
      return token

    # a "string" which starts with the "@" character. we'll skip it when we
    # search for content.
    idx = idx + 1

    chunks = [ ]

    while 1:
      if idx == len(buf):
        idx = 0
        buf = self.rcsfile.read(self.CHUNK_SIZE)
        if buf == '':
          raise RuntimeError, 'EOF'
      i = string.find(buf, '@', idx)
      if i == -1:
        chunks.append(buf[idx:])
        idx = len(buf)
        continue
      if i == len(buf) - 1:
        chunks.append(buf[idx:i])
        idx = 0
        buf = '@' + self.rcsfile.read(self.CHUNK_SIZE)
        if buf == '@':
          raise RuntimeError, 'EOF'
        continue
      if buf[i + 1] == '@':
        chunks.append(buf[idx:i+1])
        idx = i + 2
        continue

      chunks.append(buf[idx:i])

      self.buf = buf
      self.idx = i + 1

      return string.join(chunks, '')

#  _get = get
#  def get(self):
    token = self._get()
    print 'T:', `token`
    return token

  def match(self, match):
    "Try to match the next token from the input buffer."

    token = self.get()
    if token != match:
      raise RuntimeError, ('Unexpected parsing error in RCS file.\n' +
                           'Expected token: %s, but saw: %s' % (match, token))

  def unget(self, token):
    "Put this token back, for the next get() to return."

    # Override the class' .get method with a function which clears the
    # overridden method then returns the pushed token. Since this function
    # will not be looked up via the class mechanism, it should be a "normal"
    # function, meaning it won't have "self" automatically inserted.
    # Therefore, we need to pass both self and the token thru via defaults.

    # note: we don't put this into the input buffer because it may have been
    # @-unescaped already.

    def give_it_back(self=self, token=token):
      del self.get
      return token

    self.get = give_it_back

  def mget(self, count):
    "Return multiple tokens. 'next' is at the end."
    result = [ ]
    for i in range(count):
      result.append(self.get())
    result.reverse()
    return result



class Parser:

  def parse_rcs_admin(self):
    while 1:
      # Read initial token at beginning of line
      token = self.ts.get()

      # We're done once we reach the description of the RCS tree
      if token[0] in string.digits:
        self.ts.unget(token)
        return

      if token == "head":
        semi, rev = self.ts.mget(2)
        self.sink.set_head_revision(rev)
        if semi != ';':
          raise RCSExpected(semi, ';')
      elif token == "branch":
        semi, branch = self.ts.mget(2)
        self.sink.set_principal_branch(branch)
        if semi != ';':
          raise RCSExpected(semi, ';')
      elif token == "symbols":
        while 1:
          tag = self.ts.get()
          if tag == ';':
            break
          (tag_name, tag_rev) = string.split(tag, ':')
          self.sink.define_tag(tag_name, tag_rev)
      elif token == "comment":
        semi, comment = self.ts.mget(2)
        self.sink.set_comment(comment)
        if semi != ';':
          raise RCSExpected(semi, ';')

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
      semi, date, sym = self.ts.mget(3)
      if sym != 'date':
        raise RCSExpected(sym, 'date')
      if semi != ';':
        raise RCSExpected(semi, ';')

      # Convert date into timestamp
      date_fields = string.split(date, '.') + ['0', '0', '0']
      date_fields = map(string.atoi, date_fields)
      if date_fields[0] < 100:
        date_fields[0] = date_fields[0] + 1900
      timestamp = time.mktime(tuple(date_fields))

      # Parse author
      semi, author, sym = self.ts.mget(3)
      if sym != 'author':
        raise RCSExpected(sym, 'author')
      if semi != ';':
        raise RCSExpected(semi, ';')

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
      next, sym = self.ts.mget(2)
      if sym != 'next':
        raise RCSExpected(sym, 'next')
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
        if token == 'desc' or token[0] in string.digits:
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
      text, sym2, log, sym1 = self.ts.mget(4)
      if sym1 != 'log':
        print `text[:100], sym2[:100], log[:100], sym1[:100]`
        raise RCSExpected(sym1, 'log')
      if sym2 != 'text':
        raise RCSExpected(sym2, 'text')
      ### need to add code to chew up "newphrase"
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


