#!/usr/bin/env python
## vim:ts=4:et:nowrap
# [Emacs: -*- python -*-]
"""bin2inline_py.py -- creates Python source from directories containing images.

This is a very simple tool to pack a lot of small icons into a single file.

This version is a quick rape-and-past for the ViewCVS project.
Run this script from within the tools subdirectory to recreate the source file
'../lib/apache_icons.py'.

"""

import sys, os, string, fnmatch


PREAMBLE="""#! /usr/bin/env python
# This file was automatically generated!  DO NOT EDIT!
# Howto regenerate: see ../tools/bin2inline.py
# $Id$
# You have been warned.  But if you want to edit, go ahead using your
# favorite editor :-)
## vim:ts=4:et:nowrap
# [Emacs: -*- python -*-]

_ap_icons = """

def encodefile(filename):
    """returns the binary content of 'filename' as string"""
    s = open(filename, 'rb').read()
    result = [ ]
    while s:
      result.append(repr(s[:16]))
      s = s[16:]
    return string.join(result, '\n    ')

class Encode:
    """Starting at a given directory find all files matching a certain 
    filename pattern in this subtree, encode them as base64 strings and
    return a Python language dictionary with the filenames as keys and
    the files contents as values.
    """
    def __init__(self, startdir=os.curdir, fn_pattern="*.gif"):
        self.startdir = startdir
        self.fn_pattern = fn_pattern
        self.walk()

    def walk(self):
        """walk through the subtree starting at self.startdir"""
        self.result = ['{\n']
        os.path.walk(self.startdir, self.visitor, None)
        self.result.append('}\n')

    def visitor(self, dummy, dirname, filenames):
        """A visitor compatible with os.path.walk()."""
        for candidate in filenames:
            pathname = os.path.join(dirname, candidate)
            if not os.path.isfile(pathname):
                continue
            if self.match(pathname):
                self.put_item(pathname)

    def match(self, candidate):
        """should return false, if pathname 'candidate' should be skipped.
        """
        return fnmatch.fnmatch(candidate, self.fn_pattern)

    def put_item(self, pathname):
        self.result.append('  "%s" :\n    %s,\n\n'
                           % (self.compute_key(pathname),
                              encodefile(pathname)))

    def compute_key(self, pathname):
        """computes the dictionary key.  Tkinter compatible"""
        return os.path.splitext(pathname)[0]

    def __str__(self):
        return string.join(self.result, '')

#
# The remainder of this module is best described as hack, run and throw away
# software.  You may want to edit it, if you want to other icons.
#
class WebserverIconEncode(Encode):
    minimal_list = [ # List of icons actually used by ViewCVS as of 2001-11-17
        "/icons/apache_pb.gif",
        "/icons/small/back.gif",
        "/icons/small/dir.gif",
        "/icons/small/text.gif",
    ]
    def match(self, candidate):
        return self.compute_key(candidate) in self.minimal_list

    def compute_key(self, pathname):
        l = len(self.startdir)
        if pathname[:l] == self.startdir:
            return pathname[l:]
        return pathname

POSTAMBLE="""

def serve_icon(pathname, fp):
    if _ap_icons.has_key(pathname):
        fp.write(_ap_icons[pathname])
    else:
        raise OSError # icon not found

"""

if __name__ == "__main__":
    import sys

    f = open("../lib/apache_icons.py", "wt")
    f.write(PREAMBLE)
    f.write(str(WebserverIconEncode(startdir="/usr/local/httpd")))
    f.write(POSTAMBLE)
