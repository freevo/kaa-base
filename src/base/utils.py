# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# utils.py - Miscellaneous utilities
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2005 Dirk Meyer, Jason Tackaberry
#
# First Edition: Jason Tackaberry <tack@sault.org>
# Maintainer:    Jason Tackaberry <tack@sault.org>
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

import sys, tty, termios, select, fcntl, os, atexit, weakref, types

############################################################################

_tc_orig_settings = None
_getch_enabled = False

def getch(timeout = None):
    global _getch_enabled
    if not _getch_enabled:
        getch_enable()
        _getch_enabled = True

    fd = sys.stdin.fileno()

    if timeout != None:
        (rfds, wfds, efds) = select.select([fd], [], [], timeout)
        if rfds == []:
            return False

    ch = sys.stdin.read(1)
    if ord(ch) == 27:
        ch = sys.stdin.read(1)
        if ch == '[':
            ch = sys.stdin.read(1)
            ch = ord(ch) + 255

    if type(ch) == type(''):
        return ord(ch)
    return ch


def getch_enable():
    global _tc_orig_settings
    _tc_orig_settings = termios.tcgetattr(sys.stdin.fileno())
    tc = termios.tcgetattr(sys.stdin.fileno())
    tc[3] = tc[3] & ~(termios.ICANON | termios.ECHO)
    tc[6][termios.VMIN] = 1
    tc[6][termios.VTIME] = 0
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, tc)
    atexit.register(getch_disable)
    

def getch_disable():
    global _tc_orig_settings
    if _tc_orig_settings != None:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _tc_orig_settings)
    os.system("stty echo")

    
############################################################################

def utf8(text):
    """
    Returns a UTF-8 string, converting from latin-1 if necessary.  This does a
    pretty good job Doing the Right Thing, converting only when it's really
    latin-1.  Of course it's not foolproof, but it works in practice.
    """
    if type(text) == types.UnicodeType:
        return text.encode("utf-8")

    try:
        text.decode("utf-8")
    except:
        try:
            text = text.decode("latin-1").encode("utf-8")
        except:
            pass

    return text


############################################################################


def make_weakref(object, callback = None):
    if type(object) == weakref.ReferenceType or not object:
        return object
    if callback:
        return weakref.ref(object, callback)
    else:
        return weakref.ref(object)

def check_weakref(object):
    if not object:
        return None
    if not object():
        return None

    return object


