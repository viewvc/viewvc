#!/usr/bin/env python
"""ezt.py -- easy templating

ezt templates are simply text files in whatever format you so desire
(such as XML, HTML, etc.) which contain directives sprinkled
throughout.  With these directives it is possible to generate the
dynamic content from the ezt templates.

These directives are enclosed in square brackets.  If you are a
C-programmer, you might be familar with the #ifdef directives of the C
preprocessor 'cpp'.  ezt provides a similar concept.  Additionally EZT
has a 'for' directive, which allows it to iterate (repeat) certain
subsections of the template according to sequence of data items
provided by the application.

The final rendering is performed by the method generate() of the Template
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
    ...    [end] <hr />
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
     <hr />
    The doctor is out.
    </body>
    </html>

Template syntax error reporting should be improved.  Currently it is 
very sparse (template line numbers would be nice):

    >>> Template().parse("[if-any where] foo [else] bar [end unexpected args]")
    Traceback (innermost last):
      File "<stdin>", line 1, in ?
      File "ezt.py", line 220, in parse
        self.program = self._parse(text)
      File "ezt.py", line 275, in _parse
        raise ArgCountSyntaxError(str(args[1:]))
    ArgCountSyntaxError: ['unexpected', 'args']
    >>> Template().parse("[if unmatched_end]foo[end]")
    Traceback (innermost last):
      File "<stdin>", line 1, in ?
      File "ezt.py", line 206, in parse
        self.program = self._parse(text)
      File "ezt.py", line 266, in _parse
        raise UnmatchedEndError()
    UnmatchedEndError


Directives
==========

 Several directives allow the use of dotted qualified names refering to objects
 or attributes of objects contained in the data dictionary given to the 
 .generate() method.

 Qualified names
 ---------------

   Qualified names have two basic forms: a variable reference, or a string
   constant. References are a name from the data dictionary with optional
   dotted attributes (where each intermediary is an object with attributes,
   of course).

   Examples:

     [varname]

     [ob.attr]

     ["string"]

 Simple directives
 -----------------

   [QUAL_NAME]

   This directive is simply replaced by the value of the qualified name.
   If the value is a number it's converted to a string before being 
   outputted. If it is None, nothing is outputted. If it is a python file
   object (i.e. any object with a "read" method), it's contents are
   outputted. If it is a callback function (any callable python object
   is assumed to be a callback function), it is invoked and passed an EZT
   Context object as an argument.

   [QUAL_NAME QUAL_NAME ...]

   If the first value is a callback function, it is invoked with an EZT
   Context object as a first argument, and the rest of the values as
   additional arguments.

   Otherwise, the first value defines a substitution format, specifying
   constant text and indices of the additional arguments. The arguments
   are substituted and the result is inserted into the output stream.

   Example:
     ["abc %0 def %1 ghi %0" foo bar.baz]

   Note that the first value can be any type of qualified name -- a string
   constant or a variable reference. Use %% to substitute a percent sign.
   Argument indices are 0-based.

   [include "filename"]  or [include QUAL_NAME]

   This directive is replaced by content of the named include file. Note
   that a string constant is more efficient -- the target file is compiled
   inline. In the variable form, the target file is compiled and executed
   at runtime.

 Block directives
 ----------------

   [for QUAL_NAME] ... [end]
   
   The text within the [for ...] directive and the corresponding [end]
   is repeated for each element in the sequence referred to by the
   qualified name in the for directive.  Within the for block this
   identifiers now refers to the actual item indexed by this loop
   iteration.

   [if-any QUAL_NAME [QUAL_NAME2 ...]] ... [else] ... [end]

   Test if any QUAL_NAME value is not None or an empty string or list.
   The [else] clause is optional.  CAUTION: Numeric values are
   converted to string, so if QUAL_NAME refers to a numeric value 0,
   the then-clause is substituted!

   [if-index INDEX_FROM_FOR odd] ... [else] ... [end]
   [if-index INDEX_FROM_FOR even] ... [else] ... [end]
   [if-index INDEX_FROM_FOR first] ... [else] ... [end]
   [if-index INDEX_FROM_FOR last] ... [else] ... [end]
   [if-index INDEX_FROM_FOR NUMBER] ... [else] ... [end]

   These five directives work similar to [if-any], but are only useful
   within a [for ...]-block (see above).  The odd/even directives are
   for example useful to choose different background colors for
   adjacent rows in a table.  Similar the first/last directives might
   be used to remove certain parts (for example "Diff to previous"
   doesn't make sense, if there is no previous).

   [is QUAL_NAME STRING] ... [else] ... [end]
   [is QUAL_NAME QUAL_NAME] ... [else] ... [end]

   The [is ...] directive is similar to the other conditional
   directives above.  But it allows to compare two value references or
   a value reference with some constant string.

   [define VARIABLE] ... [end]

   The [define ...] directive allows you to create and modify template
   variables from within the template itself.  Essentially, any data
   between inside the [define ...] and its matching [end] will be
   expanded using the other template parsing and output generation
   rules, and then stored as a string value assigned to the variable
   VARIABLE.  The new (or changed) variable is then available for use
   with other mechanisms such as [is ...] or [if-any ...], as long as
   they appear later in the template.

   [format STRING] ... [end]

   The format directive controls how the values substituted into
   templates are escaped before they are put into the output stream. It
   has no effect on the literal text of the templates, only the output
   from [QUAL_NAME ...] directives. STRING can be one of "raw" "html" 
   "xml" or "uri". The "raw" mode leaves the output unaltered; the "html"
   and "xml" modes escape special characters using entity escapes (like
   &quot; and &gt;); the "uri" mode escapes characters using hexadecimal
   escape sequences (like %20 and %7e).

   [format CALLBACK]
 
   Python applications using EZT can provide custom formatters as callback
   variables. "[format CALLBACK][QUAL_NAME][end]" is in most cases
   equivalent to "[CALLBACK QUAL_NAME]"
"""
#
# Copyright (C) 2001-2007 Greg Stein. All Rights Reserved.
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
#    http://svn.webdav.org/repos/projects/ezt/trunk/
#

