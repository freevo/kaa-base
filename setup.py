# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# setup.py - Setup script for kaa.base
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2005, 2006 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# This library is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version
# 2.1 as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301 USA
#
# -----------------------------------------------------------------------------

# python imports
import sys
import os
import time
import distutils.sysconfig

# We require python 2.4 or later, so complain if that isn't satisfied.
if sys.version.split()[0] < '2.4':
    print "Python 2.4 or later required."
    sys.exit(1)

# We have some extensions but kaa.distribution isn't installed yet.  So import
# it directly from the source tree.  First add src/ to the modules patch ...
sys.path.append("src")
# ... and now import it.
from distribution.core import Extension, setup

ext = Extension('kaa.shmmodule', ['src/extensions/shmmodule.c'])
extensions = [ ext ]

objectrow = Extension('kaa._objectrow', ['src/extensions/objectrow.c'])
if objectrow.check_library("glib-2.0", "2.4.0"):
    extensions.append(objectrow)
else:
    print "glib >= 2.4.0 not found; kaa.db will be unavailable"

inotify_ext = Extension("kaa.inotify._inotify",
                        ["src/extensions/inotify/inotify.c"],
                        config='src/extensions/inotify/config.h')

if not inotify_ext.check_cc(["<sys/inotify.h>"], "inotify_init();"):
    if not inotify_ext.check_cc(["<sys/syscall.h>"], "syscall(0);"):
        print "inotify not enabled: doesn't look like a Linux system."
    else:
        print "inotify not supported in glibc; no problem, using built-in support instead."
        inotify_ext.config("#define USE_FALLBACK")
        extensions.append(inotify_ext)

else:
    print "inotify supported by glibc; good."
    extensions.append(inotify_ext)

if not os.path.exists(os.path.join(distutils.sysconfig.get_python_inc(), 'Python.h')):
    print "---------------------------------------------------------------------"
    print "Python headers not found; please install python development package."
    print "kaa.db and inotify support will be unavailable"
    print "---------------------------------------------------------------------"
    time.sleep(2)
    extensions = []
    
# call setup
setup(
    module       = 'base',
    version      = '0.1.4',
    license      = 'LGPL',
    summary      = 'Base module for all Kaa modules.',
    rpminfo      = {
        'requires':       'glib2 >= 2.6.0, python-sqlite2 >= 2.3.0, libxml2-python >= 2.6.0',
        'build_requires': 'glib2-devel >= 2.6.0, python-devel >= 2.4.0'
    },
    ext_modules  = extensions)
