# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# signals.py - Signal handling for the notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa-notifier - Notifier Wrapper
# Copyright (C) 2005 Dirk Meyer, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# Please see the file doc/AUTHORS for a complete list of authors.
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

from signal import *
from callback import OneShotTimer

_signal_dict = {}
_signal_list = []

def register(sig, function):
    """
    Register a signal handler.
    """
    _signal_dict[sig] = function
    signal(sig, _signal_catch)


def has_signal():
    """
    Return True if there are signals in the queue.
    """
    return _signal_list


def _signal_handler():
    """
    Call all registered signal handler.
    """
    while _signal_list:
        sig = _signal_list.pop(0)
        _signal_dict[sig](sig)
    return False


_signal_timer = OneShotTimer(_signal_handler)

def _signal_catch(sig, frame):
    """
    Catch signals to be called from the main loop.
    """
    if not sig in _signal_list:
        # add catched signal to the list
        _signal_list.append(sig)
    # FIXME: let's hope this works because the handler
    # is called asynchron
    if not _signal_timer.active():
        _signal_timer.start(0)
    return True
