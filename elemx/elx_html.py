#!/usr/bin/env python
#
# generate HTML given an input file and an element file
#

import re
import string
import cgi
import struct

_re_elem = re.compile('([a-zA-Z]) ([0-9]+) ([0-9]+)\n')

CHUNK_SIZE = 98304 # 4096*24


class ElemParser:
  "Parse an elements file, extracting the token type, start, and length."

  def __init__(self, efile):
    self.efile = efile

  def get(self):
    line = self.efile.readline()
    if not line:
      return None, None, None
    t, s, e = string.split(line)
    return t, int(s)-1, int(e)

  def unused_get(self):
    record = self.efile.read(9)
    if not record:
      return None, None, None
    return struct.unpack('>cii', record)


class Writer:
  "Generate output, including copying from another input."

  def __init__(self, ifile, ofile):
    self.ifile = ifile
    self.ofile = ofile

    self.buf = ifile.read(CHUNK_SIZE)
    self.offset = 0

  def write(self, data):
    self.ofile.write(data)

  def copy(self, pos, amt):
    "Copy 'amt' bytes from position 'pos' of input to output."
    idx = pos - self.offset
    self.ofile.write(cgi.escape(buffer(self.buf, idx, amt)))
    amt = amt - (len(self.buf) - idx)
    while amt > 0:
      self._more()
      self.ofile.write(cgi.escape(buffer(self.buf, 0, amt)))
      amt = amt - len(self.buf)

  def flush(self, pos):
    "Flush the rest of the input to the output."
    idx = pos - self.offset
    self.ofile.write(cgi.escape(buffer(self.buf, idx)))
    while 1:
      buf = self.ifile.read(CHUNK_SIZE)
      if not buf:
        break
      self.ofile.write(cgi.escape(buf))

  def _more(self):
    self.offset = self.offset + len(self.buf)
    self.buf = self.ifile.read(CHUNK_SIZE)


def generate(input, elems, output, genpage=0):
  ep = ElemParser(elems)
  w = Writer(input, output)
  cur = 0
  if genpage:
    w.write('''\
<html><head><title>ELX Output Page</title>
<style type="text/css">
  .elx_C { color: firebrick; font-style: italic; }
  .elx_S { color: #bc8f8f; font-weight: bold; }
  .elx_K { color: purple; font-weight: bold }
  .elx_F { color: blue; font-weight: bold; }
  .elx_L { color: blue; font-weight: bold; }
  .elx_M { color: blue; font-weight: bold; }
  .elx_R { color: blue; font-weight: bold; }
</style>
</head>
<body>
''')
  w.write('<pre>')
  while 1:
    type, start, length = ep.get()
    if type is None:
      break
    if cur < start:
      # print out some plain text up to 'cur'
      w.copy(cur, start - cur)

    # wrap a bit o' formatting here
    w.write('<span class="elx_%s">' % type)

    # copy over the token
    w.copy(start, length)

    # and close up the formatting
    w.write('</span>')

    cur = start + length

  # all done.
  w.flush(cur)
  w.write('</pre>')
  if genpage:
    w.write('</body></html>\n')

if __name__ == '__main__':
  import sys
  generate(open(sys.argv[1]), open(sys.argv[2]), sys.stdout, 1)
