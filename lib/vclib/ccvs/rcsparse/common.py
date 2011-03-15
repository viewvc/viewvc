# -*-python-*-
#
# Copyright (C) 1999-2008 The ViewCVS Group. All Rights Reserved.
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


class RCSExpected(RCSParseError):
  def __init__(self, got, wanted):
    RCSParseError.__init__(
        self,
        'Unexpected parsing error in RCS file.\n'
        'Expected token: %s, but saw: %s'
        % (wanted, got)
        )


class RCSStopParser(Exception):
  pass


# --------------------------------------------------------------------------
#
# STANDARD TOKEN STREAM-BASED PARSER
#

class _Parser:
  stream_class = None   # subclasses need to define this

  def _read_until_semicolon(self):
    """Read all tokens up to and including the next semicolon token.

    Return the tokens (not including the semicolon) as a list."""

    tokens = []

    while 1:
      token = self.ts.get()
      if token == ';':
        break
      tokens.append(token)

    return tokens

  def _parse_admin_head(self, token):
    rev = self.ts.get()
    if rev == ';':
      # The head revision is not specified.  Just drop the semicolon
      # on the floor.
      pass
    else:
      self.sink.set_head_revision(rev)
      self.ts.match(';')

  def _parse_admin_branch(self, token):
    branch = self.ts.get()
    if branch != ';':
      self.sink.set_principal_branch(branch)
      self.ts.match(';')

  def _parse_admin_access(self, token):
    accessors = self._read_until_semicolon()
    if accessors:
      self.sink.set_access(accessors)

  def _parse_admin_symbols(self, token):
    while 1:
      tag_name = self.ts.get()
      if tag_name == ';':
        break
      self.ts.match(':')
      tag_rev = self.ts.get()
      self.sink.define_tag(tag_name, tag_rev)

  def _parse_admin_locks(self, token):
    while 1:
      locker = self.ts.get()
      if locker == ';':
        break
      self.ts.match(':')
      rev = self.ts.get()
      self.sink.set_locker(rev, locker)

  def _parse_admin_strict(self, token):
    self.sink.set_locking("strict")
    self.ts.match(';')

  def _parse_admin_comment(self, token):
    self.sink.set_comment(self.ts.get())
    self.ts.match(';')

  def _parse_admin_expand(self, token):
    expand_mode = self.ts.get()
    self.sink.set_expansion(expand_mode)
    self.ts.match(';')

  admin_token_map = {
      'head' : _parse_admin_head,
      'branch' : _parse_admin_branch,
      'access' : _parse_admin_access,
      'symbols' : _parse_admin_symbols,
      'locks' : _parse_admin_locks,
      'strict' : _parse_admin_strict,
      'comment' : _parse_admin_comment,
      'expand' : _parse_admin_expand,
      'desc' : None,
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
        if f is None:
          self.ts.unget(token)
          return
        else:
          f(self, token)

  def _parse_rcs_tree_entry(self, revision):
    # Parse date
    self.ts.match('date')
    date = self.ts.get()
    self.ts.match(';')

    # Convert date into timestamp
    date_fields = string.split(date, '.')
    # According to rcsfile(5): the year "contains just the last two
    # digits of the year for years from 1900 through 1999, and all the
    # digits of years thereafter".
    if len(date_fields[0]) == 2:
      date_fields[0] = '19' + date_fields[0]
    date_fields = map(string.atoi, date_fields)
    EPOCH = 1970
    if date_fields[0] < EPOCH:
      raise ValueError, 'invalid year'
    timestamp = calendar.timegm(tuple(date_fields) + (0, 0, 0,))

    # Parse author
    ### NOTE: authors containing whitespace are violations of the
    ### RCS specification.  We are making an allowance here because
    ### CVSNT is known to produce these sorts of authors.
    self.ts.match('author')
    author = ' '.join(self._read_until_semicolon())

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
    branches = self._read_until_semicolon()

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
      if token == 'desc' or token[0] in string.digits:
        self.ts.unget(token)
        break
      # consume everything up to the semicolon
      self._read_until_semicolon()

    self.sink.define_revision(revision, timestamp, author, state, branches,
                              next)

  def parse_rcs_tree(self):
    while 1:
      revision = self.ts.get()

      # End of RCS tree description ?
      if revision == 'desc':
        self.ts.unget(revision)
        return

      self._parse_rcs_tree_entry(revision)

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
