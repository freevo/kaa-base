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
from kaa.notifier import loop as main

# strutils
import strutils

# tempfile support. FIXME: remove TEMP when no longer used
from tmpfile import tempfile, TEMP
