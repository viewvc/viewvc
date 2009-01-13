#
# ### add license stuff
#
# compat.py: compatibility functions for operation across Python 1.5.x
#

import urllib
import string
import time
import re

#
# urllib.urlencode() is new to Python 1.5.2
#
try:
  urlencode = urllib.urlencode
except AttributeError:
  def urlencode(dict):
    "Encode a dictionary as application/x-url-form-encoded."
    if not dict:
      return ''
    quote = urllib.quote_plus
    keyvalue = [ ]
    for key, value in dict.items():
      keyvalue.append(quote(key) + '=' + quote(str(value)))
    return '?' + string.join(keyvalue, '&')

#
# time.strptime() is new to Python 1.5.2
#
if hasattr(time, 'strptime'):
  def cvs_strptime(timestr):
    return time.strptime(timestr, '%Y/%m/%d %H:%M:%S')
else:
  _re_rev_date = re.compile('([0-9]{4})/([0-9][0-9])/([0-9][0-9]) '
                            '([0-9][0-9]):([0-9][0-9]):([0-9][0-9])')
  def cvs_strptime(timestr):
    matches = _re_rev_date.match(timestr).groups()
    return tuple(map(int, matches)) + (0, 1, -1)
cvs_strptime.__doc__ = 'Parse a CVS-style date/time value.'