import string
import re
from types import StringType, IntType, FloatType, LongType, TupleType
import os
import cgi
import urllib
try:
  import cStringIO
except ImportError:
  import StringIO
  cStringIO = StringIO

#
# Formatting types
#
FORMAT_RAW = 'raw'
FORMAT_HTML = 'html'
FORMAT_XML = 'xml'
FORMAT_URI = 'uri'

#
# This regular expression matches three alternatives:
#   expr: DIRECTIVE | BRACKET | COMMENT
#   DIRECTIVE: '[' ITEM (whitespace ITEM)* ']
#   ITEM: STRING | NAME
#   STRING: '"' (not-slash-or-dquote | '\' anychar)* '"'
#   NAME: (alphanum | '_' | '-' | '.')+
#   BRACKET: '[[]'
#   COMMENT: '[#' not-rbracket* ']'
#
# When used with the split() method, the return value will be composed of
# non-matching text and the two paren groups (DIRECTIVE and BRACKET). Since
# the COMMENT matches are not placed into a group, they are considered a
# "splitting" value and simply dropped.
#
_item = r'(?:"(?:[^\\"]|\\.)*"|[-\w.]+)'
_re_parse = re.compile(r'\[(%s(?: +%s)*)\]|(\[\[\])|\[#[^\]]*\]' % (_item, _item))

_re_args = re.compile(r'"(?:[^\\"]|\\.)*"|[-\w.]+')

# block commands and their argument counts
_block_cmd_specs = { 'if-index':2, 'for':1, 'is':2, 'define':1, 'format':1 }
_block_cmds = _block_cmd_specs.keys()

# two regular expresssions for compressing whitespace. the first is used to
# compress any whitespace including a newline into a single newline. the
# second regex is used to compress runs of whitespace into a single space.
_re_newline = re.compile('[ \t\r\f\v]*\n\\s*')
_re_whitespace = re.compile(r'\s\s+')

# this regex is used to substitute arguments into a value. we split the value,
# replace the relevant pieces, and then put it all back together. splitting
# will produce a list of: TEXT ( splitter TEXT )*. splitter will be '%' or
# an integer.
_re_subst = re.compile('%(%|[0-9]+)')

