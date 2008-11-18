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

# import tlslite.api to overwrite TLSConnection
import tlslite.api
import tlslite.errors

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

    def handshakeClientSRP(self, username, password, session=None,
                           settings=None, checker=None):
        """
        Perform a SRP-based handshake in the role of client.
        """
        handshake = tlslite.api.TLSConnection.handshakeClientSRP(
            self, username=username, password=password, session=session,
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


    def close(self):
        """
        Close the socket.
        """
        if not self.closed:
            # force socket close or this will block
            # on kaa shutdown.
            self.sock.close()
        return tlslite.api.TLSConnection.close(self)


class TLSSocket(kaa.Socket):
    """
    Special version of kaa.Socket with TLS support. On creation the
    connection is NOT encrypted, starttls_client and starttls_server
    must be called to encrypt the connection.
    """

    # list of suuported TLS authentication mechanisms
    supported_methods = [ 'X.509', 'SRP' ]

    def __init__(self):
        kaa.Socket.__init__(self)
        self.signals += ('tls',)
        self._handshake = False

    def _is_read_connected(self):
        """
        Returns True if we're interested in read events.
        """
        # During the handshake stage, we handle all reads internally.  So
        # if self._handshake is True, we are always interested in read
        # events.  If it's False, we defer to the default behaviour.
        #
        # We can't simply always return True, because then read() and
        # readline() may not work correctly (due to a race condition
        # described in IOChannel._handle_read)
        return not self._handshake and super(TLSSocket, self)._is_read_connected()

    def _handle_write(self):
        if self._handshake:
            # During the handshake stage, we don't want to write user data
            # to the socket.  It's still queued; we return immediately
            # and retry later.
            return
        return super(TLSSocket, self)._handle_write()

    @kaa.coroutine()
    def starttls_client(self, session=None, key=None, srp=None, checker=None):
        """
        Start a certificate-based handshake in the role of a TLS client.
        Note: this function DOES NOT check the server key based on the
        key chain. Provide a checker callback to be called for verification.
        http://trevp.net/tlslite/docs/public/tlslite.Checker.Checker-class.html
        Every callable object can be used as checker.

        @param session: tlslite.Session object to resume
        @param key: TLSKey object for client authentication
        @param srp: username, password pair for SRP authentication
        @param checker: callback to check the credentials from the server
        """
        if not self._rmon:
            raise RuntimeError('Socket not connected')
        try:
            self._handshake = True
            if session is None:
                session = tlslite.api.Session()
            c = TLSConnection(self._channel)
            c.ignoreAbruptClose = True
            self._rmon.unregister()
            if key:
                yield c.handshakeClientCert(session=session, checker=checker,
                          privateKey=key.private, certChain=key.certificate.chain)
            elif srp:
                yield c.handshakeClientSRP(session=session, checker=checker,
                          username=srp[0], password=srp[1])
                pass
            else:
                yield c.handshakeClientCert(session=session, checker=checker)
            self._channel  = c
            self.signals['tls'].emit()
            self._update_read_monitor()
        finally:
            self._handshake = False


    @kaa.coroutine()
    def starttls_server(self, session=None, key=None, request_cert=False, srp=None, checker=None):
        """
        Start a certificate-based or SRP-based handshake in the role of a TLS server.
        Note: this function DOES NOT check the client key if requested,
        provide a checker callback to be called for verification.
        http://trevp.net/tlslite/docs/public/tlslite.Checker.Checker-class.html
        Every callable object can be used as checker.

        @param session: tlslite.Session object to resume
        @param key: TLSKey object for server authentication
        @param request_cert: Request client certificate
        @param srp: tlslite.VerifierDB for SRP authentication
        @param checker: callback to check the credentials from the server
        """
        try:
            self._handshake = True
            c = TLSConnection(self._channel)
            c.ignoreAbruptClose = True
            self._rmon.unregister()
            kwargs = {}
            if key:
                kwargs['privateKey'] = key.private
                kwargs['certChain'] = key.certificate.chain
            if srp:
                kwargs['verifierDB'] = srp
            if request_cert:
                kwargs['reqCert'] = True
            yield c.handshakeServer(checker=checker, **kwargs)
            self._channel  = c
            self.signals['tls'].emit()
            self._update_read_monitor()
        finally:
            self._handshake = False


class TLSKey(object):
    """
    Class to hold the public (and private) key together with the certification chain.
    This class can be used with TLSSocket as key.
    """
    def __init__(self, filename, private, *certs):
        self.private = tlslite.api.parsePEMKey(open(filename).read(), private=private)
        self.certificate = tlslite.api.X509()
        self.certificate.parse(open(filename).read())
        chain = []
        for cert in (filename, ) + certs:
            x509 = tlslite.api.X509()
            x509.parse(open(cert).read())
            chain.append(x509)
        self.certificate.chain = tlslite.api.X509CertChain(chain)

#: Error to raise in the checker
TLSAuthenticationError = tlslite.errors.TLSAuthenticationError
