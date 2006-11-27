# -* -coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# rpc.py - Simple RPC InterProcessCommunication
# -----------------------------------------------------------------------------
# $Id$
#
# This module defines an alternative way for InterProcessCommunication with
# less features than the ipc.py module. It does not keep references, return
# values are only given back as a callback and it is only possible to access
# functions.
#
# So wy use this module and not kaa.ipc? Well, kaa.ipc makes it very easy to
# shoot yourself into the foot. It keeps references over ipc which could
# confuse the garbage collector and a simple function call on an object can
# result in many notifier steps incl. recursion inside the notifier.
#
#
# Documentation:
#
# Start a server: kaa.rpc.Server(address, secret)
# Start a client: kaa.rpc.Client(address, secret)
#
# Since everything is async, the challenge response is done in the background
# and you can start using it right away. If the authentication is wrong, it
# will fail without notifing the user (I know this is bad, but it is designed
# to work internaly where everything is correct).
#
# Next you need to define functions the remote side is allowed to call and
# give it a name. Use use expose for that.
#
# | class MyClass(object)
# |   @kaa.rpc.expose("do_something")
# |   def my_function(self, foo)
#
# Connect the object with that function to the server/client. You can connect
# as many objects as you want
# | server.connect(MyClass())
#
# The client can now call do_something (not my_function, this is the internal
# name). To do that, you need to create a RPC object with the callback you
# want to have
#
# | x = client.rpc('do_something', 6) or
# | x = client.rpc('do_something', foo=4)
#
# The result is an InProgress object. Connect to it to get the result.
#
# When a new client connects to the server, the 'client_connected' signals will
# be emitted with a Channel object as parameter. This object can be used to
# call functions on client side the same way the client calls functions on
# server side. The client and the channel objects have a signal 'disconnected'
# to be called when the connection gets lost.
#
# -----------------------------------------------------------------------------
# Copyright (C) 2006 Dirk Meyer, Jason Tackaberry
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

__all__ = [ 'Server', 'Client', 'expose', 'ConnectError' ]

# python imports
import types
import socket
import errno
import logging
import os
import cPickle
import pickle
import struct
import sys
import sha
import time

# kaa imports
import kaa
import kaa.notifier

# get logging object
log = logging.getLogger('rpc')

class ConnectError(Exception):
    pass

class Server(object):
    """
    RPC server class.
    """
    def __init__(self, address, auth_secret = ''):

        self._auth_secret = auth_secret
        if type(address) in types.StringTypes:
            if address.find('/') == -1:
                # create socket in kaa temp dir
                address = '%s/%s' % (kaa.TEMP, address)

            if os.path.exists(address):
                # maybe a server is already running at this address, test it
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(address)
                except socket.error, (err, msg):
                    if err == errno.ECONNREFUSED:
                        # not running, everything is fine
                        log.info('remove socket from dead server')
                    else:
                        # some error we do not expect
                        raise socket.error(err, msg)
                else:
                    # server already running
                    raise IOError('server already running')
                os.unlink(address)
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        elif type(address) == tuple:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.socket.setblocking(False)
        self.socket.bind(address)
        self.socket.listen(5)
        self._mon = kaa.notifier.WeakSocketDispatcher(self._new_connection)
        self._mon.register(self.socket.fileno())
        # Remove socket file and close clients on shutdown
        kaa.signals["shutdown"].connect_weak(self.close)

        self.signals = {
            "client_connected": kaa.notifier.Signal(),
        }
        self.objects = []


    def _new_connection(self):
        """
        Callback when a new client connects.
        """
        client_sock = self.socket.accept()[0]
        client_sock.setblocking(False)
        log.info("New connection %s", client_sock)
        client = Channel(socket = client_sock, auth_secret = self._auth_secret)
        for obj in self.objects:
            client.connect(obj)
        client._send_auth_challenge()
        self.signals["client_connected"].emit(client)


    def close(self):
        """
        Close the server socket.
        """
        self.socket = None
        self._mon.unregister()
        kaa.signals["shutdown"].disconnect(self.close)


    def connect(self, obj):
        """
        Connect an object to be exposed to the rpc.
        """
        self.objects.append(obj)