class Template:

  def __init__(self, fname=None, compress_whitespace=1,
               base_format=FORMAT_RAW):
    self.compress_whitespace = compress_whitespace
    if fname:
      self.parse_file(fname, base_format)

  def parse_file(self, fname, base_format=FORMAT_RAW):
    "fname -> a string object with pathname of file containg an EZT template."

    self.parse(_FileReader(fname), base_format)

  def parse(self, text_or_reader, base_format=FORMAT_RAW):
    """Parse the template specified by text_or_reader.

    The argument should be a string containing the template, or it should
    specify a subclass of ezt.Reader which can read templates. The base
    format for printing values is given by base_format.
    """
    if not isinstance(text_or_reader, Reader):
      # assume the argument is a plain text string
      text_or_reader = _TextReader(text_or_reader)

    self.program = self._parse(text_or_reader, base_format=base_format)

  def generate(self, fp, data):
    if hasattr(data, '__getitem__') or callable(getattr(data, 'keys', None)):
      # a dictionary-like object was passed. convert it to an
      # attribute-based object.
      class _data_ob:
        def __init__(self, d):
          vars(self).update(d)
      data = _data_ob(data)

    ctx = Context(fp)
    ctx.data = data
    ctx.for_iterators = { }
    ctx.defines = { }
    self._execute(self.program, ctx)

  def _parse(self, reader, for_names=None, file_args=(), base_format=None):
    """text -> string object containing the template.

    This is a private helper function doing the real work for method parse.
    It returns the parsed template as a 'program'.  This program is a sequence
    made out of strings or (function, argument) 2-tuples.

    Note: comment directives [# ...] are automatically dropped by _re_parse.
    """

    # parse the template program into: (TEXT DIRECTIVE BRACKET)* TEXT
    parts = _re_parse.split(reader.text)

    program = [ ]
    stack = [ ]
    if not for_names:
      for_names = [ ]

    if base_format:
      program.append((self._cmd_format, _printers[base_format]))

    for i in range(len(parts)):
      piece = parts[i]
      which = i % 3  # discriminate between: TEXT DIRECTIVE BRACKET
      if which == 0:
        # TEXT. append if non-empty.
        if piece:
          if self.compress_whitespace:
            piece = _re_whitespace.sub(' ', _re_newline.sub('\n', piece))
          program.append(piece)
      elif which == 2:
        # BRACKET directive. append '[' if present.
        if piece:
          program.append('[')
      elif piece:
        # DIRECTIVE is present.
        args = _re_args.findall(piece)
        cmd = args[0]
        if cmd == 'else':
          if len(args) > 1:
            raise ArgCountSyntaxError(str(args[1:]))
          ### check: don't allow for 'for' cmd
          idx = stack[-1][1]
          true_section = program[idx:]
          del program[idx:]
          stack[-1][3] = true_section
        elif cmd == 'end':
          if len(args) > 1:
            raise ArgCountSyntaxError(str(args[1:]))
          # note: true-section may be None
          try:
            cmd, idx, args, true_section = stack.pop()
          except IndexError:
            raise UnmatchedEndError()
          else_section = program[idx:]
          if cmd == 'format':
            program.append((self._cmd_end_format, None))
          else:
            func = getattr(self, '_cmd_' + re.sub('-', '_', cmd))
            program[idx:] = [ (func, (args, true_section, else_section)) ]
            if cmd == 'for':
              for_names.pop()
        elif cmd in _block_cmds:
          if len(args) > _block_cmd_specs[cmd] + 1:
            raise ArgCountSyntaxError(str(args[1:]))
          ### this assumes arg1 is always a ref unless cmd is 'define'
          if cmd != 'define':
            args[1] = _prepare_ref(args[1], for_names, file_args)

          # handle arg2 for the 'is' command
          if cmd == 'is':
            args[2] = _prepare_ref(args[2], for_names, file_args)
          elif cmd == 'for':
            for_names.append(args[1][0])  # append the refname
          elif cmd == 'format':
            if args[1][0]:
              # argument is a variable reference
              printer = args[1]
            else:
              # argument is a string constant referring to built-in printer
              printer = _printers.get(args[1][1])
              if not printer:
                raise UnknownFormatConstantError(str(args[1:]))
            program.append((self._cmd_format, printer))

          # remember the cmd, current pos, args, and a section placeholder
          stack.append([cmd, len(program), args[1:], None])
        elif cmd == 'include':
          if args[1][0] == '"':
            include_filename = args[1][1:-1]
            f_args = [ ]
            for arg in args[2:]:
              f_args.append(_prepare_ref(arg, for_names, file_args))
            program.extend(self._parse(reader.read_other(include_filename),
                                       for_names, f_args))
          else:
            if len(args) != 2:
              raise ArgCountSyntaxError(str(args))
            program.append((self._cmd_include,
                            (_prepare_ref(args[1], for_names, file_args),
                             reader)))
        elif cmd == 'if-any':
          f_args = [ ]
          for arg in args[1:]:
            f_args.append(_prepare_ref(arg, for_names, file_args))
          stack.append(['if-any', len(program), f_args, None])
        else:
          # implied PRINT command
          f_args = [ ]
          for arg in args:
            f_args.append(_prepare_ref(arg, for_names, file_args))
          program.append((self._cmd_print, f_args))

    if stack:
      ### would be nice to say which blocks...
      raise UnclosedBlocksError()
    return program

  def _execute(self, program, ctx):
    """This private helper function takes a 'program' sequence as created
    by the method '_parse' and executes it step by step.  strings are written
    to the file object 'fp' and functions are called.
    """
    for step in program:
      if isinstance(step, StringType):
        ctx.fp.write(step)
      else:
        step[0](step[1], ctx)

  def _cmd_print(self, valrefs, ctx):
    value = _get_value(valrefs[0], ctx)
    args = map(lambda valref, ctx=ctx: _get_value(valref, ctx), valrefs[1:])
    try:
      _write_value(value, args, ctx)
    except TypeError:
      raise Exception("Unprintable value type for '%s'" % (str(valrefs[0][0])))

  def _cmd_format(self, printer, ctx):
    if type(printer) is TupleType:
      printer = _get_value(printer, ctx)
    ctx.printers.append(printer)

  def _cmd_end_format(self, valref, ctx):
    ctx.printers.pop()

  def _cmd_include(self, (valref, reader), ctx):
    fname = _get_value(valref, ctx)
    ### note: we don't have the set of for_names to pass into this parse.
    ### I don't think there is anything to do but document it.
    self._execute(self._parse(reader.read_other(fname)), ctx)

  def _cmd_if_any(self, args, ctx):
    "If any value is a non-empty string or non-empty list, then T else F."
    (valrefs, t_section, f_section) = args
    value = 0
    for valref in valrefs:
      if _get_value(valref, ctx):
        value = 1
        break
    self._do_if(value, t_section, f_section, ctx)

  def _cmd_if_index(self, args, ctx):
    ((valref, value), t_section, f_section) = args
    iterator = ctx.for_iterators[valref[0]]
    if value == 'even':
      value = iterator.index % 2 == 0
    elif value == 'odd':
      value = iterator.index % 2 == 1
    elif value == 'first':
      value = iterator.index == 0
    elif value == 'last':
      value = iterator.is_last()
    else:
      value = iterator.index == int(value)
    self._do_if(value, t_section, f_section, ctx)

  def _cmd_is(self, args, ctx):
    ((left_ref, right_ref), t_section, f_section) = args
    value = _get_value(right_ref, ctx)
    value = string.lower(_get_value(left_ref, ctx)) == string.lower(value)
    self._do_if(value, t_section, f_section, ctx)

  def _do_if(self, value, t_section, f_section, ctx):
    if t_section is None:
      t_section = f_section
      f_section = None
    if value:
      section = t_section
    else:
      section = f_section
    if section is not None:
      self._execute(section, ctx)

  def _cmd_for(self, args, ctx):
    ((valref,), unused, section) = args
    list = _get_value(valref, ctx)
    if isinstance(list, StringType):
      raise NeedSequenceError("The value of '%s' is not a sequence"
                              % (valref[0]))
    refname = valref[0]
    ctx.for_iterators[refname] = iterator = _iter(list)
    for unused in iterator:
      self._execute(section, ctx)
    del ctx.for_iterators[refname]

  def _cmd_define(self, args, ctx):
    ((name,), unused, section) = args
    origfp = ctx.fp
    ctx.fp = cStringIO.StringIO()
    if section is not None:
      self._execute(section, ctx)
    ctx.defines[name] = ctx.fp.getvalue()
    ctx.fp = origfp

