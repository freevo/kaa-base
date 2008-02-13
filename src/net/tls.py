# -* -coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# tls.py - TLS support for kaa.notifier based on tlslite
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2008 Dirk Meyer
#
# First Edition: Dirk Meyer <dischi@freevo.org>
# Maintainer:    Dirk Meyer <dischi@freevo.org>
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

# import some classes to the namespace of this module
from tlslite.api import X509, X509CertChain, parsePEMKey, Session

# import tlslite.api to overwrite TLSConnection
import tlslite.api

# kaa imports
import kaa

class TLSConnection(tlslite.api.TLSConnection):
    """
    This class wraps a socket and provides TLS handshaking and data transfer.
    It enhances the tlslite version of the class with the same name with
    kaa.notifier support.
    """
    @kaa.coroutine()
    def handshakeClientCert(self, certChain=None, privateKey=None, session=None,
                            settings=None, checker=None):
        """
        Perform a certificate-based handshake in the role of client.
        """
        handshake = tlslite.api.TLSConnection.handshakeClientCert(
            self, certChain=certChain, privateKey=privateKey, session=session,
            settings=settings, checker=checker, async=True)
        try:
            while True:
                n = handshake.next()
                cb = kaa.YieldCallback()
                disp = kaa.notifier.SocketDispatcher(cb)
                if n == 0:
                    disp.register(self.sock.fileno(), kaa.notifier.IO_READ)
                if n == 1:
                    disp.register(self.sock.fileno(), kaa.notifier.IO_WRITE)
                yield cb
                disp.unregister()
        except StopIteration:
            pass
        yield True


    def fileno(self):
        """
        Return socket descriptor. This makes this class feel like a normal
        socket to the SocketDispatcher.
        """
        return self.sock.fileno()



class Socket(kaa.Socket):
    """
    Special version of kaa.Socket with TLS support.
    """
    def __init__(self):
        kaa.Socket.__init__(self)
        self.signals['tls'] = kaa.Signal()


    @kaa.coroutine()
    def starttls_client(self, session=None):
        """
        Start a certificate-based handshake in the role of a TLS client.
        Note: this function DOES NOT check the server key based on the
        key chain yet.
        """
        if session is None:
            session = Session()
        c = TLSConnection(self._socket)
        self._rmon.unregister()
        yield c.handshakeClientCert(session=session)
        self._socket = c
        self.signals['tls'].emit()
        self._rmon.register(self._socket.fileno(), kaa.IO_READ)