class Channel(object):
    """
    Channel object for two point communication. The server creates a Channel
    object for each client connection, Client itslef is a Channel.
    """
    def __init__(self, socket, auth_secret):
        self._socket = socket

        self._rmon = kaa.notifier.SocketDispatcher(self._handle_read)
        self._rmon.register(self._socket.fileno(), kaa.notifier.IO_READ)
        self._wmon = kaa.notifier.SocketDispatcher(self._handle_write)
        self._authenticated = False
        self._write_buffer = ''
        self._write_buffer_delayed = ''
        self._read_buffer = []
        self._callbacks = {}
        self._next_seq = 1
        self._rpc_in_progress = {}
        self._auth_secret = auth_secret
        self._pending_challenge = None

        self.signals = { 'closed': kaa.notifier.Signal() }
        kaa.signals["shutdown"].connect_weak(self._handle_close)


    def connect(self, obj):
        """
        Connect an object to be exposed to the rpc.
        """
        if type(obj) == types.FunctionType:
            callables = [obj]
        else:
            callables = [ getattr(obj, func) for func in dir(obj) ]

        for func in callables:
            if callable(func) and hasattr(func, '_kaa_rpc'):
                self._callbacks[func._kaa_rpc] = func


    def rpc(self, cmd, *args, **kwargs):
        """
        Call the remote command and return InProgress.
        """
        if not self._wmon:
            raise IOError('channel is disconnected')
        seq = self._next_seq
        self._next_seq += 1
        packet_type = 'CALL'
        payload = cPickle.dumps((cmd, args, kwargs), pickle.HIGHEST_PROTOCOL)
        self._send_packet(seq, packet_type, payload)
        # create InProgress object and return
        callback = kaa.notifier.InProgress()
        # callback with error handler
        self._rpc_in_progress[seq] = callback
        return callback


    def _handle_close(self):
        """
        Socket is closed.
        """
        if not self._wmon:
            # already closed (no idea why this happens)
            return False
        log.info('close socket for %s', self)
        self._socket.close()
        self._socket = None
        if self._wmon.active():
            self._wmon.unregister()
        if self._rmon.active():
            self._rmon.unregister()
        self._wmon = self._rmon = None
        self.signals['closed'].emit()
        self.signals = {}
        kaa.signals["shutdown"].disconnect(self._handle_close)


    def _handle_read(self):
        """
        Read from the socket (callback from notifier).
        """
        try:
            data = self._socket.recv(1024*1024)
        except socket.error, (err, msg):
            if err == errno.EAGAIN:
                # Resource temporarily unavailable -- we are trying to read
                # data on a socket when none is available.
                return
            # If we're here, then the socket is likely disconnected.
            data = None
        except (KeyboardInterrupt, SystemExit):
            raise SystemExit
        except:
            log.exception('_handle_read failed, close socket')
            data = None

        if not data:
            log.info('no data received')
            self._handle_close()
            # Return False to cause notifier to remove fd handler.
            return False

        self._read_buffer.append(data)
        # read as much data as we have
        while True:
            try:
                data = self._socket.recv(1024*1024)
            except socket.error, (err, msg):
                break
            if not data:
                break
            self._read_buffer.append(data)

        header_size = struct.calcsize("I4sI")
        # Before we start into the loop, make sure we have enough data for
        # a full packet.  For very large packets (if we just received a huge
        # pickled object), this saves the string.join() which can be very
        # expensive.  (This is the reason we use a list for our read buffer.)
        buflen = reduce(lambda x, y: x + len(y), self._read_buffer, 0)
        if buflen < header_size:
            return

        if buflen > 512 and not self._authenticated:
            # 512 bytes is plenty for authentication handshake.  Any more than
            # that and something isn't right.
            log.warning("Too much data received from remote end before authentication; disconnecting")
            self._handle_close()
            return

        # Ensure the first block in the read buffer is big enough for a full
        # packet header.  If it isn't, then we must have more than 1 block in
        # the buffer, so keep merging blocks until we have a block big enough
        # to be a header.  If we're here, it means that buflen >= header_size,
        # so we can safely loop.
        while len(self._read_buffer[0]) < header_size:
            self._read_buffer[0] += self._read_buffer.pop(1)

        # Make sure the the buffer holds enough data as indicated by the
        # payload size in the header.
        header = self._read_buffer[0][:header_size]
        payload_len = struct.unpack("I4sI", header)[2]
        if buflen < payload_len + header_size:
            return

        # At this point we know we have enough data in the buffer for the
        # packet, so we merge the array into a single buffer.
        strbuf = ''.join(self._read_buffer)
        self._read_buffer = []
        while 1:
            if len(strbuf) <= header_size:
                if len(strbuf) > 0:
                    self._read_buffer.append(str(strbuf))
                break
            header = strbuf[:header_size]
            seq, packet_type, payload_len = struct.unpack("I4sI", header)
            if len(strbuf) < payload_len + header_size:
                # We've also received portion of another packet that we
                # haven't fully received yet.  Put back to the buffer what
                # we have so far, and we can exit the loop.
                self._read_buffer.append(str(strbuf))
                break

            # Grab the payload for this packet, and shuffle strbuf to the
            # next packet.
            payload = strbuf[header_size:header_size + payload_len]
            strbuf = buffer(strbuf, header_size + payload_len)
            #log.debug("Got packet %s", packet_type)
            if not self._authenticated:
                self._handle_packet_before_auth(seq, packet_type, payload)
            else:
                self._handle_packet_after_auth(seq, packet_type, payload)


    def _send_packet(self, seq, packet_type, payload):
        """
        Send a packet (header + payload) to the other side.
        """
        if not self._socket:
            return
        header = struct.pack("I4sI", seq, packet_type, len(payload))
        if not self._authenticated and packet_type not in ('RESP', 'AUTH'):
            log.info('delay packet %s', packet_type)
            self._write_buffer_delayed += header + payload
        else:
            self._write_buffer += header + payload

        self._handle_write(close_on_error=False)
        self._flush()


    def _flush(self):
        """
        If there is data pending in the write buffer, ensure that it is
        written next notifier loop.
        """
        if not self._wmon.active() and self._write_buffer:
            self._wmon.register(self._socket.fileno(), kaa.notifier.IO_WRITE)


    def _handle_write(self, close_on_error=True):
        """
        Write to the socket (callback from notifier).
        """
        if not len(self._write_buffer):
            return False
        try:
            sent = self._socket.send(self._write_buffer)
            self._write_buffer = self._write_buffer[sent:]
            if not self._write_buffer:
                return False
        except socket.error, (err, msg):
            if err == errno.EAGAIN:
                # Resource temporarily unavailable -- we are trying to write
                # data to a socket when none is available.
                return
            # If we're here, then the socket is likely disconnected.
            if close_on_error:
                self._handle_close()
            return False
        return True


    def _send_delayed_answer(self, payload, seq, packet_type):
        """
        Send delayed answer when callback returns InProgress.
        """
        payload = cPickle.dumps(payload, pickle.HIGHEST_PROTOCOL)
        self._send_packet(seq, packet_type, payload)


    def _handle_packet_after_auth(self, seq, type, payload):
        """
        Handle incoming packet (called from _handle_write) after 
        authentication has been completed.
        """
        if type == 'CALL':
            # Remote function call, send answer
            payload = cPickle.loads(payload)
            function, args, kwargs = payload
            try:
                payload = self._callbacks[function](*args, **kwargs)
                if isinstance(payload, kaa.notifier.InProgress):
                    payload.connect(self._send_delayed_answer, seq, 'RETN')
                    payload.exception_handler.connect(self._send_delayed_answer, seq, 'EXCP')
                    return True
                packet_type = 'RETN'
            except (SystemExit, KeyboardInterrupt):
                sys.exit(0)
            except Exception, e:
                log.exception('rpc call %s', function)
                if not function in self._callbacks:
                    log.error(self._callbacks.keys())
                packet_type = 'EXCP'
                payload = e
            payload = cPickle.dumps(payload, pickle.HIGHEST_PROTOCOL)
            self._send_packet(seq, packet_type, payload)
            return True

        if type == 'RETN':
            # RPC return
            payload = cPickle.loads(payload)
            callback = self._rpc_in_progress.get(seq)
            if callback is None:
                return True
            del self._rpc_in_progress[seq]
            callback.finished(payload)
            return True

        if type == 'EXCP':
            # Exception for remote call
            error = cPickle.loads(payload)
            callback = self._rpc_in_progress.get(seq)
            if callback is None:
                return True
            del self._rpc_in_progress[seq]
            callback.exception(error)
            return True

        log.error('unknown packet type %s', type)
        return True


    def _handle_packet_before_auth(self, seq, type, payload):
        """
        This function handles any packet received by the remote end while we
        are waiting for authentication.  It responds to AUTH or RESP packets
        (auth packets) while closing the connection on all other packets (non-
        auth packets).

        Design goals of authentication:
           * prevent unauthenticated connections from executing RPC commands
             other than 'auth' commands.
           * prevent unauthenticated connections from causing denial-of-
             service at or above the RPC layer.
           * prevent third parties from learning the shared secret by
             eavesdropping the channel.

        Non-goals:
           * provide any level of security whatsoever subsequent to successful
             authentication.
           * detect in-transit tampering of authentication by third parties
             (and thus preventing successful authentication).

        The parameters 'seq' and 'type' are untainted and safe.  The parameter
        payload is potentially dangerous and this function must handle any
        possible malformed payload gracefully.

        Authentication is a 4 step process and once it has succeeded, both
        sides should be assured that they share the same authentication secret.
        It uses a challenge-response scheme similar to CRAM.  The party
        responding to a challenge will hash the response with a locally
        generated salt to prevent a Chosen Plaintext Attack.  (Although CPA is
        not very practical, as they require the client to connect to a rogue
        server.) The server initiates authentication.

           1. Server sends challenge to client (AUTH packet)
           2. Client receives challenge, computes response, generates a
              counter-challenge and sends both to the server in reply (RESP
              packet with non-null challenge).
           3. Server receives response to its challenge in step 1 and the
              counter-challenge from server in step 2.  Server validates
              client's response.  If it fails, server logs the error and
              disconnects.  If it succeeds, server sends response to client's
              counter-challenge (RESP packet with null challenge).  At this
              point server considers client authenticated and allows it to send
              non-auth packets.
           4. Client receives server's response and validates it.  If it fails,
              it disconnects immediately.  If it succeeds, it allows the server
              to send non-auth packets.

        Step 1 happens when a new connection is initiated.  Steps 2-4 happen in
        this function.  3 packets are sent in this handshake (steps 1-3).

        WARNING: once authentication succeeds, there is implicit full trust.
        There is no security after that point, and it should be assumed that
        the client can invoke arbitrary calls on the server, and vice versa,
        because no effort is made to validate the data on the channel.

        Also, individual packets aren't authenticated.  Once each side has
        sucessfully authenticated, this scheme cannot protect against
        hijacking or denial-of-service attacks.

        One goal is to restrict the code path taken packets sent by
        unauthenticated connections.  That path is:

           _handle_read() -> _handle_packet_before_auth()

        Therefore these functions must be able to handle malformed and/or
        potentially malicious data on the channel, and as a result they are
        highly paranoid.  When these methods calls other functions, it must do
        so only with untainted data.  Obviously one assumption is that the
        underlying python calls made in these methods (particularly
        struct.unpack) aren't susceptible to attack.
        """
        if type not in ('AUTH', 'RESP'):
            # Received a non-auth command while expecting auth.
            log.error('got %s before authentication is complete; closing socket.' % type)
            # Hang up.
            self._handle_close()
            return

        try:
            # Payload could safely be longer than 20+20+20 bytes, but if it
            # is, something isn't quite right.  We'll be paranoid and
            # disconnect unless it's exactly 60 bytes.
            assert(len(payload) == 60)

            # Unpack the auth packet payload into three separate 20 byte
            # strings: the challenge, response, and salt.  If challenge is
            # not NULL (i.e. '\x00' * 20) then the remote is expecting a
            # a response.  If response is not NULL then salt must also not
            # be NULL, and the salt is used along with the previously sent
            # challenge to validate the response.
            challenge, response, salt = struct.unpack("20s20s20s", payload)
        except:
            log.warning("Malformed authentication packet from remote; disconnecting.")
            self._handle_close()
            return

        # At this point, challenge, response, and salt are 20 byte strings of
        # arbitrary binary data.  They're considered benign.

        if type == 'AUTH':
            # Step 2: We've received a challenge.  If we've already sent a
            # challenge (which is the case if _pending_challenge is not None),
            # then something isn't right.  This could be a DoS so we'll
            # disconnect immediately.
            if self._pending_challenge:
                self._pending_challenge = None
                self._handle_close()
                return

            # Otherwise send the response, plus a challenge of our own.
            response, salt = self._get_challenge_response(challenge)
            self._pending_challenge = self._get_rand_value()
            payload = struct.pack("20s20s20s", self._pending_challenge, response, salt)
            self._send_packet(seq, 'RESP', payload)
            log.info('Got initial challenge from server, sending response.')
            return

        elif type == 'RESP':
            # We've received a reply to an auth request.

            if self._pending_challenge == None:
                # We've received a response packet to auth, but we haven't
                # sent a challenge.  Something isn't right, so disconnect.
                self._handle_close()
                return

            # Step 3/4: We are expecting a response to our previous challenge
            # (either the challenge from step 1, or the counter-challenge from
            # step 2).  First compute the response we expect to have received
            # based on the challenge sent earlier, our shared secret, and the
            # salt that was generated by the remote end.

            expected_response = self._get_challenge_response(self._pending_challenge, salt)[0]
            # We have our response, so clear the pending challenge.
            self._pending_challenge = None
            # Now check to see if we were sent what we expected.
            if response != expected_response:
                log.error('authentication error')
                self._handle_close()
                return

            # Challenge response was good, so the remote is considered
            # authenticated now.
            self._authenticated = True
            log.info('Valid response received, remote authenticated.')

            # If remote has issued a counter-challenge along with their
            # response (step 2), we'll respond.  Unless something fishy is
            # going on, this should always succeed on the remote end, because
            # at this point our auth secrets must match.  A challenge is
            # considered issued if it is not NULL ('\x00' * 20).  If no
            # counter-challenge was received as expected from step 2, then
            # authentication is only one-sided (we trust the remote, but the
            # remote won't trust us).  In this case, things won't work
            # properly, but there are no negative security implications.
            if len(challenge.strip("\x00")) != 0:
                response, salt = self._get_challenge_response(challenge)
                payload = struct.pack("20s20s20s", '', response, salt)
                self._send_packet(seq, 'RESP', payload)
                log.info('Sent response to challenge from client.')

            self._write_buffer += self._write_buffer_delayed
            self._write_buffer_delayed = ''
            self._flush()


    def _get_rand_value(self):
        """
        Returns a 20 byte value which is computed as a SHA hash of the
        current time concatenated with 64 bytes from /dev/urandom.  This
        value is not by design a nonce, but in practice it probably is.
        """
        rbytes = file("/dev/urandom").read(64)
        return sha.sha(str(time.time()) + rbytes).digest()


    def _send_auth_challenge(self):
        """
        Send challenge to remote end to initiate authentication handshake.
        """
        self._pending_challenge = self._get_rand_value()
        payload = struct.pack("20s20s20s", self._pending_challenge, '', '')
        self._send_packet(0, 'AUTH', payload)


    def _get_challenge_response(self, challenge, salt = None):
        """
        Generate a response for the challenge based on the auth secret supplied
        to the constructor.  This essentially implements CRAM, as defined in
        RFC 2195, using SHA-1 as the hash function, however the challenge is
        concatenated with a locally generated 20 byte salt.
        
        If salt is not None, it is the value generated by the remote end that
        was used in computing their response.  If it is None, a new 20-byte
        salt is generated and used in computing our response.
        """
        def xor(s, byte):
            # XORs each character in string s with byte.
            return ''.join([ chr(ord(x) ^ byte) for x in s ])

        def H(s):
            # Returns the 20 byte SHA-1 digest of string s.
            return sha.sha(s).digest()

        if not salt:
            salt = self._get_rand_value()

        K = self._auth_secret + salt
        return H(xor(K, 0x5c) + H(xor(K, 0x36) + challenge)), salt


    def __repr__(self):
        if not self._socket:
            return '<kaa.rpc.Channel (server) - disconnected>'
        return '<kaa.rpc.Channel (server) %s>' % self._socket.fileno()


class Client(Channel):
    """
    RPC client to be connected to a server.
    """
    def __init__(self, address, auth_secret = ''):
        if type(address) in types.StringTypes:
            address = '%s/%s' % (kaa.TEMP, address)
            fd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if type(address) == tuple:
            fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            fd.connect(address)
        except socket.error, e:
            raise ConnectError(e)
        fd.setblocking(False)
        Channel.__init__(self, fd, auth_secret)


    def __repr__(self):
        if not self._socket:
            return '<kaa.rpc.Channel (client) - disconnected>'
        return '<kaa.rpc.Channel (client) %s>' % self._socket.fileno()



def expose(command):
    """
    Decorator to expose a function.
    """
    def decorator(func):
        func._kaa_rpc = command
        return func
    return decorator
