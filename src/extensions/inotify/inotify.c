/*
 * ----------------------------------------------------------------------------
 * Inotify module for Python
 * ----------------------------------------------------------------------------
 * $Id$
 *
 * ----------------------------------------------------------------------------
 * Copyright (C) 2006 Jason Tackaberry <tack@sault.org>
 *
 * First Edition: Jason Tackaberry <tack@sault.org>
 * Maintainer:    Jason Tackaberry <tack@sault.org>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of MER-
 * CHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
 * Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
 *
 * ----------------------------------------------------------------------------
 */

#include <Python.h>
#include "config.h"

#include <inttypes.h>

#ifdef USE_FALLBACK
#   include "fallback-inotify.h"
#   include "fallback-inotify-syscalls.h"
#else
#   include <sys/inotify.h>
#endif

PyObject *init(PyObject *self, PyObject *args)
{
    int fd = inotify_init();
    return Py_BuildValue("l", fd);
}

PyObject *add_watch(PyObject *self, PyObject *args)
{
    int fd;
    uint32_t mask;
    char *name;

    if (!PyArg_ParseTuple(args, "isi", &fd, &name, &mask))
        return NULL;

    return Py_BuildValue("l", inotify_add_watch(fd, name, mask));
}

PyObject *rm_watch(PyObject *self, PyObject *args)
{
    int fd;
    uint32_t wd;

    if (!PyArg_ParseTuple(args, "ii", &fd, &wd))
        return NULL;

    return Py_BuildValue("l", inotify_rm_watch(fd, wd));
}


PyMethodDef inotify_methods[] = {
    { "init", init, METH_VARARGS }, 
    { "add_watch", add_watch, METH_VARARGS }, 
    { "rm_watch", rm_watch, METH_VARARGS }, 
    { NULL }
};


void init_inotify()
{
    PyObject *m = Py_InitModule("_inotify", inotify_methods);
    #define add_const(x) PyModule_AddObject(m, #x, PyLong_FromLong(IN_ ## x));
    add_const(ACCESS);
    add_const(MODIFY);
    add_const(ATTRIB);
    add_const(CLOSE_WRITE);
    add_const(CLOSE_NOWRITE);
    add_const(CLOSE);
    add_const(OPEN);
    add_const(MOVED_FROM);
    add_const(MOVED_TO);
    add_const(MOVE);
    add_const(CREATE);
    add_const(DELETE);
    add_const(DELETE_SELF);
    add_const(MOVE_SELF);
    add_const(UNMOUNT);
    add_const(Q_OVERFLOW);
    add_const(IGNORED);
    add_const(ISDIR);
    add_const(ONESHOT);
    add_const(ALL_EVENTS);
}
