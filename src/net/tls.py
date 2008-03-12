# -* -coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# tls.py - TLS support for kaa.notifier based on tlslite
# -----------------------------------------------------------------------------
# $Id$
#
# This module wraps TLS for client and server based on tlslite. See
# http://trevp.net/tlslite/docs/public/tlslite.TLSConnection.TLSConnection-class.html
# for more information about optional paramater.
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

# python imports
import sys
import logging

# import tlslite API to the namespace of this module
from tlslite.api import *

# import tlslite.api to overwrite TLSConnection
import tlslite.api

# kaa imports
import kaa

# get logging object
log = logging.getLogger('tls')


class TLSConnection(tlslite.api.TLSConnection):
    """
    This class wraps a socket and provides TLS handshaking and data transfer.
    It enhances the tlslite version of the class with the same name with
    kaa.notifier support.
    """
    @kaa.coroutine()
    def _iterate_handshake(self, handshake):
        """
        Iterate through the TLS handshake for asynchronous calls using
        kaa.notifier IOMonitor and InProgressCallback.
        """
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

    def handshakeClientCert(self, certChain=None, privateKey=None, session=None,
                            settings=None, checker=None):
        """
        Perform a certificate-based handshake in the role of client.
        """
        handshake = tlslite.api.TLSConnection.handshakeClientCert(
            self, certChain=certChain, privateKey=privateKey, session=session,
            settings=settings, checker=checker, async=True)
        return self._iterate_handshake(handshake)

    def handshakeServer(self, sharedKeyDB=None, verifierDB=None, certChain=None,
                        privateKey=None, reqCert=None, sessionCache=None,
                        settings=None, checker=None):
        """
        Start a server handshake operation on the TLS connection.
        """
        handshake = tlslite.api.TLSConnection.handshakeServerAsync(
            self, sharedKeyDB, verifierDB, certChain, privateKey, reqCert,
            sessionCache, settings, checker)
        return self._iterate_handshake(handshake)

    def fileno(self):
        """
        Return socket descriptor. This makes this class feel like a normal
        socket to the IOMonitor.
        """
        return self.sock.fileno()



class TLSSocket(kaa.Socket):
    """
    Special version of kaa.Socket with TLS support. On creation the
    connection is NOT encrypted, starttls_client and starttls_server
    must be called to encrypt the connection.
    """
    def __init__(self):
        kaa.Socket.__init__(self)
        self.signals['tls'] = kaa.Signal()
        self._handshake = False

    def _accept(self):
        """
        Accept a new connection and return a new Socket object.
        """
        sock, addr = self._socket.accept()
        client_socket = TLSSocket()
        client_socket.wrap(sock, addr)
        self.signals['new-client'].emit(client_socket)

    def _update_read_monitor(self, signal = None, change = None):
        # FIXME: This function is broken in TLSSocket for two reasons:
        # 1. auto-reconnect while doing a tls handshake is wrong
        #    This could be fixed using self._handshake
        # 2. Passing self._socket to register does not work,
        #    self._socket.fileno() is needed. Always using fileno()
        #    does not work for some strange reason.
        return

    def wrap(self, sock, addr = None):
        """
        Wraps an existing low-level socket object.  addr specifies the address
        corresponding to the socket.
        """
        super(TLSSocket, self).wrap(sock, addr)
        # since _update_read_monitor is deactivated we need to always register
        # the rmon to the notifier.
        if not self._rmon.active():
            self._rmon.register(self._socket.fileno(), kaa.IO_READ)

    def write(self, data):
        """
        Write data to the socket. The data will be delayed while the socket
        is doing the TLS handshake.
        """
        if self._handshake:
            # do not send data while doing a handshake
            return self._write_buffer.append(data)
        return super(TLSSocket, self).write(data)

    def _handle_read(self):
        """
        Callback for new data on the socket.
        """
        try:
            return super(TLSSocket, self)._handle_read()
        except TLSAbruptCloseError, e:
            log.error('TLSAbruptCloseError')
            self._read_signal.emit(None)
            self._readline_signal.emit(None)
            return self.close(immediate=True, expected=False)

    @kaa.coroutine()
    def starttls_client(self, session=None, key=None, **kwargs):
        """
        Start a certificate-based handshake in the role of a TLS client.
        Note: this function DOES NOT check the server key based on the
        key chain. Provide a checker callback to be called for verification.
        http://trevp.net/tlslite/docs/public/tlslite.Checker.Checker-class.html
        Every callable object can be used as checker.
        """
        try:
            if key:
                kwargs['privateKey'] = key.key
                kwargs['certChain'] = key.chain
            self._handshake = True
            if session is None:
                session = Session()
            c = TLSConnection(self._socket)
            self._rmon.unregister()
            yield c.handshakeClientCert(session=session, **kwargs)
            self._socket = c
            self.signals['tls'].emit()
            self._rmon.register(self._socket.fileno(), kaa.IO_READ)
            self._handshake = False
        except:
            self._handshake = False
            type, value, tb = sys.exc_info()
            raise type, value, tb

    @kaa.coroutine()
    def starttls_server(self, key, **kwargs):
        """
        Start a certificate-based handshake in the role of a TLS server.
        Note: this function DOES NOT check the client key if requested,
        provide a checker callback to be called for verification.
        http://trevp.net/tlslite/docs/public/tlslite.Checker.Checker-class.html
        Every callable object can be used as checker.
        """
        try:
            self._handshake = True
            c = TLSConnection(self._socket)
            self._rmon.unregister()
            yield c.handshakeServer(privateKey=key.key, certChain=key.chain, **kwargs)
            self._socket = c
            self.signals['tls'].emit()
            self._rmon.register(self._socket.fileno(), kaa.IO_READ)
            self._handshake = False
        except:
            self._handshake = False
            type, value, tb = sys.exc_info()
            raise type, value, tb


class TLSKey(object):
    """
    Class to hold the public (and private) key together with the certification chain.
    This class can be used with TLSSocket as key.
    """
    def __init__(self, filename, private, *certs):
        self.key = parsePEMKey(open(filename).read(), private=private)
        chain = []
        for cert in (filename, ) + certs:
            x509 = X509()
            x509.parse(open(cert).read())
            chain.append(x509)
        self.chain = X509CertChain(chain)
