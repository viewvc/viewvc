#
# generate HTML given an input file and an element file
#

import re
import string
import cgi

_re_elem = re.compile('([a-zA-Z]) ([0-9]+) ([0-9]+)\n')

CHUNK_SIZE = 98304 # 4096*24


class ElemParser:
  "Parse an elements file, extracting the token type, start, and length."

  def __init__(self, efile):
    self.efile = efile
    self.leftover = ''
    self.elems = [ ]

  def get(self):
    if self.elems:
      t, s, e = self.elems.pop()
      return t, int(s)-1, int(e)
    s = self.leftover + self.efile.read(CHUNK_SIZE)
    idx = string.rfind(s, '\n')
    if idx == -1:
      # woah. empty. no more elements then.
      self.leftover = ''
      return None, None, None
    self.leftover = s[idx+1:]
    self.elems = _re_elem.findall(s[:idx+1])
    self.elems.reverse()
    if self.elems:
      t, s, e = self.elems.pop()
      return t, int(s)-1, int(e)
    # no more elems
    return None, None, None


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
    self.ofile.write(cgi.escape(self.buf[idx:idx+amt]))
    amt = amt - (len(self.buf) - idx)
    while amt > 0:
      self._more()
      self.ofile.write(cgi.escape(self.buf[:amt]))
      amt = amt - len(self.buf)

  def flush(self, pos):
    "Flush the rest of the input to the output."
    idx = pos - self.offset
    self.ofile.write(cgi.escape(self.buf[idx:]))
    while 1:
      buf = self.ifile.read(CHUNK_SIZE)
      if not buf:
        break
      self.ofile.write(cgi.escape(buf))

  def _more(self):
    self.offset = self.offset + len(self.buf)
    self.buf = self.ifile.read(CHUNK_SIZE)


def generate(input, elems, output):
  ep = ElemParser(elems)
  w = Writer(input, output)
  cur = 0
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


if __name__ == '__main__':
  import sys
  generate(open(sys.argv[1]), open(sys.argv[2]), sys.stdout)
