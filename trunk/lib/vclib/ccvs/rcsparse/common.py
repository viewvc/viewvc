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
# -----------------------------------------------------------------------
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

# Parsing errors defined.

class RCSParseError(Exception):
  pass
class RCSIllegalCharacter(RCSParseError):
  pass
### need more work on this one
class RCSExpected(RCSParseError):
  def __init__(self, got, wanted):
    pass

class RCSStopParser(Exception):
  pass