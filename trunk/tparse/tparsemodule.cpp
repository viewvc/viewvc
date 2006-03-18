/*
# Copyright (C) 2000-2002 The ViewCVS Group. All Rights Reserved.
# This file has been rewritten in C++ from the rcsparse.py file by
# Lucas Bruand <lucas.bruand@ecl2002.ec-lyon.fr>
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# This software is being maintained as part of the ViewVC project.
# Information is available at:
#    http://viewvc.org/
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

#include <fstream>

#include "tparsemodule.h"
#include "tparse.cpp"

#if (__GNUC__ >= 4) || (__GNUC__ == 3 && __GNUC_MINOR__ >= 1)
#include <memory> // for auto_ptr
#include <ext/stdio_filebuf.h>
typedef __gnu_cxx::stdio_filebuf<char> stdio_filebuf;
#define GNUC_STDIO_FILEBUF_AVAILABLE
#endif

using namespace std;

class PythonException
{
  public:
    PythonException() {};
};


class pyobject
{
  private:
    PyObject *obj;
  public:
    pyobject(PyObject *myobj)
    {
      obj = myobj;
    }
    ~pyobject()
    {
      Py_XDECREF(obj);
    };
    PyObject *operator*()
    {
      return obj;
    };
};


class pystring : public pyobject
{
public:
  pystring(const char *s) :
    pyobject(PyString_FromString(s))
  {};
  pystring(rcstoken& t) :
    pyobject(PyString_FromStringAndSize(t.data, t.length))
  {};
};


static
void chkpy(PyObject *obj)
{
  Py_XDECREF(obj);
  if (!obj)
    throw PythonException();
};



static PyMethodDef tparseMethods[] = {
  {"parse", tparse, METH_VARARGS, tparse__doc__},
  {NULL, NULL}        /* Sentinel */
};

void inittparse()
{
  PyObject *m, *d, *common, *commondict;
  pystring ver(__version__),
    dat(__date__),
    aut(__author__);
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

  PyDict_SetItemString(d, "__version__", *ver);
  PyDict_SetItemString(d, "__date__", *dat);
  PyDict_SetItemString(d, "__author__", *aut);
}

class PythonSink : public Sink
{
  public:
    PyObject *sink;
    PythonSink(PyObject *mysink)
    {
      sink = mysink;
      Py_INCREF(sink);
    };
    virtual ~PythonSink() throw ()
    {
      Py_DECREF(sink);
    };
    virtual void set_head_revision(rcstoken &revision)
    {
      chkpy(PyObject_CallMethod(sink, "set_head_revision", "s",
                                revision.data));
    };
    virtual void set_principal_branch(rcstoken &branch_name)
    {
      chkpy(PyObject_CallMethod(sink, "set_principal_branch",
                                "s", branch_name.data));
    };
    virtual void define_tag(rcstoken &name, rcstoken &revision)
    {
      chkpy(PyObject_CallMethod(sink, "define_tag", "ss",
                                name.data, revision.data));
    };
    virtual void set_comment(rcstoken &comment)
    {
      pystring c(comment);
      chkpy(PyObject_CallMethod(sink, "set_comment", "S", *c));
    };
    virtual void set_description(rcstoken &description)
    {
      pystring d(description);
      chkpy(PyObject_CallMethod(sink, "set_description", "S", *d));
    };
    virtual void define_revision(rcstoken &revision, long timestamp,
                                 rcstoken &author, rcstoken &state,
                                 tokenlist &branches, rcstoken &next)
    {
      pyobject branchlist(PyList_New(0));
      tokenlist_iter branch;

      for (branch = branches.begin(); branch != branches.end(); branch++)
        {
          pystring str(*branch);
          PyList_Append(*branchlist, *str);
        }

      chkpy(PyObject_CallMethod(sink, "define_revision", "slssOs",
                                revision.data,timestamp,
                                author.data,state.data,*branchlist,
                                next.data));
    };
    virtual void set_revision_info(rcstoken& revision,
                                   rcstoken& log, rcstoken& text)
    {
      pystring l(log), txt(text);
      chkpy(PyObject_CallMethod(sink, "set_revision_info", "sSS",
                                revision.data, *l, *txt));
    };
    virtual void tree_completed()
    {
      chkpy(PyObject_CallMethod(sink, "tree_completed", NULL));
    };
    virtual void parse_completed()
    {
      chkpy(PyObject_CallMethod(sink, "parse_completed", NULL));
    };
};

static PyObject * tparse( PyObject *self, PyObject *args)
{
  char *filename;
  istream *input = NULL;
  PyObject *file = NULL;
  PyObject *hsink;
  PyObject *rv = Py_None;
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

  try
  {
    tparseParser tp(input, new PythonSink(hsink));
    tp.parse();
  }
  catch (RCSExpected e)
  {
    const char *got = e.got.c_str();
    const char *wanted = e.wanted.c_str();

    pyobject arg(Py_BuildValue("(ss)", got, wanted)),
      exp(PyInstance_New(pyRCSExpected, *arg, NULL));
    PyErr_SetObject(pyRCSExpected, *exp);

    delete [] got;
    delete [] wanted;
    rv = NULL;
  }
  catch (RCSIllegalCharacter e)
  {
    const char *value = e.value.c_str();

    pyobject arg(Py_BuildValue("(s)", value)),
      exp(PyInstance_New(pyRCSIllegalCharacter,*arg, NULL));
    PyErr_SetObject(pyRCSIllegalCharacter, *exp);

    delete [] value;
    rv = NULL;
  }
  catch (RCSParseError e)
  {
    const char *value = e.value.c_str();

    pyobject arg(Py_BuildValue("(s)", value)),
      exp(PyInstance_New(pyRCSParseError, *arg, NULL));
    PyErr_SetObject(pyRCSParseError, *exp);

    delete [] value;
    rv = NULL;
  }
  catch (PythonException e)
  {
    if (! PyErr_ExceptionMatches(pyRCSStopParser))
      rv = NULL;
    else
      PyErr_Clear();
  }

  Py_XINCREF(rv);
  return rv;
};
