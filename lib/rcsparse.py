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


class _TokenStream:
  token_term = string.whitespace + ';'

  # the algorithm is about the same speed for any CHUNK_SIZE chosen.
  # grab a good-sized chunk, but not too large to overwhelm memory.
  CHUNK_SIZE  = 100000

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

try:
  from mx import TextTools
except ImportError:
  _mxTokenStream = None
else:
  _tt = TextTools

  _idchar_list = map(chr, range(33, 127)) + map(chr, range(160, 256))
  _idchar_list.remove('$')
  _idchar_list.remove(',')
  #_idchar_list.remove('.')	leave as part of 'num' symbol
  _idchar_list.remove(':')
  _idchar_list.remove(';')
  _idchar_list.remove('@')
  _idchar = string.join(_idchar_list, '')
  _idchar_set = _tt.set(_idchar)

  _onechar_token_set = _tt.set(':;')

  _not_at_set = _tt.invset('@')

  _T_TOKEN = 30
  _T_STRING_START = 40
  _T_STRING_SPAN = 60
  _T_STRING_END = 70

  _E_COMPLETE = 100	# ended on a complete token
  _E_TOKEN = 110	# ended mid-token
  _E_STRING_SPAN = 130	# ended within a string
  _E_STRING_END = 140	# ended with string-end ('@') (could be mid-@@)

  _SUCCESS = +100

  _EOF = 'EOF'
  _CONTINUE = 'CONTINUE'
  _UNUSED = 'UNUSED'


  # continuation of a token over a chunk boundary
  _c_token_table = (
    (_T_TOKEN,      _tt.AllInSet, _idchar_set),
    )

  class _mxTokenStream:

    # the algorithm is about the same speed for any CHUNK_SIZE chosen.
    # grab a good-sized chunk, but not too large to overwhelm memory.
    CHUNK_SIZE  = 100000

  #  CHUNK_SIZE  = 5	# for debugging, make the function grind...

    def __init__(self, file):
      self.rcsfile = file
      self.tokens = [ ]
      self.partial = None

      self.string_end = None

    def _parse_chunk(self, buf, start=0):
      "Get the next token from the RCS file."

      buflen = len(buf)

      assert start < buflen

      # construct a tag table which refers to the buffer we need to parse.
      table = (
        # ignore whitespace. with or without whitespace, move to the next rule.
        (None, _tt.AllInSet, _tt.whitespace_set, +1),

        (_E_COMPLETE, _tt.EOF + _tt.AppendTagobj, _tt.Here, +1, _SUCCESS),

        # accumulate token text and exit, or move to the next rule.
        (_UNUSED,      _tt.AllInSet + _tt.AppendMatch, _idchar_set, +2),

        (_E_TOKEN,  _tt.EOF + _tt.AppendTagobj, _tt.Here, -3, _SUCCESS),

        # single character tokens exit immediately, or move to the next rule
        (_UNUSED,    _tt.IsInSet + _tt.AppendMatch, _onechar_token_set, +2),

        (_E_COMPLETE, _tt.EOF + _tt.AppendTagobj, _tt.Here, -5, _SUCCESS),

        # if this isn't an '@' symbol, then we have a syntax error (go to a
        # negative index to indicate that condition). otherwise, suck it up
        # and move to the next rule.
        (_T_STRING_START, _tt.Is + _tt.AppendTagobj, '@'),

        (None, _tt.Is, '@', +4, +1),
        (buf, _tt.Is, '@', +1, -1),
        (_T_STRING_END, _tt.Skip + _tt.AppendTagobj, 0, 0, +1),
        (_E_STRING_END, _tt.EOF + _tt.AppendTagobj, _tt.Here, -10, _SUCCESS),

        (_E_STRING_SPAN, _tt.EOF + _tt.AppendTagobj, _tt.Here, +1, _SUCCESS),

        # suck up everything that isn't an AT. go to next rule to look for EOF
        (buf,  _tt.AllInSet, _not_at_set, 0, +1),

        # go back to look for double AT if we aren't at the end of the string
        (_E_STRING_SPAN,   _tt.EOF + _tt.AppendTagobj, _tt.Here, -6, _SUCCESS),
        )

      success, taglist, idx = _tt.tag(buf, table, start)

      if not success:
        ### need a better way to report this error
        raise RCSIllegalCharacter()
      assert idx == buflen

      # pop off the last item
      last_which = taglist.pop()

      i = 0
      tlen = len(taglist)
      while i < tlen:
        if taglist[i] == _T_STRING_START:
          j = i + 1
          while j < tlen:
            if taglist[j] == _T_STRING_END:
              s = _tt.join(taglist, '', i+1, j)
              del taglist[i:j]
              tlen = len(taglist)
              taglist[i] = s
              break
            j = j + 1
          else:
            assert last_which == _E_STRING_SPAN
            s = _tt.join(taglist, '', i+1)
            del taglist[i:]
            self.partial = (_T_STRING_SPAN, [ s ])
            break
        i = i + 1

      # figure out whether we have a partial last-token
      if last_which == _E_TOKEN:
        self.partial = (_T_TOKEN, [ taglist.pop() ])
      elif last_which == _E_COMPLETE:
        pass
      elif last_which == _E_STRING_SPAN:
        assert self.partial
      else:
        assert last_which == _E_STRING_END
        self.partial = (_T_STRING_END, [ taglist.pop() ])

      taglist.reverse()
      taglist.extend(self.tokens)
      self.tokens = taglist

    def _set_end(self, taglist, text, l, r, subtags):
      self.string_end = l

    def _handle_partial(self, buf):
      which, chunks = self.partial
      if which == _T_TOKEN:
        success, taglist, idx = _tt.tag(buf, _c_token_table)
        if not success:
          # The start of this buffer was not a token. So the end of the
          # prior buffer was a complete token.
          self.tokens.insert(0, string.join(chunks, ''))
        else:
          assert len(taglist) == 1 and taglist[0][0] == _T_TOKEN \
                 and taglist[0][1] == 0 and taglist[0][2] == idx
          if idx == len(buf):
            #
            # The whole buffer was one huge token, so we may have a
            # partial token again.
            #
            # Note: this modifies the list of chunks in self.partial
            #
            chunks.append(buf)

            # consumed the whole buffer
            return len(buf)

          # got the rest of the token.
          chunks.append(buf[:idx])
          self.tokens.insert(0, string.join(chunks, ''))

        # no more partial token
        self.partial = None

        return idx

      if which == _T_STRING_END:
        if buf[0] != '@':
          self.tokens.insert(0, string.join(chunks, ''))
          return 0
        chunks.append('@')
        start = 1
      else:
        start = 0

      self.string_end = None
      string_table = (
        (None,    _tt.Is, '@', +3, +1),
        (_UNUSED, _tt.Is + _tt.AppendMatch, '@', +1, -1),
        (self._set_end, _tt.Skip + _tt.CallTag, 0, 0, _SUCCESS),

        (None,    _tt.EOF, _tt.Here, +1, _SUCCESS),

        # suck up everything that isn't an AT. move to next rule to look
        # for EOF
        (_UNUSED, _tt.AllInSet + _tt.AppendMatch, _not_at_set, 0, +1),

        # go back to look for double AT if we aren't at the end of the string
        (None,    _tt.EOF, _tt.Here, -5, _SUCCESS),
        )

      success, unused, idx = _tt.tag(buf, string_table,
                                     start, len(buf), chunks)

      # must have matched at least one item
      assert success

      if self.string_end is None:
        assert idx == len(buf)
        self.partial = (_T_STRING_SPAN, chunks)
      elif self.string_end < len(buf):
        self.partial = None
        self.tokens.insert(0, string.join(chunks, ''))
      else:
        self.partial = (_T_STRING_END, chunks)

      return idx

    def _parse_more(self):
      buf = self.rcsfile.read(self.CHUNK_SIZE)
      if not buf:
        return _EOF

      if self.partial:
        idx = self._handle_partial(buf)
        if idx is None:
          return _CONTINUE
        if idx < len(buf):
          self._parse_chunk(buf, idx)
      else:
        self._parse_chunk(buf)

      return _CONTINUE

    def get(self):
      try:
        return self.tokens.pop()
      except IndexError:
        pass

      while not self.tokens:
        action = self._parse_more()
        if action == _EOF:
          return None

      return self.tokens.pop()


  #  _get = get
  #  def get(self):
      token = self._get()
      print 'T:', `token`
      return token

    def match(self, match):
      if self.tokens:
        token = self.tokens.pop()
        if token != match:
          raise RuntimeError, ('Unexpected parsing error in RCS file.\n'
                               'Expected token: %s, but saw: %s'
                               % (match, token))
      else:
        token = self.get()
        if token != match:
          raise RuntimeError, ('Unexpected parsing error in RCS file.\n'
                               'Expected token: %s, but saw: %s'
                               % (match, token))

    def unget(self, token):
      self.tokens.append(token)

    def mget(self, count):
      "Return multiple tokens. 'next' is at the end."
      while len(self.tokens) < count:
        action = self._parse_more()
        if action == _EOF:
          ### fix this
          raise RuntimeError, 'EOF hit while expecting tokens'
      result = self.tokens[-count:]
      del self.tokens[-count:]
      return result


class RCSParseError(Exception):
  pass
class RCSIllegalCharacter(RCSParseError):
  pass
### need more work on this one
class RCSExpected(RCSParseError):
  def __init__(self, got, wanted):
    pass


class Parser:

  stream_class = _mxTokenStream or _TokenStream

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
          if self.stream_class == _mxTokenStream:
            self.ts.match(':')
            tag_name = tag
            tag_rev = self.ts.get()
          else:
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
    self.ts = self.stream_class(file)
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
    _usage()
  if sys.argv[1] == 'dump':
    dump_file(sys.argv[2])
  elif sys.argv[1] == 'time':
    time_file(sys.argv[2])
  else:
    _usage()
