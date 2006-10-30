# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# decorators.py - some helping decorators
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2006 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
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
import sys
import logging

# get logging object
log = logging.getLogger()


def save_execution():
    """
    Catch all exceptions from the function. The return value
    will be dropped.
    """
    def decorator(func):

        def newfunc(*args, **kwargs):
            try:
                func(*args, **kwargs)
            except (KeyboardInterrupt, SystemExit), e:
                sys.exit(0)
            except Exception, e:
                log.exception('crash:')

        newfunc.func_name = func.func_name
        return newfunc

    return decorator
