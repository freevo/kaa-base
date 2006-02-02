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

from distutils.core import setup, Extension

extensions = []
try:
    import shm
except ImportError:
    print "Building kaa shm module (no system shm module already available)."
    extensions.append( Extension('shmmodule', ['src/extensions/shmmodule.c']) )

# call setup
setup(
    name             = 'kaa-base',
    version          = '0.1',
    maintainer       = 'The Freevo Project',
    maintainer_email = 'developer@freevo.org',
    url              = 'http://www.freevo.org/kaa',
    package_dir      = { 'kaa': 'src', 'kaa.base': 'src/base',
                         'kaa.notifier': 'src/notifier', 'kaa.input': 'src/input' },
    packages         = [ 'kaa', 'kaa.base', 'kaa.notifier', 'kaa.input' ],
    ext_modules      = extensions)
