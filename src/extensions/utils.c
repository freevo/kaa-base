/*
 * ----------------------------------------------------------------------------
 * Miscellaneous low-level functions
 * ----------------------------------------------------------------------------
 * $Id$
 * ----------------------------------------------------------------------------
 * Copyright (C) 2007-2009 Jason Tackaberry
 *
 * First Edition: Jason Tackaberry <tack@urandom.ca>
 * Maintainer:    Jason Tackaberry <tack@urandom.ca>
 *
 * Please see the file AUTHORS for a complete list of authors.
 *
 * This library is free software; you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License version
 * 2.1 as published by the Free Software Foundation.
 *
 * This library is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
 * 02110-1301 USA
 *
 * ----------------------------------------------------------------------------
 */

#include "Python.h"
#include "config.h"
#ifdef HAVE_PRCTL
#include <sys/prctl.h>
#endif

extern void Py_GetArgcArgv(int *argc, char ***argv);

PyObject *set_process_name(PyObject *self, PyObject *args)
{
#ifdef HAVE_PRCTL
    int argc, limit;
    char **argv, *name;

    if (!PyArg_ParseTuple(args, "si", &name, &limit))
        return NULL;

    Py_GetArgcArgv(&argc, &argv);
    memset(argv[0], 0, limit);
    strncpy(argv[0], name, limit-1);

    // Needed for killall
    prctl(PR_SET_NAME, argv[0], 0, 0, 0);
#endif
    Py_INCREF(Py_None);
    return Py_None;
}

PyMethodDef utils_methods[] = {
    {"set_process_name",  set_process_name, METH_VARARGS },
    { NULL }
};

void init_utils(void)
{
    Py_InitModule("_utils", utils_methods);
}
