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

import sys, tty, termios, select, fcntl, os, atexit, types, locale

############################################################################

_tc_orig_settings = None
_getch_enabled = False

_keycode_names = {
    "\x1b\x5b\x41": "up",
    "\x1b\x5b\x42": "down",
    "\x1b\x5b\x43": "right",
    "\x1b\x5b\x44": "left",

    "\x1b\x4f\x50": "F1",
    "\x1b\x4f\x51": "F2",
    "\x1b\x4f\x52": "F3",
    "\x1b\x4f\x53": "F4",
    "\x1b\x5b\x31\x35\x7e": "F5",
    "\x1b\x5b\x31\x37\x7e": "F6",
    "\x1b\x5b\x31\x38\x7e": "F7",
    "\x1b\x5b\x31\x39\x7e": "F8",
    "\x1b\x5b\x32\x30\x7e": "F9",
    "\x1b\x5b\x32\x31\x7e": "F10",
    "\x1b\x5b\x32\x33\x7e": "F11",
    "\x1b\x5b\x32\x34\x7e": "F12",

    "\x1b\x5b\x32\x7e": "ins",
    "\x1b\x5b\x33\x7e": "del",
    "\x1b\x4f\x46": "end",
    "\x1b\x4f\x48": "home",
    "\x1b\x1b": "esc",
    "\x0a": "enter",
    "\x20": "space",
    "\x7f": "backspace"
}
    
def getch():
    global _getch_enabled

    if not _getch_enabled:
        getch_enable()
        _getch_enabled = True

    buf = sys.stdin.read(1)
    while buf in ("\x1b", "\x1b\x4f", "\x1b\x5b") or \
          buf[:3] in ("\x1b\x5b\x31", "\x1b\x5b\x32", "\x1b\x5b\x33"):
        buf += sys.stdin.read(1)
        if buf[-1] == "\x7e":
            break

    #print "KEYCODE:"
    #for c in buf:
    #    print "  " +  hex(ord(c)) 
    code = buf
    #buf = ""
    if code in _keycode_names:
        return _keycode_names[code]
    elif len(code) == 1:
        return code
    else:
        return "??"


def getch_enable():
    global _tc_orig_settings
    _tc_orig_settings = termios.tcgetattr(sys.stdin.fileno())
    tc = termios.tcgetattr(sys.stdin.fileno())
    tc[3] = tc[3] & ~(termios.ICANON | termios.ECHO)
    tc[6][termios.VMIN] = 1
    tc[6][termios.VTIME] = 0
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, tc)
    atexit.register(getch_disable)
    

def getch_disable():
    global _tc_orig_settings
    if _tc_orig_settings != None:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, _tc_orig_settings)
    os.system("stty echo")

    
############################################################################

def utf8(s):
    """
    Returns a UTF-8 string, converting from other character sets if
    necessary.
    """
    return str_to_unicode(s).encode("utf-8")

def str_to_unicode(s):
    """
    Attempts to convert a string of unknown character set to a unicode
    string.  First it tries to decode the string based on the locale's
    preferred encoding, and if that fails, fall back to UTF-8 and then
    latin-1.  If all fails, it will force encoding to the preferred
    charset, replacing unknown characters.
    """
    if type(s) == unicode:
        # Already unicode
        return s

    for c in (locale.getpreferredencoding(), "utf-8", "latin-1"):
        try:
            return s.decode(c)
        except UnicodeDecodeError:
            pass

    return s.decode(local.getpreferredencoding(), "replace")


############################################################################


