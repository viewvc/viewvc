#!/usr/bin/env python
"""ezt.py -- easy templating

ezt templates are very similar to standard HTML files.  But additionaly
they contain directives sprinkled in between.  With these directives
it possible to generate the dynamic content from the ezt templates.

These directives are enclosed in square brackets.  If you are a 
C-programmer, you might be familar with the #ifdef directives of the
C preprocessor 'cpp'.  ezt provides a similar concept for HTML.  Additionally 
EZT has a 'for' directive, which allows to iterate (repeat) certain 
subsections of the template according to sequence of data items
provided by the application.

The HTML rendering is performed by the method generate() of the Template
class.  Building template instances can either be done using external
EZT files (convention: use the suffix .ezt for such files):

    >>> template = Template("../templates/log.ezt")

or by calling the parse() method of a template instance directly with 
a EZT template string:

    >>> template = Template()
    >>> template.parse('''<html><head>
    ... <title>[title_string]</title></head>
    ... <body><h1>[title_string]</h1>
    ...    [for a_sequence] <p>[a_sequence]</p>
    ...    [end] <hr>
    ...    The [person] is [if-any state]in[else]out[end].
    ... </body>
    ... </html>
    ... ''')

The application should build a dictionary 'data' and pass it together
with the output fileobject to the templates generate method:

    >>> data = {'title_string' : "A Dummy Page",
    ...         'a_sequence' : ['list item 1', 'list item 2', 'another element'],
    ...         'person': "doctor",
    ...         'state' : None }
    >>> import sys
    >>> template.generate(sys.stdout, data)
    <html><head>
    <title>A Dummy Page</title></head>
    <body><h1>A Dummy Page</h1>
     <p>list item 1</p>
     <p>list item 2</p>
     <p>another element</p>
     <hr>
    The doctor is out.
    </body>
    </html>

Directives
==========

 Several directives allow the use of dotted qualified names refering to objects
 or attributes of objects contained in the data dictionary given to the 
 .generate() method.

 Simple directives
 -----------------

   [QUAL_NAME]

   This directive is simply replaced by the value of identifier from the data 
   dictionary.  QUAL_NAME might be a dotted qualified name refering to some
   instance attribute of objects contained in the dats dictionary.
   Numbers are converted to string though.

   [include "filename"]  or [include QUAL_NAME]

   This directive is replaced by content of the named include file.

 Block directives
 ----------------

   [for QUAL_NAME] ... [end]
   
   The text within the [for ...] directive and the corresponding [end]
   is repeated for each element in the sequence referred to by the qualified
   name in the for directive.  Within the for block this identifiers now 
   refers to the actual item indexed by this loop iteration.

   [if-any QUAL_NAME] ... [else] ... [end]

   Test if the value QUAL_NAME is not None or an empty string or list.  
   The [else] clause is optional.  CAUTION: Numeric values are converted to string,
   so if QUAL_NAME refers to a numeric value 0, the then-clause is
   substituted!

   [if-index odd] ... [else] ... [end]
   [if-index even] ... [else] ... [end]
   [if-index first] ... [else] ... [end]
   [if-index last] ... [else] ... [end]
   [if-index NUMBER] ... [else] ... [end]

   These five directives work similar to [if-any], but are only useful 
   within a [for ...]-block (see above).  The odd/even directives are 
   for example useful to choose different background colors for adjacent rows 
   in a table.  Similar the first/last directives might be used to
   remove certain parts (for example "Diff to previous" doesn't make sense,
   if there is no previous).

   [is QUAL_NAME STRING] ... [else] ... [end]
   [is QUAL_NAME QUAL_NAME] ... [else] ... [end]

   The [is ...] directive is similar to the other conditional directives
   above.  But it allows to compare two value references or a value reference
   with some constant string.
 
"""
#
# Copyright (C) 2001 Greg Stein. All Rights Reserved.
#
# Redistribution and use in source and binary forms, with or without 
# modification, are permitted provided that the following conditions are 
# met:
#
# * Redistributions of source code must retain the above copyright 
#   notice, this list of conditions and the following disclaimer. 
#
# * Redistributions in binary form must reproduce the above copyright 
#   notice, this list of conditions and the following disclaimer in the 
#   documentation and/or other materials provided with the distribution. 
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS 
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, 
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR 
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE REGENTS OR CONTRIBUTORS BE 
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR 
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF 
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS 
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN 
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) 
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE 
# POSSIBILITY OF SUCH DAMAGE.
#
#
# This software is maintained by Greg and is available at:
#    http://viewcvs.sourceforge.net/
# it is also used by the following projects:
#    http://edna.sourceforge.net/
#

