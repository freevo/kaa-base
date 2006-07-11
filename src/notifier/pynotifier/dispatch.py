#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# dispatcher.py
#
# Author: Andreas Büsching <crunchy@bitkipper.net>
#
# generic notifier implementation
#
# $Id$
#
# Copyright (C) 2006 Andreas Büsching <crunchy@bitkipper.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

"""generic implementation of external dispatchers, integratable into
several notifiers."""

from copy import copy

# required for dispatcher use
MIN_TIMER = 100

__dispatchers = []

def dispatcher_add( method ):
    """The notifier supports external dispatcher functions that will be called
    within each scheduler step. This functionality may be usful for
    applications having an own event mechanism that needs to be triggered as
    often as possible. This method registers a new dispatcher function. To
    ensure that the notifier loop does not suspend to long in the sleep state
    during the select a minimal timer MIN_TIMER is set to guarantee that the
    dispatcher functions are called at least every MIN_TIMER milliseconds."""
    global __dispatchers
    __dispatchers.append( method )

def dispatcher_remove( method ):
    """Removes an external dispatcher function from the list"""
    global __dispatchers
    if method in __dispatchers:
        __dispatchers.remove( method )

def dispatcher_run():
    for disp in copy( __dispatchers ):
        if not disp():
            dispatcher_remove( disp )


