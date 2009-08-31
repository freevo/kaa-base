# -* -coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# tls/__init__.py - TLS support for the Kaa Framework
# -----------------------------------------------------------------------------
# $Id$
#
# This module wraps TLS for client and server based on tlslite. See
# http://trevp.net/tlslite/docs/public/tlslite.TLSConnection.TLSConnection-class.html
# for more information about optional paramater.
#
# -----------------------------------------------------------------------------
# Copyright 2008-2009 Dirk Meyer, Jason Tackaberry
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

from common import *

try:
    from m2 import M2TLSSocket
except ImportError:
    M2TLSSocket = None

try:
    from tlslite import TLSAuthenticationError, TLSKey, TLSLiteConnection, TLSLiteSocket
except ImportError:
    TLSLiteSocket = None

# FIXME: for now, keep TLSLiteSocket as general TLSSocket object
TLSSocket = TLSLiteSocket or M2TLSSocket

if TLSLiteSocket == M2TLSSocket == None:
    raise ImportError('No suitable TLS backend found: tried tlslite and M2Crypto')

