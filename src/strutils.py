# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# strutils.py - Miscellaneous utilities for string handling
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2006 Dirk Meyer, Jason Tackaberry
#
# First Edition: Jason Tackaberry <tack@sault.org>
# Maintainer:    Jason Tackaberry <tack@sault.org>
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

__all__ = [ 'ENCODING', 'get_encoding', 'set_encoding', 'utf8',
            'str_to_unicode', 'unicode_to_str', 'format', 'to_unicode',
            'to_str' ]

# python imports
import locale

# find the correct encoding
try:
    ENCODING = locale.getdefaultlocale()[1]
    ''.encode(ENCODING)
except:
    ENCODING = 'latin-1'


def get_encoding():
    """
    Return the current encoding.
    """
    return ENCODING


def set_encoding(encoding):
    """
    Set encoding. This function won't set the global Python encoding because
    that is not possible. It will only set the encoding for the string helper
    functions defined in strutils.
    """
    global ENCODING
    ENCODING = encoding


def utf8(s):
    """
    Returns a UTF-8 string, converting from other character sets if
    necessary.
    """
    return to_unicode(s).encode("utf-8")


def str_to_unicode(s):
    """
    Attempts to convert a string of unknown character set to a unicode
    string.  First it tries to decode the string based on the locale's
    preferred encoding, and if that fails, fall back to UTF-8 and then
    latin-1.  If all fails, it will force encoding to the preferred
    charset, replacing unknown characters. If the given object is no
    string, this function will return the given object.
    """
    if not type(s) == str:
        return s

    for c in (ENCODING, "utf-8", "latin-1"):
        try:
            return s.decode(c)
        except UnicodeDecodeError:
            pass

    return s.decode(ENCODING, "replace")


def unicode_to_str(s):
    """
    Attempts to convert a unicode string of unknown character set to a
    string.  First it tries to encode the string based on the locale's
    preferred encoding, and if that fails, fall back to UTF-8 and then
    latin-1.  If all fails, it will force encoding to the preferred
    charset, replacing unknown characters. If the given object is no
    unicode string, this function will return the given object.
    """
    if not type(s) == unicode:
        return s

    for c in (ENCODING, "utf-8", "latin-1"):
        try:
            return s.encode(c)
        except UnicodeDecodeError:
            pass

    return s.encode(ENCODING, "replace")


def format(s, *args):
    """
    Format a string and make sure all string or unicode arguments are
    converted to the correct type.
    """
    if type(s) == str:
        return s % tuple([ unicode_to_str(x) for x in args ])
    if type(s) == unicode:
        return s % tuple([ str_to_unicode(x) for x in args ])
    raise AttributeError("no format string given")


def to_unicode(s):
    """
    Attempts to convert every object to an unicode string using the objects
    __unicode__ or __str__ function or str_to_unicode.
    """
    if type(s) == unicode:
        return s
    if type(s) == str:
        return str_to_unicode(s)
    try:
        return unicode(s)
    except UnicodeDecodeError:
        return str_to_unicode(str(s))


def to_str(s):
    """
    Attempts to convert every object to a string using the objects
    __unicode__ or __str__ function or unicode_to_str.
    """
    if type(s) == str:
        return s
    if type(s) == unicode:
        return unicode_to_str(s)
    try:
        return unicode_to_str(unicode(s))
    except UnicodeDecodeError:
        return str(s)
