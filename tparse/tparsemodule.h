/*
# Copyright (C) 1999-2014 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# This file has been rewritten in C++ from the rcsparse.py file by
# Lucas Bruand <lucas.bruand@ecl2002.ec-lyon.fr>
#
# This file was originally based on portions of the blame.py script by
# Curt Hagenlocher.
#
# -----------------------------------------------------------------------
*/

#ifdef __cplusplus
extern "C"
{
#endif

#include <Python.h>

  static char *__doc__ = \
    "This python extension module is a binding to the tparse library.\n" \
    "tparse is a C++ library that offers an API to a performance-oriented\n" \
    "RCSFILE parser.\n" \
    "It does little syntax checking.\n" \
    "\n" \
    "Version: $Id$\n";
  static char *__version__ = "0.14";
  static char *__date__ = "2002/02/11";
  static char *__author__ = "Lucas Bruand <lucas.bruand@ecl2002.ec-lyon.fr>";

  //static char *pyRCSStopParser__doc__ =
  // "Stop parser exception: to be raised from the sink to abort parsing.";
  static PyObject *pyRCSStopParser;

  //static char *pyRCSParseError__doc__ =
  // "Ancestor Exception";
  static PyObject *pyRCSParseError;

  //static char *pyRCSIllegalCharacter__doc__ =
  // "Parser has encountered an Illegal Character.";
  static PyObject *pyRCSIllegalCharacter;

  //static char *pyRCSExpected__doc__ =
  // "Parse has found something but the expected.";
  static PyObject *pyRCSExpected;
  static PyObject *PySink; // Sink Class from the common module.

  static char *tparse__doc__ = \
    "Main function: Parse a file and send the result to the sink.\n" \
    "Two ways of invoking this function from python:\n" \
    "* tparse.parse(filename, sink)\n" \
    "where filename is a string and sink is an instance of the class Sink\n" \
    "defined in the common.py module.\n" \
    "* tparse.parse(file, sink)\n" \
    "where file is a python file and sink is an instance of the class Sink\n" \
    "defined in the common.py module.\n";
  static PyObject * tparse( PyObject *self, PyObject *args);

  /* Init function for this module: Invoked when the module is
     imported from Python Load the stopparser expression into the
     tparser's namespace */
  void inittparse();
#ifdef __cplusplus
}
#endif


