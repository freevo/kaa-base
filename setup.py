# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# setup.py - Setup script for kaa.base
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2005 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MER-
# CHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
#
# -----------------------------------------------------------------------------

from distutils.core import setup

# We have some extensions but kaa.distribution isn't installed yet.  So import
# it directly from the source tree.  First add src/ to the modules patch ...
import sys
sys.path.insert(0, "src")
# ... and now import it.
from distribution import Extension

extensions = []
extensions.append(Extension('kaa.shmmodule', ['src/extensions/shmmodule.c']).convert())

inotify_ext = Extension("kaa.inotify._inotify",
                        ["src/extensions/inotify/inotify.c"],
                        config='src/extensions/inotify/config.h')

if not inotify_ext.check_cc(["<sys/inotify.h>"], "inotify_init();"):
    if not inotify_ext.check_cc(["<sys/syscall.h>"], "syscall(0);"):
        print "inotify not enabled: doesn't look like a Linux system."
    else:
        print "inotify not supported in glibc; using fallback."
        inotify_ext.config("#define USE_FALLBACK")
        extensions.append(inotify_ext.convert())

else:
    print "inotify supported by glibc; good."
    extensions.append(inotify_ext.convert())


# call setup
setup(
    name             = 'kaa-base',
    version          = '0.1',
    maintainer       = 'The Freevo Project',
    maintainer_email = 'developer@freevo.org',
    url              = 'http://www.freevo.org/kaa',
    package_dir      = { 'kaa': 'src', 
                         'kaa.notifier': 'src/notifier',
                         'kaa.input': 'src/input',
                         'kaa.inotify': 'src/extensions/inotify' },
    packages         = [ 'kaa', 'kaa.notifier', 'kaa.input', 'kaa.inotify' ],
    ext_modules      = extensions)