import string
import re
from types import StringType, IntType, FloatType

#
# This regular expression matches three alternatives:
#   expr: DIRECTIVE | BRACKET | COMMENT
#   DIRECTIVE: '[' ('-' | '.' | ' ' | '"' | '/' | alphanum)+ ']
#   BRACKET: '[[]'
#   COMMENT: '[#' not-rbracket* ']'
#
# When used with the split() method, the return value will be composed of
# non-matching text and the two paren groups (DIRECTIVE and BRACKET). Since
# the COMMENT matches are not placed into a group, they are considered a
# "splitting" value and simply dropped.
#
_re_parse = re.compile('(\[[-\w."/ ]+\])|(\[\[\])|\[#[^\]]*\]')

# block commands and their argument counts
_block_cmd_specs = { 'if-any':1, 'if-index':2, 'for':1, 'is':2 }
_block_cmds = _block_cmd_specs.keys()

# two regular expresssions for compressing whitespace. the first is used to
# compress any whitespace including a newline into a single newline. the
# second regex is used to compress runs of whitespace into a single space.
_re_newline = re.compile('[ \t\r\f\v]*\n\\s*')
_re_whitespace = re.compile(r'\s\s+')

class Template:

  def __init__(self, fname=None):
    if fname:
      self.parse_file(fname)

  def parse_file(self, fname):
    """fname -> a string object with pathname of file containg an EZT template.
    """
    self.program = self._parse_file(fname)

  def parse(self, text):
    """text -> a string object containing the HTML template.

    parse the template program into: (TEXT DIRECTIVE BRACKET)* TEXT
    DIRECTIVE will be '[directive]' or None
    BRACKET will be '[[]' or None
    """
    self.program = self._parse(text)

  def generate(self, fp, data):
    ctx = _context()
    ctx.data = data
    ctx.for_index = { }
    self._execute(self.program, fp, ctx)

  def _parse_file(self, fname, for_names=None):
    return self._parse(open(fname, "rt").read(), for_names)

  def _parse(self, text, for_names=None):
    """text -> string object containing the HTML template.

    This is a private helper function doing the real work for method parse.
    It returns the parsed template as a 'program'.  This program is a sequence
    made out of strings or (function, argument) 2-tuples.

    Note: comment directives [# ...] are automatically dropped by _re_parse.
    """

    parts = _re_parse.split(text)

    program = [ ]
    stack = [ ]
    if not for_names:
       for_names = [ ]

    for i in range(len(parts)):
      piece = parts[i]
      which = i % 3  # discriminate between: TEXT DIRECTIVE BRACKET
      if which == 0:
        # TEXT. append if non-empty.
        if piece:
          piece = _re_whitespace.sub(' ', _re_newline.sub('\n', piece))
          program.append(piece)
      elif which == 2:
        # BRACKET directive. append '[' if present.
        if piece:
          program.append('[')
      elif piece:
        # DIRECTIVE is present.
        args = string.split(piece[1:-1])
        cmd = args[0]
        if cmd == 'else':
          if len(args) > 1:
            raise ArgCountSyntaxError()
          ### check: don't allow for 'for' cmd
          idx = stack[-1][1]
          true_section = program[idx:]
          del program[idx:]
          stack[-1][3] = true_section
        elif cmd == 'end':
          if len(args) > 1:
            raise ArgCountSyntaxError()
          # note: true-section may be None
          cmd, idx, args, true_section = stack.pop()
          else_section = program[idx:]
          func = getattr(self, '_cmd_' + re.sub('-', '_', cmd))
          program[idx:] = [ (func, (args, true_section, else_section)) ]
          if cmd == 'for':
            for_names.pop()
        elif cmd in _block_cmds:
          if len(args) > _block_cmd_specs[cmd] + 1:
            raise ArgCountSyntaxError()
          ### this assumes arg1 is always a ref
          args[1] = _prepare_ref(args[1], for_names)

          # handle arg2 for the 'is' command
          if cmd == 'is':
            if args[2][0] == '"':
              # strip the quotes
              args[2] = args[2][1:-1]
            else:
              args[2] = _prepare_ref(args[2], for_names)
          elif cmd == 'for':
            for_names.append(args[1][0])

          # remember the cmd, current pos, args, and a section placeholder
          stack.append([cmd, len(program), args[1:], None])
        elif cmd == 'include':
          if len(args) != 2:
            raise ArgCountSyntaxError()
          if args[1][0] in ('"', "'"):
            include_filename = args[1][1:-1]
            program.extend(self._parse_file(include_filename, for_names))
          else:
            program.append((self._cmd_include, _prepare_ref(args[1], for_names)))
        else:
          # implied PRINT command
          if len(args) > 1:
            raise ArgCountSyntaxError()
          program.append((self._cmd_print, _prepare_ref(args[0], for_names)))

    return program

  def _execute(self, program, fp, ctx):
    """This private helper function takes a 'program' sequence as created
    by the method '_parse' and executes it step by step.  strings are written
    to the file object 'fp' and functions are called.
    """
    for step in program:
      if isinstance(step, StringType):
        fp.write(step)
      else:
        step[0](step[1], fp, ctx)

  def _cmd_print(self, valref, fp, ctx):
    ### type check the value
    fp.write(_get_value(valref, ctx))

  def _cmd_include(self, valref, fp, ctx):
    self._execute(self._parse_file(_get_value(valref, ctx)), fp, ctx)

  def _cmd_if_any(self, args, fp, ctx):
    "If the value is a non-empty string or non-empty list, then T else F."
    ((valref,), t_section, f_section) = args
    value = _get_value(valref, ctx)
    self._do_if(value, t_section, f_section, fp, ctx)

  def _cmd_if_index(self, args, fp, ctx):
    ((valref, value), t_section, f_section) = args
    list, idx = ctx.for_index[valref[0]]
    if value == 'even':
      value = idx % 2 == 0
    elif value == 'odd':
      value = idx % 2 == 1
    elif value == 'first':
      value = idx == 0
    elif value == 'last':
      value = idx == len(list)-1
    else:
      value = idx == int(value)
    self._do_if(value, t_section, f_section, fp, ctx)

  def _cmd_is(self, args, fp, ctx):
    ((valref, value), t_section, f_section) = args
    if not isinstance(value, StringType):
      value = _get_value(value, ctx)
    value = string.lower(_get_value(valref, ctx)) == string.lower(value)
    self._do_if(value, t_section, f_section, fp, ctx)

  def _do_if(self, value, t_section, f_section, fp, ctx):
    if t_section is None:
      t_section = f_section
      f_section = None
    if value:
      section = t_section
    else:
      section = f_section
    if section is not None:
      self._execute(section, fp, ctx)

  def _cmd_for(self, args, fp, ctx):
    ((valref,), unused, section) = args
    list = _get_value(valref, ctx)
    if isinstance(list, StringType):
      raise NeedSequenceError()
    refname = valref[0]
    ctx.for_index[refname] = [ list, 0 ]
    for i in range(len(list)):
      ctx.for_index[refname][1] = i
      self._execute(section, fp, ctx)
    del ctx.for_index[refname]


