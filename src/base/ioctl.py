# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------
# ioctl.py - A module to make ioctl's in python easier.
# -----------------------------------------------------------------------
# $Id$
#
# Notes:
# Todo:        
#
# -----------------------------------------------------------------------------
# kaa-base - base module for kaa
# Copyright (C) 2005 Dirk Meyer, Jason Tackaberry
#
# First Edition: Rob Shortt <rob@tvcentric.com>
# Maintainer:    Rob Shortt <rob@tvcentric.com>
#
# Please see the file doc/CREDITS for a complete list of authors.
# -----------------------------------------------------------------------
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
# ----------------------------------------------------------------------- */


import sys
import struct
import fcntl

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_DIRBITS = 2

_IOC_NRMASK = ((1 << _IOC_NRBITS)-1)
_IOC_TYPEMASK = ((1 << _IOC_TYPEBITS)-1)
_IOC_SIZEMASK = ((1 << _IOC_SIZEBITS)-1)
_IOC_DIRMASK = ((1 << _IOC_DIRBITS)-1)

_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = (_IOC_NRSHIFT+_IOC_NRBITS)
_IOC_SIZESHIFT = (_IOC_TYPESHIFT+_IOC_TYPEBITS)
_IOC_DIRSHIFT = (_IOC_SIZESHIFT+_IOC_SIZEBITS)

# Direction bits.
_IOC_NONE = 0
_IOC_WRITE = 1
_IOC_READ = 2

def _IOC(dir,type,nr,size):
    # Note: this functions uses lshift to avoid future warnings. It
    # may not work every time and is more or less a bad hack
    return (long(dir) << _IOC_DIRSHIFT) | (ord(type) << _IOC_TYPESHIFT) | \
           (nr << _IOC_NRSHIFT) | (size << _IOC_SIZESHIFT)

def IO(type,nr):
    return _IOC(_IOC_NONE,(type),(nr),0)

def IOR(type,nr,size):
    return _IOC(_IOC_READ,(type),(nr),struct.calcsize(size))

def IOW(type,nr,size):
    return _IOC(_IOC_WRITE,(type),(nr),struct.calcsize(size))

def IOWR(type,nr,size):
    return _IOC(_IOC_READ|_IOC_WRITE,(type),(nr),struct.calcsize(size))

# used to decode ioctl numbers..
def IOC_DIR(nr): return (((nr) >> _IOC_DIRSHIFT) & _IOC_DIRMASK)
def IOC_TYPE(nr): return (((nr) >> _IOC_TYPESHIFT) & _IOC_TYPEMASK)
def IOC_NR(nr): return (((nr) >> _IOC_NRSHIFT) & _IOC_NRMASK)
def IOC_SIZE(nr): return (((nr) >> _IOC_SIZESHIFT) & _IOC_SIZEMASK)

def ioctl(fd, code, *args, **kargs):
    if code > sys.maxint:
        code = int(~(-code % sys.maxint) - 1)
    return fcntl.ioctl(fd, code, *args, **kargs)
    
pack   = struct.pack
unpack = struct.unpack
