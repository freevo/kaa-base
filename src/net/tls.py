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
    def _iterate_handshake(self, handshake):
        try:
            while True:
                n = handshake.next()
                cb = kaa.InProgressCallback()
                disp = kaa.notifier.IOMonitor(cb)
                if n == 0:
                    disp.register(self.sock.fileno(), kaa.notifier.IO_READ)
                if n == 1:
                    disp.register(self.sock.fileno(), kaa.notifier.IO_WRITE)
                yield cb
                disp.unregister()
        except StopIteration:
            pass

    @kaa.coroutine()
    def handshakeClientCert(self, certChain=None, privateKey=None, session=None,
                            settings=None, checker=None):
        """
        Perform a certificate-based handshake in the role of client.
        """
        handshake = tlslite.api.TLSConnection.handshakeClientCert(
            self, certChain=certChain, privateKey=privateKey, session=session,
            settings=settings, checker=checker, async=True)
        yield self._iterate_handshake(handshake)

    @kaa.coroutine()
    def handshakeServer(self, sharedKeyDB=None, verifierDB=None, certChain=None,
                        privateKey=None, reqCert=None, sessionCache=None,
                        settings=None, checker=None):
        """
        Start a server handshake operation on the TLS connection.
        """
        handshake = tlslite.api.TLSConnection.handshakeServerAsync(
            self, sharedKeyDB, verifierDB, certChain, privateKey, reqCert,
            sessionCache, settings, checker)
        yield self._iterate_handshake(handshake)

    def fileno(self):
        """
        Return socket descriptor. This makes this class feel like a normal
        socket to the IOMonitor.
        """
        return self.sock.fileno()



class TlsSocket(kaa.Socket):
    """
    Special version of kaa.Socket with TLS support.
    """
    def __init__(self):
        kaa.Socket.__init__(self)
        self.signals['tls'] = kaa.Signal()


    def _accept(self):
        """
        Accept a new connection and return a new Socket object.
        """
        sock, addr = self._socket.accept()
        client_socket = TlsSocket()
        client_socket.wrap(sock, addr)
        self.signals['new-client'].emit(client_socket)

    def _update_read_monitor(self, signal = None, change = None):
        # This function is broken in TlsSocket for two reasons:
        # 1. auto-reconnect while doing a tls handshake is wrong
        # 2. Passing self._socket to register does not work,
        #    self._socket.fileno() is needed. Always using fileno()
        #    does not work for some strange reason.
        pass

    def wrap(self, sock, addr = None):
        """
        Wraps an existing low-level socket object.  addr specifies the address
        corresponding to the socket.
        """
        super(TlsSocket, self).wrap(sock, addr)
        # since _update_read_monitor is deactivated we need to always register
        # the rmon to the notifier.
        if not self._rmon.active():
            self._rmon.register(self._socket.fileno(), kaa.IO_READ)

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


    @kaa.coroutine()
    def starttls_server(self, key, cert_chain, client_cert=None):
        """
        Start a certificate-based handshake in the role of a TLS server.
        Note: this function DOES NOT check the client key if requested.
        """
        c = TLSConnection(self._socket)
        self._rmon.unregister()
 	yield c.handshakeServer(
            privateKey=key, certChain=cert_chain, reqCert=client_cert)
        self._socket = c
        self.signals['tls'].emit()
        self._rmon.register(self._socket.fileno(), kaa.IO_READ)


def loadkey(filename, private=False):
    """
    Load a key in PEM format from file.
    """
    return parsePEMKey(open(filename).read(), private=private)


def loadcert(filename):
    """
    Load a X509 certificate and create a chain.
    """
    x509 = X509()
    x509.parse(open(filename).read())
    return X509CertChain([x509])