def _prepare_ref(refname, for_names):
  """refname -> a string containing a dotted identifier. example:"foo.bar.bang"
  for_names -> a list of active for sequences.

  Returns a `value reference', a 3-Tupel made out of (refname, start, rest), 
  for fast access later.
  """
  parts = string.split(refname, '.')
  start = parts[0]
  rest = parts[1:]
  while rest and (start in for_names):
    # check if the next part is also a "for name"
    name = start + '.' + rest[0]
    if name in for_names:
      start = name
      del rest[0]
    else:
      break
  return refname, start, rest

def _get_value((refname, start, rest), ctx):
  """(refname, start, rest) -> a prepared `value reference' (see above).
  ctx -> an execution context instance.

  Does a name space lookup within the template name space.  Active 
  for blocks take precedence over data dictionary members with the 
  same name.
  """
  if ctx.for_index.has_key(start):
    list, idx = ctx.for_index[start]
    ob = list[idx]
  elif ctx.data.has_key(start):
    ob = ctx.data[start]
  else:
    raise UnknownReference(refname)

  # walk the rest of the dotted reference
  for attr in rest:
    try:
      ob = getattr(ob, attr)
    except AttributeError:
      raise UnknownReference(refname)

  # make sure we return a string instead of some various Python types
  if isinstance(ob, IntType) or isinstance(ob, FloatType):
    return str(ob)
  if ob is None:
    return ''

  # string or a sequence
  return ob

class _context:
  """A container for the execution context"""

class ArgCountSyntaxError(Exception):
  pass

class UnknownReference(Exception):
  pass

class NeedSequenceError(Exception):
  pass

# --- standard test environment ---
def _test(argv):
  import doctest, ezt           
  verbose = "-v" in argv
  return doctest.testmod(ezt, verbose=verbose)

if __name__ == "__main__":
  # invoke unit test for this module:
  import sys
  sys.exit(_test(sys.argv)[0])