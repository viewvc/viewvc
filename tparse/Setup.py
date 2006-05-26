#!/usr/bin/env python

from distutils.core import setup,Extension

setup(name="tparse",
      version="1.0",
      description="A quick RCS file format parser",
      author="Lucas Bruand",
      author_email="lbruand@users.sourceforge.net",
      url="http://viewvc.org",
      ext_modules=[Extension("tparse", ["tparsemodule.cpp"],libraries=["stdc++"])]
     )