def boolean(value):
  "Return a value suitable for [if-any bool_var] usage in a template."
  if value:
    return 'yes'
  return None


def _prepare_ref(refname, for_names, file_args):
  """refname -> a string containing a dotted identifier. example:"foo.bar.bang"
  for_names -> a list of active for sequences.

  Returns a `value reference', a 3-tuple made out of (refname, start, rest), 
  for fast access later.
  """
  # is the reference a string constant?
  if refname[0] == '"':
    return None, refname[1:-1], None

  parts = string.split(refname, '.')
  start = parts[0]
  rest = parts[1:]

  # if this is an include-argument, then just return the prepared ref
  if start[:3] == 'arg':
    try:
      idx = int(start[3:])
    except ValueError:
      pass
    else:
      if idx < len(file_args):
        orig_refname, start, more_rest = file_args[idx]
        if more_rest is None:
          # the include-argument was a string constant
          return None, start, None

        # prepend the argument's "rest" for our further processing
        rest[:0] = more_rest

        # rewrite the refname to ensure that any potential 'for' processing
        # has the correct name
        ### this can make it hard for debugging include files since we lose
        ### the 'argNNN' names
        if not rest:
          return start, start, [ ]
        refname = start + '.' + string.join(rest, '.')

  if for_names:
    # From last to first part, check if this reference is part of a for loop
    for i in range(len(parts), 0, -1):
      name = string.join(parts[:i], '.')
      if name in for_names:
        return refname, name, parts[i:]

  return refname, start, rest

