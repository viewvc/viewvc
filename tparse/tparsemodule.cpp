/*
# Copyright (C) 2000-2002 The ViewCVS Group. All Rights Reserved.
# This file has been rewritten in C++ from the rcsparse.py file by
# Lucas Bruand <lucas.bruand@ecl2002.ec-lyon.fr>
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://viewcvs.sourceforge.net/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewcvs.sourceforge.net/
#
# -----------------------------------------------------------------------
#
# This software is being maintained as part of the ViewCVS project.
# Information is available at:
#    http://viewcvs.sourceforge.net/
#
# This file was originally based on portions of the blame.py script by
# Curt Hagenlocher.
#
# -----------------------------------------------------------------------
#
*/ 
/*
   This python extension module is a binding to the tparse library.
   tparse is a C++ library that offers an API to a performance-oriented 
   RCSFILE parser.  It does little syntax checking.
 
   Version: $Id$
*/
#include <Python.h>
#include "tparsemodule.h"
#include "tparse.cpp"

#if (__GNUC__ >= 4) || (__GNUC__ == 3 && __GNUC_MINOR__ >= 1)
#include <memory> // for auto_ptr
#include <ext/stdio_filebuf.h>
typedef __gnu_cxx::stdio_filebuf<char> stdio_filebuf;
#define GNUC_STDIO_FILEBUF_AVAILABLE
#endif

using namespace std;

static PyMethodDef tparseMethods[] = {
  {"parse", tparse, METH_VARARGS, tparse__doc__},
  {NULL, NULL}        /* Sentinel */
};

void inittparse()
{
  PyObject *m, *d, *common, *commondict;
  m = Py_InitModule3("tparse", tparseMethods, __doc__);

  common = PyImport_ImportModule("common");
  if (!common)
    return ; // Common not imported ?

  commondict = PyModule_GetDict(common);
  pyRCSStopParser = PyDict_GetItemString(commondict, "RCSStopParser");
  Py_INCREF(pyRCSStopParser);

  pyRCSParseError = PyDict_GetItemString(commondict, "RCSParseError");
  Py_INCREF(pyRCSParseError);

  pyRCSIllegalCharacter = PyDict_GetItemString(commondict, 
                                               "RCSIllegalCharacter");
  Py_INCREF(pyRCSIllegalCharacter);

  pyRCSExpected = PyDict_GetItemString(commondict, "RCSExpected");
  Py_INCREF(pyRCSExpected);

  PySink = PyDict_GetItemString(commondict, "Sink");
  Py_INCREF(PySink);

  d = PyModule_GetDict(m);

  PyDict_SetItemString(d, "__version__", PyString_FromString(__version__));
  PyDict_SetItemString(d, "__date__", PyString_FromString(__date__));
  PyDict_SetItemString(d, "__author__", PyString_FromString(__author__));
}

class PythonException
{
  public:
    PythonException() {};
};

