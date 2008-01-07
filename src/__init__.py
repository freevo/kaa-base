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

# import logger to update the Python logging module
import logger

# import notifier functions into kaa namespace
from kaa.notifier import *

# strutils
import strutils

# tempfile support. FIXME: remove TEMP when no longer used
from tmpfile import tempfile, TEMP


# XXX: when support for deprecated API is removed, everything below can be deleted
# and replaced by 'from kaa.notifier import main'
import kaa.notifier.main

class MainWrapper:
    signals = kaa.notifier.main.signals

    def __call__(self):
        import logging
        log = logging.getLogger('notifier')
        log.warning('Deprecated call to kaa.main(); use kaa.main.start() instead')
        return kaa.notifier.main.start()

    # Wrappers for new API.
    def start(self):
        return kaa.notifier.main.start()

    def step(self):
        return kaa.notifier.main.step()

    def stop(self):
        return kaa.notifier.main.stop()

    def is_running(self):
        return kaa.notifier.main.is_running()

    def select_notifier(self, *args, **kwargs):
        return kaa.notifier.main.select_notifier(*args, **kwargs)

    def __getattr__(self, attr):
        return getattr(kaa.notifier.main, attr)
    
main = MainWrapper()
