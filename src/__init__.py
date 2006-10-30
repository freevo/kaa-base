# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# __init__.py - main kaa init module
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2005,2006 Dirk Meyer, Jason Tackaberry
#
# Please see the file AUTHORS for a complete list of authors.
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
import os
import stat

# import logger to update the Python logging module
import logger

# import some basic notifier functions
from kaa.notifier import signals, loop as main, shutdown

# strutils
import strutils

TEMP = '/tmp/kaa-%s' % os.getuid()

if os.path.isdir(TEMP):
    # temp dir is already there, check permissions
    if os.path.islink(TEMP):
        raise IOError('Security Error: %s is a link, aborted')
    if stat.S_IMODE(os.stat(TEMP)[stat.ST_MODE]) != 0700:
        raise IOError('Security Error: %s has wrong permissions, aborted')
    if os.stat(TEMP)[stat.ST_UID] != os.getuid():
        raise IOError('Security Error: %s does not belong to you, aborted')
else:
    os.mkdir(TEMP, 0700)
