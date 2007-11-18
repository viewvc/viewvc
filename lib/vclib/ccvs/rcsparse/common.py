# -*-python-*-
#
# Copyright (C) 1999-2006 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

"""common.py: common classes and functions for the RCS parsing tools."""

import calendar
import string

class Sink:
  def set_head_revision(self, revision):
    pass

  def set_principal_branch(self, branch_name):
    pass

  def set_access(self, accessors):
    pass

  def define_tag(self, name, revision):
    pass

  def set_locker(self, revision, locker):
    pass

  def set_locking(self, mode):
    """Used to signal locking mode.

    Called with mode argument 'strict' if strict locking
    Not called when no locking used."""

    pass

  def set_comment(self, comment):
    pass

  def set_expansion(self, mode):
    pass

  def admin_completed(self):
    pass

  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    pass

  def tree_completed(self):
    pass

  def set_description(self, description):
    pass

  def set_revision_info(self, revision, log, text):
    pass

  def parse_completed(self):
    pass


# --------------------------------------------------------------------------
#
# EXCEPTIONS USED BY RCSPARSE
#

class RCSParseError(Exception):
  pass
class RCSIllegalCharacter(RCSParseError):
  pass
### need more work on this one
class RCSExpected(RCSParseError):
  def __init__(self, got, wanted):
    RCSParseError.__init__(self, got, wanted)

class RCSStopParser(Exception):
  pass

# --------------------------------------------------------------------------
#
# STANDARD TOKEN STREAM-BASED PARSER
#

class _Parser:
  stream_class = None   # subclasses need to define this

  def _parse_admin_head(self, token):
    semi, rev = self.ts.mget(2)
    self.sink.set_head_revision(rev)
    if semi != ';':
      raise RCSExpected(semi, ';')

  def _parse_admin_branch(self, token):
    semi, branch = self.ts.mget(2)
    if semi == ';':
      self.sink.set_principal_branch(branch)
    else:
      if branch == ';':
        self.ts.unget(semi);
      else:
        raise RCSExpected(semi, ';')

  def _parse_admin_access(self, token):
    accessors = []
    while 1:
      tag = self.ts.get()
      if tag == ';':
        if accessors != []:
          self.sink.set_access(accessors)
        return
      accessors = accessors + [ tag ]

  def _parse_admin_symbols(self, token):
    while 1:
      tag = self.ts.get()
      if tag == ';':
        break
      self.ts.match(':')
      tag_name = tag
      tag_rev = self.ts.get()
      self.sink.define_tag(tag_name, tag_rev)

  def _parse_admin_locks(self, token):
    while 1:
      tag = self.ts.get()
      if tag == ';':
        break
      self.ts.match(':')
      locker = tag
      rev = self.ts.get()
      self.sink.set_locker(rev, locker)

  def _parse_admin_strict(self, token):
    self.sink.set_locking("strict")
    self.ts.match(';')

  def _parse_admin_comment(self, token):
    semi, comment = self.ts.mget(2)
    self.sink.set_comment(comment)
    if semi != ';':
      raise RCSExpected(semi, ';')

  def _parse_admin_expand(self, token):
    semi, expand_mode = self.ts.mget(2)
    self.sink.set_expansion(expand_mode)
    if semi != ';':
      raise RCSExpected(semi, ';')

  admin_token_map = {
      'head' : _parse_admin_head,
      'branch' : _parse_admin_branch,
      'access' : _parse_admin_access,
      'symbols' : _parse_admin_symbols,
      'locks' : _parse_admin_locks,
      'strict' : _parse_admin_strict,
      'comment' : _parse_admin_comment,
      'expand' : _parse_admin_expand,
      }

  def parse_rcs_admin(self):
    while 1:
      # Read initial token at beginning of line
      token = self.ts.get()

      try:
        f = self.admin_token_map[token]
      except KeyError:
        # We're done once we reach the description of the RCS tree
        if token[0] in string.digits:
          self.ts.unget(token)
          return
        else:
          # Chew up "newphrase"
          # warn("Unexpected RCS token: $token\n")
          pass
      else:
        f(self, token)

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
      # need to make the date four digits for timegm
      EPOCH = 1970
      if date_fields[0] < EPOCH:
          if date_fields[0] < 70:
              date_fields[0] = date_fields[0] + 2000
          else:
              date_fields[0] = date_fields[0] + 1900
          if date_fields[0] < EPOCH:
              raise ValueError, 'invalid year'

      timestamp = calendar.timegm(tuple(date_fields))

      # Parse author
      ### NOTE: authors containing whitespace are violations of the
      ### RCS specification.  We are making an allowance here because
      ### CVSNT is known to produce these sorts of authors.
      self.ts.match('author')
      author = ''
      while 1:
        token = self.ts.get()
        if token == ';':
          break
        author = author + token + ' '
      author = author[:-1]   # toss the trailing space

      # Parse state
      self.ts.match('state')
      state = ''
      while 1:
        token = self.ts.get()
        if token == ';':
          break
        state = state + token + ' '
      state = state[:-1]   # toss the trailing space

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

    # let sink know when the admin section has been completed
    self.sink.admin_completed()

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

# --------------------------------------------------------------------------