def _get_value((refname, start, rest), ctx):
  """(refname, start, rest) -> a prepared `value reference' (see above).
  ctx -> an execution context instance.

  Does a name space lookup within the template name space.  Active 
  for blocks take precedence over data dictionary members with the 
  same name.
  """
  if rest is None:
    # it was a string constant
    return start

  # get the starting object
  if ctx.for_iterators.has_key(start):
    ob = ctx.for_iterators[start].last_item
  elif ctx.defines.has_key(start):
    ob = ctx.defines[start]
  elif hasattr(ctx.data, start):
    ob = getattr(ctx.data, start)
  else:
    raise UnknownReference(refname)

  # walk the rest of the dotted reference
  for attr in rest:
    try:
      ob = getattr(ob, attr)
    except AttributeError:
      raise UnknownReference(refname)

  # make sure we return a string instead of some various Python types
  if isinstance(ob, IntType) \
         or isinstance(ob, LongType) \
         or isinstance(ob, FloatType):
    return str(ob)
  if ob is None:
    return ''

  # string or a sequence
  return ob

def _write_value(value, args, ctx):
  # value is a callback function, generates its own output
  if callable(value):
    apply(value, [ctx] + list(args))
    return

  # pop printer in case it recursively calls _write_value
  printer = ctx.printers.pop()

  try:
    # if the value has a 'read' attribute, then it is a stream: copy it
    if hasattr(value, 'read'):
      while 1:
        chunk = value.read(16384)
        if not chunk:
          break
        printer(ctx, chunk)

    # value is a substitution pattern
    elif args:
      parts = _re_subst.split(value)
      for i in range(len(parts)):
        piece = parts[i]
        if i%2 == 1 and piece != '%':
          idx = int(piece)
          if idx < len(args):
            piece = args[idx]
          else:
            piece = '<undef>'
        printer(ctx, piece)

    # plain old value, write to output
    else:
      printer(ctx, value)

  finally:
    ctx.printers.append(printer)


class TemplateData:
  """A custom dictionary-like object that allows one-time definition
  of keys, and only value fetches and changes, and key deletions,
  thereafter.

  EZT doesn't require the use of this special class -- a normal
  dict-type data dictionary works fine.  But use of this class will
  assist those who want the data sent to their templates to have a
  consistent set of keys."""

  def __init__(self, initial_data={}):
    self._items = initial_data
    
  def __getitem__(self, key):
    return self._items.__getitem__(key)

  def __setitem__(self, key, item):
    assert self._items.has_key(key)
    return self._items.__setitem__(key, item)

  def __delitem__(self, key):
    return self._items.__delitem__(key)

  def keys(self):
    return self._items.keys()

  def merge(self, template_data):
    """Merge the data in TemplataData instance TEMPLATA_DATA into this
    instance.  Avoid the temptation to use this conditionally in your
    code -- it rather defeats the purpose of this class."""
    
    assert isinstance(template_data, TemplateData)
    self._items.update(template_data._items)


class Context:
  """A container for the execution context"""
  def __init__(self, fp):
    self.fp = fp
    self.printers = []
  def write(self, value, args=()):
    _write_value(value, args, self)

class Reader:
  "Abstract class which allows EZT to detect Reader objects."

