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
 	this python extension module is a binding to the tparse library.
 	tparse is a C++ library that offers an API to a performance-oriented RCSFILE parser.
 	It does little syntax checking.
 	
 	Version: $Id$
 */
#include <Python.h>
#include <stdiostream.h>
#include "tparsemodule.h"
#include "tparse.cpp"

static PyMethodDef tparseMethods[] = {
    {"parse",  tparse, METH_VARARGS, tparse__doc__},
    {NULL,      NULL}        /* Sentinel */
};

void inittparse()
{
    PyObject *m, *d;
    m= Py_InitModule3("tparse", tparseMethods,__doc__);
    d = PyModule_GetDict(m);
    StopParser = PyErr_NewException("tparse.stopparser", NULL, NULL);
    PyObject_SetAttrString(StopParser,"__doc__",PyString_FromString(StopParser__doc__));
    PyDict_SetItemString(d, "stopparser", StopParser);
    PyDict_SetItemString(d, "__version__", PyString_FromString(__version__));
    PyDict_SetItemString(d, "__date__", PyString_FromString(__date__));
    PyDict_SetItemString(d, "__author__", PyString_FromString(__author__));
}

class PythonException {
	public:
	PythonException() {};
};

class PythonSink : public Sink {
	public:
	PyObject *sink;
	PythonSink(PyObject *mysink)
	{ sink=mysink;};
	int set_head_revision(char * revision) 
	{
		if (!PyObject_CallMethod(sink,"set_head_revision", "s", revision)) {
			delstr(revision);
			if (PyErr_ExceptionMatches(StopParser))
				return 1;
			else  
				throw PythonException();
		}
		delstr(revision);
		return 0;
	};
	int set_principal_branch(char *branch_name) 
	{
		if (!PyObject_CallMethod(sink,"set_principal_branch", "s", branch_name)) {
			delstr(branch_name);
			if (PyErr_ExceptionMatches(StopParser)) 
				return 1;
			else 
				throw PythonException();
		}
		delstr(branch_name);
		return 0;
	};
	int define_tag(char *name, char *revision)
	{
		if (!PyObject_CallMethod(sink,"define_tag", "ss", name,revision)) {
			delstr(name);
			if (PyErr_ExceptionMatches(StopParser))
				return 1;
			else 
				throw PythonException();
		}
		delstr(name);
		return 0;
	};
	int set_comment(char *comment)
	{
		if (!PyObject_CallMethod(sink,"set_comment", "s", comment)) {
			delstr(comment);
			if (PyErr_ExceptionMatches(StopParser)) 
				return 1;
			else 
				throw PythonException();
		}
		delstr(comment);
		return 0;
	};
	int set_description(char *description) 
	{
		if (!PyObject_CallMethod(sink,"set_description", "s", description)) {
			delstr(description);
			if (PyErr_ExceptionMatches(StopParser))
				return 1;
			else 
				throw PythonException();
		}
		delstr(description);
		return 0;
	};
	int define_revision(char *revision, long timestamp, char *author, char *state, Branche *branches, char *next)
	{
		PyObject *pbranchs=PyList_New(0);
		Py_INCREF(pbranchs);
		Branche *move=branches;
		while (move!=NULL) {
			PyList_Append(pbranchs, PyString_FromString(move->name) );
			move=move->next;
		}
		
		if (!PyObject_CallMethod(sink,"define_revision", "slssOs",revision,timestamp,author,state,pbranchs,next))
		{
			Py_DECREF(pbranchs);
			delstr(revision);
			delstr(author);
			delstr(state);
			if (branches!=NULL) delete branches;delstr(next);
			if (PyErr_ExceptionMatches(StopParser))
				return 1;
			else 
				throw PythonException();
		}
		Py_DECREF(pbranchs);
		delstr(revision);
		delstr(author);
		delstr(state);
		if (branches!=NULL) delete branches;delstr(next);
		return 0;
	};
	int set_revision_info(char *revision, char *log, char *text) 
	{
		if (!PyObject_CallMethod(sink,"set_revision_info", "sss", revision,log,text))
		{
			delstr(revision);
			delstr(log);
			delstr(text);
			if (PyErr_ExceptionMatches(StopParser)) 
				return 1;
			else
				throw PythonException();
		}
		delstr(revision);
		delstr(log);
		delstr(text);
		return 0;
	};
  	int tree_completed()
  	{
  		if (!PyObject_CallMethod(sink,"tree_completed", NULL))
  		{
			if (PyErr_ExceptionMatches(StopParser)) 
  				return 1;
  			else
  				throw PythonException();
  		}
  		return 0;
  	};
  	int parse_completed()
  	{
  		if (!PyObject_CallMethod(sink,"parse_completed", NULL))
  		{
			if (PyErr_ExceptionMatches(StopParser)) 
  				return 1;
  			else
  				throw PythonException();
  		}
  		return 0;
  		
  	};
};


static PyObject * tparse( PyObject *self, PyObject *args)
{
	char *filename;
	ifstream *input;
	PyObject *file=NULL;
	PyObject *hsink;
	
	if (PyArg_ParseTuple(args, "sO!", &filename,&PyInstance_Type,&hsink))
        	input=new ifstream(filename,ios::nocreate|ios::in);
    	else if (PyArg_ParseTuple(args, "O!O!",&PyFile_Type ,&file,&PyInstance_Type, &hsink))
    		input=(ifstream *) new stdiobuf(PyFile_AsFile(file));
    	else
    		return NULL;
    	Py_INCREF(hsink);
    	Py_XINCREF(file);
    	try {
    		tparseParser *tp=new tparseParser(input,new PythonSink(hsink) );
    	}
    	catch (tparseException e) 
        {
        	PyErr_SetString(PyExc_Exception,e.getvalue());
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

}
