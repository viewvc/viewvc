# -*-python-*-
#
# Copyright (C) 1999-2009 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# accept.py: parse/handle the various Accept headers from the client
#
# -----------------------------------------------------------------------

import re
import string


def language(hdr):
  "Parse an Accept-Language header."

  # parse the header, storing results in a _LanguageSelector object
  return _parse(hdr, _LanguageSelector())

# -----------------------------------------------------------------------

_re_token = re.compile(r'\s*([^\s;,"]+|"[^"]*")+\s*')
_re_param = re.compile(r';\s*([^;,"]+|"[^"]*")+\s*')
_re_split_param = re.compile(r'([^\s=])\s*=\s*(.*)')

def _parse(hdr, result):
  # quick exit for empty or not-supplied header
  if not hdr:
    return result

  pos = 0
  while pos < len(hdr):
    name = _re_token.match(hdr, pos)
    if not name:
      raise AcceptLanguageParseError()
    a = result.item_class(string.lower(name.group(1)))
    pos = name.end()
    while 1:
      # are we looking at a parameter?
      match = _re_param.match(hdr, pos)
      if not match:
        break
      param = match.group(1)
      pos = match.end()

      # split up the pieces of the parameter
      match = _re_split_param.match(param)
      if not match:
        # the "=" was probably missing
        continue

      pname = string.lower(match.group(1))
      if pname == 'q' or pname == 'qs':
        try:
          a.quality = float(match.group(2))
        except ValueError:
          # bad float literal
          pass
      elif pname == 'level':
        try:
          a.level = float(match.group(2))
        except ValueError:
          # bad float literal
          pass
      elif pname == 'charset':
        a.charset = string.lower(match.group(2))

    result.append(a)
    if hdr[pos:pos+1] == ',':
      pos = pos + 1

  return result

class _AcceptItem:
  def __init__(self, name):
    self.name = name
    self.quality = 1.0
    self.level = 0.0
    self.charset = ''

  def __str__(self):
    s = self.name
    if self.quality != 1.0:
      s = '%s;q=%.3f' % (s, self.quality)
    if self.level != 0.0:
      s = '%s;level=%.3f' % (s, self.level)
    if self.charset:
      s = '%s;charset=%s' % (s, self.charset)
    return s

class _LanguageRange(_AcceptItem):
  def matches(self, tag):
    "Match the tag against self. Returns the qvalue, or None if non-matching."
    if tag == self.name:
      return self.quality

    # are we a prefix of the available language-tag
    name = self.name + '-'
    if tag[:len(name)] == name:
      return self.quality
    return None

class _LanguageSelector:
  """Instances select an available language based on the user's request.

  Languages found in the user's request are added to this object with the
  append() method (they should be instances of _LanguageRange). After the
  languages have been added, then the caller can use select_from() to
  determine which user-request language(s) best matches the set of
  available languages.

  Strictly speaking, this class is pretty close for more than just
  language matching. It has been implemented to enable q-value based
  matching between requests and availability. Some minor tweaks may be
  necessary, but simply using a new 'item_class' should be sufficient
  to allow the _parse() function to construct a selector which holds
  the appropriate item implementations (e.g. _LanguageRange is the
  concrete _AcceptItem class that handles matching of language tags).
  """

  item_class = _LanguageRange

  def __init__(self):
    self.requested = [ ]

  def select_from(self, avail):
    """Select one of the available choices based on the request.

    Note: if there isn't a match, then the first available choice is
    considered the default. Also, if a number of matches are equally
    relevant, then the first-requested will be used.

    avail is a list of language-tag strings of available languages
    """

    # tuples of (qvalue, language-tag)
    matches = [ ]

    # try matching all pairs of desired vs available, recording the
    # resulting qvalues. we also need to record the longest language-range
    # that matches since the most specific range "wins"
    for tag in avail:
      longest = 0
      final = 0.0

      # check this tag against the requests from the user
      for want in self.requested:
        qvalue = want.matches(tag)
        #print 'have %s. want %s. qvalue=%s' % (tag, want.name, qvalue)
        if qvalue is not None and len(want.name) > longest:
          # we have a match and it is longer than any we may have had.
          # the final qvalue should be from this tag.
          final = qvalue
          longest = len(want.name)

      # a non-zero qvalue is a potential match
      if final:
        matches.append((final, tag))

    # if there are no matches, then return the default language tag
    if not matches:
      return avail[0]

    # get the highest qvalue and its corresponding tag
    matches.sort()
    qvalue, tag = matches[-1]

    # if the qvalue is zero, then we have no valid matches. return the
    # default language tag.
    if not qvalue:
      return avail[0]

    # if there are two or more matches, and the second-highest has a
    # qvalue equal to the best, then we have multiple "best" options.
    # select the one that occurs first in self.requested
    if len(matches) >= 2 and matches[-2][0] == qvalue:
      # remove non-best matches
      while matches[0][0] != qvalue:
        del matches[0]
      #print "non-deterministic choice", matches

      # sequence through self.requested, in order
      for want in self.requested:
        # try to find this one in our best matches
        for qvalue, tag in matches:
          if want.matches(tag):
            # this requested item is one of the "best" options
            ### note: this request item could match *other* "best" options,
            ### so returning *this* one is rather non-deterministic.
            ### theoretically, we could go further here, and do another
            ### search based on the ordering in 'avail'. however, note
            ### that this generally means that we are picking from multiple
            ### *SUB* languages, so I'm all right with the non-determinism
            ### at this point. stupid client should send a qvalue if they
            ### want to refine.
            return tag

      # NOTREACHED

    # return the best match
    return tag

  def append(self, item):
    self.requested.append(item)

class AcceptLanguageParseError(Exception):
  pass

def _test():
  s = language('en')
  assert s.select_from(['en']) == 'en'
  assert s.select_from(['en', 'de']) == 'en'
  assert s.select_from(['de', 'en']) == 'en'

  # Netscape 4.x and early version of Mozilla may not send a q value
  s = language('en, ja')
  assert s.select_from(['en', 'ja']) == 'en'

  s = language('fr, de;q=0.9, en-gb;q=0.7, en;q=0.6, en-gb-foo;q=0.8')
  assert s.select_from(['en']) == 'en'
  assert s.select_from(['en-gb-foo']) == 'en-gb-foo'
  assert s.select_from(['de', 'fr']) == 'fr'
  assert s.select_from(['de', 'en-gb']) == 'de'
  assert s.select_from(['en-gb', 'en-gb-foo']) == 'en-gb-foo'
  assert s.select_from(['en-bar']) == 'en-bar'
  assert s.select_from(['en-gb-bar', 'en-gb-foo']) == 'en-gb-foo'

  # non-deterministic. en-gb;q=0.7 matches both avail tags.
  #assert s.select_from(['en-gb-bar', 'en-gb']) == 'en-gb'
