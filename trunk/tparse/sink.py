import tparse
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
    
class DebugSink(Sink):
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

