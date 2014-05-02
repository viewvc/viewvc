# -*-python-*-
#
# Copyright (C) 1999-2014 The ViewCVS Group. All Rights Reserved.
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
  """Interface to be implemented by clients.  The RCS parser calls this as
  it parses the RCS file.

  All these methods have stub implementations that do nothing, so you only
  have to override the callbacks that you care about.
  """
  def set_head_revision(self, revision):
    """Reports the head revision for this RCS file.

    This is the value of the 'head' header in the admin section of the RCS
    file.  This function can only be called before admin_completed().

    Parameter: REVISION is a string containing a revision number.  This is
    an actual revision number, not a branch number.
    """
    pass

  def set_principal_branch(self, branch_name):
    """Reports the principal branch for this RCS file.  This is only called
    if the principal branch is not trunk.

    This is the value of the 'branch' header in the admin section of the RCS
    file.  This function can only be called before admin_completed().

    Parameter: BRANCH_NAME is a string containing a branch number.  If this
    function is called, the parameter is typically "1.1.1", indicating the
    vendor branch.
    """
    pass

  def set_access(self, accessors):
    """Reports the access control list for this RCS file.  This function is
    only called if the ACL is set.  If this function is not called then
    there is no ACL and all users are allowed access.

    This is the value of the 'access' header in the admin section of the RCS
    file.  This function can only be called before admin_completed().

    Parameter: ACCESSORS is a list of strings.  Each string is a username.
    The user is allowed access if and only if their username is in the list,
    OR the user owns the RCS file on disk, OR the user is root.

    Note that CVS typically doesn't use this field.
    """
    pass

  def define_tag(self, name, revision):
    """Reports a tag or branch definition.  This function will be called
    once for each tag or branch.

    This is taken from the 'symbols' header in the admin section of the RCS
    file.  This function can only be called before admin_completed().

    Parameters: NAME is a string containing the tag or branch name.
    REVISION is a string containing a revision number.  This may be
    an actual revision number (for a tag) or a branch number.

    The revision number consists of a number of decimal components separated
    by dots.  There are three common forms.  If there are an odd number of
    components, it's a branch.  Otherwise, if the next-to-last component is
    zero, it's a branch (and the next-to-last component is an artifact of
    CVS and should not be shown to the user).  Otherwise, it's a tag.

    This function is called in the order that the tags appear in the RCS
    file header.  For CVS, this appears to be in reverse chronological
    order of tag/branch creation.
    """
    pass

  def set_locker(self, revision, locker):
    """Reports a lock on this RCS file.  This function will be called once
    for each lock.

    This is taken from the 'locks' header in the admin section of the RCS
    file.  This function can only be called before admin_completed().

    Parameters: REVISION is a string containing a revision number.  This is
    an actual revision number, not a branch number.
    LOCKER is a string containing a username.
    """
    pass

  def set_locking(self, mode):
    """Signals strict locking mode.  This function will be called if and
    only if the RCS file is in strict locking mode.

    This is taken from the 'strict' header in the admin section of the RCS
    file.  This function can only be called before admin_completed().

    Parameters: MODE is always the string 'strict'.
    """
    pass

  def set_comment(self, comment):
    """Reports the comment for this RCS file.

    This is the value of the 'comment' header in the admin section of the
    RCS file.  This function can only be called before admin_completed().

    Parameter: COMMENT is a string containing the comment.  This may be
    multi-line.

    This field does not seem to be used by CVS.    
    """
    pass

  def set_expansion(self, mode):
    """Reports the keyword expansion mode for this RCS file.

    This is the value of the 'expand' header in the admin section of the
    RCS file.  This function can only be called before admin_completed().

    Parameter: MODE is a string containing the keyword expansion mode.
    Possible values include 'o' and 'b', amongst others.
    """
    pass

  def admin_completed(self):
    """Reports that the initial RCS header has been parsed.  This function is
    called exactly once.
    """
    pass

  def define_revision(self, revision, timestamp, author, state,
                      branches, next):
    """Reports metadata about a single revision.

    This function is called for each revision.  It is called later than
    admin_completed() and earlier than tree_completed().

    Parameter: REVISION is a revision number, as a string.  This is an
    actual revision number, not a branch number.
    TIMESTAMP is the date and time that the revision was created, as an
    integer number of seconds since the epoch.  (I.e. "UNIX time" format).
    AUTHOR is the author name, as a string.
    STATE is the state of the revision, as a string.  Common values are
    "Exp" and "dead".
    BRANCHES is a list of strings, with each string being an actual
    revision number (not a branch number).  For each branch which is based
    on this revision and has commits, the revision number of the first
    branch commit is listed here.
    NEXT is either None or a string representing an actual revision number
    (not a branch number).

    When on trunk, NEXT points to what humans might consider to be the
    'previous' revision number.  For example, 1.3's NEXT is 1.2.
    However, on a branch, NEXT really does point to what humans would
    consider to be the 'next' revision number.  For example, 1.1.2.1's
    NEXT would be 1.1.2.2.
    In other words, NEXT always means "where to find the next deltatext
    that you need this revision to retrieve".
    """
    pass

  def tree_completed(self):
    """Reports that the RCS revision tree has been parsed.  This function is
    called exactly once.  This function will be called later than
    admin_completed().
    """
    pass

  def set_description(self, description):
    """Reports the description from the RCS file.  This is set using the
    "-m" flag to "cvs add".  However, many CVS users don't use that option,
    so this is often empty.

    This function is called once, after tree_completed().

    Parameter: DESCRIPTION is a string containing the description.  This may
    be multi-line.
    """
    pass

  def set_revision_info(self, revision, log, text):
    """Reports the log message and contents of a CVS revision.

    This function is called for each revision.  It is called later than
    set_description().

    Parameters: REVISION is a string containing the actual revision number.
    LOG is a string containing the log message.  This may be multi-line.
    TEXT is the contents of the file in this revision, either as full-text or
    as a diff.  This is usually multi-line, and often quite large and/or
    binary.
    """
    pass

  def parse_completed(self):
    """Reports that parsing an RCS file is complete.

    This function is called once.  After it is called, no more calls will be
    made via this interface.
    """
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
          while self.ts.get() != ';':
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

    # Convert date into standard UNIX time format (seconds since epoch)
    date_fields = string.split(date, '.')
    # According to rcsfile(5): the year "contains just the last two
    # digits of the year for years from 1900 through 1999, and all the
    # digits of years thereafter".
    if len(date_fields[0]) == 2:
      date_fields[0] = '19' + date_fields[0]
    date_fields = map(string.atoi, date_fields)
    EPOCH = 1970
    if date_fields[0] < EPOCH:
      raise ValueError, 'invalid year for revision %s' % (revision,)
    try:
      timestamp = calendar.timegm(tuple(date_fields) + (0, 0, 0,))
    except ValueError, e:
      raise ValueError, 'invalid date for revision %s: %s' % (revision, e,)

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
    #    commitid	mLiHw3bulRjnTDGr;
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
    """Parse an RCS file.

    Parameters: FILE is the file object to parse.  (I.e. an object of the
    built-in Python type "file", usually created using Python's built-in
    "open()" function).
    SINK is an instance of (some subclass of) Sink.  It's methods will be
    called as the file is parsed; see the definition of Sink for the
    details.
    """
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