class PythonSink : public Sink
{
  public:
    PyObject *sink;
    PythonSink(PyObject *mysink)
    {
      sink = mysink;
    };
    int set_head_revision(char * revision)
    {
      PyObject *rv = PyObject_CallMethod(sink, "set_head_revision", "s",
                                         revision);
      if (!rv) {
        delstr(revision);
        if (PyErr_ExceptionMatches(pyRCSStopParser))
          return 1;
        else
          throw PythonException();
      }
      else {
        Py_DECREF(rv);
      }
      delstr(revision);
      return 0;
    };
    int set_principal_branch(char *branch_name)
    {
      PyObject *rv = PyObject_CallMethod(sink, "set_principal_branch", "s",
                                         branch_name);
      if (!rv) {
        delstr(branch_name);
        if (PyErr_ExceptionMatches(pyRCSStopParser))
          return 1;
        else
          throw PythonException();
      }
      else {
        Py_DECREF(rv);
      }
      delstr(branch_name);
      return 0;
    };
    int define_tag(char *name, char *revision)
    {
      PyObject *rv = PyObject_CallMethod(sink, "define_tag", "ss",
                                         name, revision);
      if (!rv) {
        delstr(name);
        if (PyErr_ExceptionMatches(pyRCSStopParser))
          return 1;
        else
          throw PythonException();
      }
      else {
        Py_DECREF(rv);
      }
      delstr(name);
      return 0;
    };
    int set_comment(char *comment)
    {
      PyObject *rv = PyObject_CallMethod(sink, "set_comment", "s", comment);
      if (!rv) {
        delstr(comment);
        if (PyErr_ExceptionMatches(pyRCSStopParser))
          return 1;
        else
          throw PythonException();
      }
      else {
        Py_DECREF(rv);
      }
      delstr(comment);
      return 0;
    };
    int set_description(char *description)
    {
      PyObject *rv = PyObject_CallMethod(sink, "set_description", "s",
                                         description);
      if (!rv) {
        delstr(description);
        if (PyErr_ExceptionMatches(pyRCSStopParser))
          return 1;
        else
          throw PythonException();
      }
      else {
        Py_DECREF(rv);
      }
      delstr(description);
      return 0;
    };
    int define_revision(char *revision, long timestamp, char *author,
                        char *state, Branche *branches, char *next)
    {
      PyObject *pbranchs = PyList_New(0);
      Branche *move = branches;
      while (move != NULL)
      {
        PyObject *str = PyString_FromString(move->name);
        PyList_Append(pbranchs, str );
        Py_DECREF(str);
        move = move->next;
      }

      PyObject *rv = PyObject_CallMethod(sink, "define_revision", "slssOs",
                                         revision,timestamp,
                                         author,state,pbranchs,next);
      if (!rv) {
        Py_DECREF(pbranchs);
        delstr(revision);
        delstr(author);
        delstr(state);
        if (branches != NULL)
          delete branches;
        delstr(next);
        if (PyErr_ExceptionMatches(pyRCSStopParser))
          return 1;
        else
          throw PythonException();
      }
      else {
        Py_DECREF(rv);
      }
      Py_DECREF(pbranchs);
      delstr(revision);
      delstr(author);
      delstr(state);
      if (branches != NULL)
        delete branches;
      delstr(next);
      return 0;
    };
    int set_revision_info(char *revision, char *log, char *text)
    {
      PyObject *rv = PyObject_CallMethod(sink, "set_revision_info", "sss", 
                                         revision,log,text);
      if (!rv) {
        delstr(revision);
        delstr(log);
        delstr(text);
        if (PyErr_ExceptionMatches(pyRCSStopParser))
          return 1;
        else
          throw PythonException();
      }
      else {
        Py_DECREF(rv);
      }
      delstr(revision);
      delstr(log);
      delstr(text);
      return 0;
    };
    int tree_completed()
    {
      PyObject *rv = PyObject_CallMethod(sink, "tree_completed", NULL);
      if (!rv) {
        if (PyErr_ExceptionMatches(pyRCSStopParser))
          return 1;
        else
          throw PythonException();
      }
      else {
        Py_DECREF(rv);
      }
      return 0;
    };
    int parse_completed()
    {
      PyObject *rv = PyObject_CallMethod(sink, "parse_completed", NULL);
      if (!rv) {
        if (PyErr_ExceptionMatches(pyRCSStopParser))
          return 1;
        else
          throw PythonException();
      }
      else {
        Py_DECREF(rv);
      }
      return 0;

    };
};

static PyObject * tparse( PyObject *self, PyObject *args)
{
  char *filename;
  istream *input;
  PyObject *file = NULL;
  PyObject *hsink;
#ifdef GNUC_STDIO_FILEBUF_AVAILABLE
  auto_ptr<streambuf> rdbuf;
#endif

  if (PyArg_ParseTuple(args, "sO!", &filename, &PyInstance_Type, &hsink))
    input = new ifstream(filename, ios::in);
  else if (PyArg_ParseTuple(args, "O!O!", &PyFile_Type, &file, 
                            &PyInstance_Type, &hsink))
  {
    PyErr_Clear();   // Reset the exception PyArg_ParseTuple has raised.
#ifdef GNUC_STDIO_FILEBUF_AVAILABLE
    rdbuf.reset(new stdio_filebuf(PyFile_AsFile(file), ios::in | ios::binary));
    input = new istream(rdbuf.get());
#else
    PyErr_SetString(PyExc_NotImplementedError,
                    "tparse only implements the parsing of filehandles "
                    "when compiled with GNU C++ version 3.1 or later - "
                    "please pass a filename instead");
    return NULL;
#endif
  }
  else
    return NULL;

  if (!PyObject_IsInstance(hsink, PySink))
  {
    PyErr_SetString(PyExc_TypeError,
                    "Sink has to be an instance of class Sink.");
    return NULL;
  }

  Py_INCREF(hsink);
  Py_XINCREF(file);
  try
  {
    tparseParser tp(input, new PythonSink(hsink));
  }
  catch (RCSExpected e)
  {
    PyObject *exp = PyInstance_New(pyRCSExpected,
                                   Py_BuildValue("(ss)", e.got, e.wanted), 
                                   NULL);
    PyErr_SetObject(pyRCSExpected, exp);
    Py_DECREF(hsink);
    Py_XDECREF(file);
    return NULL;
  }
  catch (RCSIllegalCharacter e)
  {
    PyObject *exp = PyInstance_New(pyRCSIllegalCharacter,
                                   Py_BuildValue("(s)", e.value), NULL);
    PyErr_SetObject(pyRCSIllegalCharacter, exp);
    Py_DECREF(hsink);
    Py_XDECREF(file);
    return NULL;
  }
  catch (RCSParseError e)
  {
    PyObject *exp = PyInstance_New(pyRCSParseError,
                                   Py_BuildValue("(s)", e.value), NULL);
    PyErr_SetObject(pyRCSParseError, exp);
    Py_DECREF(hsink);
    Py_XDECREF(file);
    return NULL;
  }
  catch (PythonException e)
  {
    Py_DECREF(hsink);
    Py_XDECREF(file);
    return NULL;
  }
  Py_DECREF(hsink);
  Py_XDECREF(file);
  Py_INCREF(Py_None);
  return Py_None;
};