class _FileReader(Reader):
  """Reads templates from the filesystem."""
  def __init__(self, fname):
    self.text = open(fname, 'rb').read()
    self._dir = os.path.dirname(fname)
  def read_other(self, relative):
    return _FileReader(os.path.join(self._dir, relative))

class _TextReader(Reader):
  """'Reads' a template from provided text."""
  def __init__(self, text):
    self.text = text
  def read_other(self, relative):
    raise BaseUnavailableError()

class _Iterator:
  """Specialized iterator for EZT that counts items and can look ahead

  Implements standard iterator interface and provides an is_last() method
  and two public members:

    index - integer index of the current item
    last_item - last item returned by next()"""

  def __init__(self, sequence):
    self._iter = iter(sequence)

  def next(self):
    if hasattr(self, '_next_item'):
      self.last_item = self._next_item
      del self._next_item
    else:
      self.last_item = self._iter.next() # may raise StopIteration

    if hasattr(self, 'index'):
      self.index = self.index + 1
    else:
      self.index = 0

    return self.last_item

  def is_last(self):
    """Return true if the current item is the last in the sequence"""
    # the only way we can tell if the current item is last is to call next()
    # and store the return value so it doesn't get lost
    if not hasattr(self, '_next_item'):
      try:
        self._next_item = self._iter.next()
      except StopIteration:
        return 1
    return 0

  def __iter__(self):
    return self

class _OldIterator:
  """Alternate implemention of _Iterator for old Pythons without iterators

  This class implements the sequence protocol, instead of the iterator
  interface, so it's really not an iterator at all. But it can be used in
  python "for" loops as a drop-in replacement for _Iterator. It also provides
  the is_last() method and "last_item" and "index" members described in the
  _Iterator docstring."""

  def __init__(self, sequence):
    self._seq = sequence

  def __getitem__(self, index):
    self.last_item = self._seq[index] # may raise IndexError
    self.index = index
    return self.last_item

  def is_last(self):
    return self.index + 1 >= len(self._seq)

try:
  iter
except NameError:
  _iter = _OldIterator
else:
  _iter = _Iterator

class EZTException(Exception):
  """Parent class of all EZT exceptions."""

class ArgCountSyntaxError(EZTException):
  """A bracket directive got the wrong number of arguments."""

class UnknownReference(EZTException):
  """The template references an object not contained in the data dictionary."""

class NeedSequenceError(EZTException):
  """The object dereferenced by the template is no sequence (tuple or list)."""

class UnclosedBlocksError(EZTException):
  """This error may be simply a missing [end]."""

class UnmatchedEndError(EZTException):
  """This error may be caused by a misspelled if directive."""

class BaseUnavailableError(EZTException):
  """Base location is unavailable, which disables includes."""

class UnknownFormatConstantError(EZTException):
  """The format specifier is an unknown value."""

def _raw_printer(ctx, s):
  ctx.fp.write(s)
  
def _html_printer(ctx, s):
  ctx.fp.write(cgi.escape(s))

def _uri_printer(ctx, s):
  ctx.fp.write(urllib.quote(s))

_printers = {
  FORMAT_RAW  : _raw_printer,
  FORMAT_HTML : _html_printer,
  FORMAT_XML  : _html_printer,
  FORMAT_URI  : _uri_printer,
}

# --- standard test environment ---
def test_parse():
  assert _re_parse.split('[a]') == ['', '[a]', None, '']
  assert _re_parse.split('[a] [b]') == \
         ['', '[a]', None, ' ', '[b]', None, '']
  assert _re_parse.split('[a c] [b]') == \
         ['', '[a c]', None, ' ', '[b]', None, '']
  assert _re_parse.split('x [a] y [b] z') == \
         ['x ', '[a]', None, ' y ', '[b]', None, ' z']
  assert _re_parse.split('[a "b" c "d"]') == \
         ['', '[a "b" c "d"]', None, '']
  assert _re_parse.split(r'["a \"b[foo]" c.d f]') == \
         ['', '["a \\"b[foo]" c.d f]', None, '']

def _test(argv):
  import doctest, ezt           
  verbose = "-v" in argv
  return doctest.testmod(ezt, verbose=verbose)

if __name__ == "__main__":
  # invoke unit test for this module:
  import sys
  sys.exit(_test(sys.argv)[0])
