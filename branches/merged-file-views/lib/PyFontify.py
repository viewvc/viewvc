"""Module to analyze Python source code; for syntax coloring tools.

Interface:

    tags = fontify(pytext, searchfrom, searchto)

The PYTEXT argument is a string containing Python source code.  The
(optional) arguments SEARCHFROM and SEARCHTO may contain a slice in
PYTEXT.

The returned value is a list of tuples, formatted like this:

    [('keyword', 0, 6, None),
     ('keyword', 11, 17, None),
     ('comment', 23, 53, None),
     ...
    ]
    
The tuple contents are always like this:

    (tag, startindex, endindex, sublist)
    
TAG is one of 'keyword', 'string', 'comment' or 'identifier'
SUBLIST is not used, hence always None.
"""

# Based on FontText.py by Mitchell S. Chapman,
# which was modified by Zachary Roadhouse,
# then un-Tk'd by Just van Rossum.
# Many thanks for regular expression debugging & authoring are due to:
#    Tim (the-incredib-ly y'rs) Peters and Cristian Tismer
# So, who owns the copyright? ;-) How about this:
# Copyright 1996-1997: 
#    Mitchell S. Chapman,
#    Zachary Roadhouse,
#    Tim Peters,
#    Just van Rossum

__version__ = "0.3.1"

import string, re


# This list of keywords is taken from ref/node13.html of the
# Python 1.3 HTML documentation. ("access" is intentionally omitted.)

keywordsList = ["and", "assert", "break", "class", "continue", "def",
                "del", "elif", "else", "except", "exec", "finally",
                "for", "from", "global", "if", "import", "in", "is",
                "lambda", "not", "or", "pass", "print", "raise",
                "return", "try", "while",
                ]

# A regexp for matching Python comments.
commentPat = "#.*"

# A regexp for matching simple quoted strings.
pat = "q[^q\\n]*(\\[\000-\377][^q\\n]*)*q"
quotePat = string.replace(pat, "q", "'") + "|" + string.replace(pat, 'q', '"')

# A regexp for matching multi-line tripled-quoted strings.  (Way to go, Tim!)
pat = """
    qqq
    [^q]*
    (
        (    \\[\000-\377]
        |    q
            (    \\[\000-\377]
            |    [^q]
            |    q
                (    \\[\000-\377]
                |    [^q]
                )
            )
        )
        [^q]*
    )*
    qqq
"""
pat = string.join(string.split(pat), '')   # get rid of whitespace
tripleQuotePat = string.replace(pat, "q", "'") + "|" \
                 + string.replace(pat, 'q', '"')

# A regexp which matches all and only Python keywords. This will let
# us skip the uninteresting identifier references.
nonKeyPat = "(^|[^a-zA-Z0-9_.\"'])"   # legal keyword-preceding characters
keyPat = nonKeyPat + "(" + string.join(keywordsList, "|") + ")" + nonKeyPat

# Our final syntax-matching regexp is the concatation of the regexp's we
# constructed above.
syntaxPat = keyPat + \
            "|" + commentPat + \
            "|" + tripleQuotePat + \
            "|" + quotePat
syntaxRE = re.compile(syntaxPat)

# Finally, we construct a regexp for matching indentifiers (with
# optional leading whitespace).
idKeyPat = "[ \t]*[A-Za-z_][A-Za-z_0-9.]*"
idRE = re.compile(idKeyPat)


def fontify(pytext, searchfrom=0, searchto=None):
    if searchto is None:
        searchto = len(pytext)
    tags = []
    commentTag = 'comment'
    stringTag = 'string'
    keywordTag = 'keyword'
    identifierTag = 'identifier'
    
    start = 0
    end = searchfrom
    while 1:
        # Look for some syntax token we're interested in.  If find
        # nothing, we're done.
        matchobj = syntaxRE.search(pytext, end)
        if not matchobj:
            break

        # If we found something outside our search area, it doesn't
        # count (and we're done).
        start = matchobj.start()
        if start >= searchto:
            break

        match = matchobj.group(0)
        end = start + len(match)
        c = match[0]
        if c == '#':
            # We matched a comment.
            tags.append((commentTag, start, end, None))
        elif c == '"' or c == '\'':
            # We matched a string.
            tags.append((stringTag, start, end, None))
        else:
            # We matched a keyword.
            if start != searchfrom:
                # there's still a redundant char before and after it, strip!
                match = match[1:-1]
                start = start + 1
            else:
                # This is the first keyword in the text.
                # Only a space at the end.
                match = match[:-1]
            end = end - 1
            tags.append((keywordTag, start, end, None))
            # If this was a defining keyword, look ahead to the
            # following identifier.
            if match in ["def", "class"]:
                matchobj = idRE.search(pytext, end)
                if matchobj:
                    start = matchobj.start()
                    if start == end and start < searchto:
                        end = start + len(matchobj.group(0))
                        tags.append((identifierTag, start, end, None))
    return tags


def test(path):
    f = open(path)
    text = f.read()
    f.close()
    tags = fontify(text)
    for tag, start, end, sublist in tags:
        print tag, `text[start:end]`

if __name__ == "__main__":
    import sys
    test(sys.argv[0])
