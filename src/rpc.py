# -*- coding: iso-8859-1 -*-
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
# Copyright (C) 2006 Dirk Meyer, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# Please see the file AUTHORS for a complete list of authors.
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

__all__ = [ 'Server', 'Client', 'expose' ]

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
        client._request_auth_packet()
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
        for func in [ getattr(obj, func) for func in dir(obj) ]:
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
        self._send_packet(seq, packet_type, len(payload), payload)
        # create InProgress object and return
        callback = kaa.notifier.InProgress()
        # callback with error handler
        self._rpc_in_progress[seq] = callback
        return callback


    def _handle_close(self):
        """
        Socket is closed.
        """
        log.info('close socket for %s', self)
        self._socket.close()
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
        except:
            log.exception('_handle_read failed, close socket')
            data = None

        if not data:
            log.info('no data received')
            self._handle_close()
            # Return False to cause notifier to remove fd handler.
            return False

        header_size = struct.calcsize("I4sI")
        self._read_buffer.append(data)
        # Before we start into the loop, make sure we have enough data for
        # a full packet.  For very large packets (if we just received a huge
        # pickled object), this saves the string.join() which can be very
        # expensive.  (This is the reason we use a list for our read buffer.)
        buflen = reduce(lambda x, y: x + len(y), self._read_buffer, 0)
        if buflen < header_size:
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
            self._handle_packet(seq, packet_type, payload)


    def _send_packet(self, seq, packet_type, length, payload):
        """
        Send a packet (header + payload) to the other side.
        """
        header = struct.pack("I4sI", seq, packet_type, length)
        if not self._authenticated:
            if packet_type in ('RESP', 'AUTH'):
                self._write_buffer = header + payload + self._write_buffer
                if not self._wmon.active():
                    self._wmon.register(self._socket.fileno(),
                                        kaa.notifier.IO_WRITE)
                return True
            log.info('delay packet %s', packet_type)
            self._write_buffer += header + payload
            return True

        self._write_buffer += header + payload
        if not self._wmon.active():
            self._wmon.register(self._socket.fileno(), kaa.notifier.IO_WRITE)


    def _handle_write(self):
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
            self._handle_close()
            return False
        return True


    def _send_delayed_answer(self, payload, seq, packet_type):
        """
        Send delayed answer when callback returns InProgress.
        """
        payload = cPickle.dumps(payload, pickle.HIGHEST_PROTOCOL)
        self._send_packet(seq, packet_type, len(payload), payload)

        
    def _handle_packet(self, seq, type, payload):
        """
        Handle incoming packet (called from _handle_write).
        """
        if not self._authenticated:
            # Not authenticated, only AUTH and RESP are allowed.
            if type == 'AUTH':
                response, salt = self._get_challenge_response(payload)
                payload = struct.pack("20s20s20s", payload, response, salt)
                self._send_packet(seq, 'RESP', len(payload), payload)
                self._authenticated = True
                if not self._wmon.active() and self._write_buffer:
                    # send delayed stuff now
                    self._wmon.register(self._socket.fileno(), kaa.notifier.IO_WRITE)
                return True

            if type == 'RESP':
                challenge, response, salt = struct.unpack("20s20s20s", payload)
                if response == self._get_challenge_response(challenge, salt)[0] \
                   and challenge == self._pending_challenge:
                    self._authenticated = True
                    if not self._wmon.active() and self._write_buffer:
                        # send delayed stuff now
                        self._wmon.register(self._socket.fileno(), kaa.notifier.IO_WRITE)
                    return True
                log.error('authentication error')
                return True

            log.error('got %s before challenge response is complete', type)
            return True

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
            self._send_packet(seq, packet_type, len(payload), payload)
            return True

        if type == 'RETN':
            # RPC return
            payload = cPickle.loads(payload)
            callback = self._rpc_in_progress.get(seq)
            if not callback:
                return True
            del self._rpc_in_progress[seq]
            callback.finished(payload)
            return True

        if type == 'EXCP':
            # Exception for remote call
            error = cPickle.loads(payload)
            callback = self._rpc_in_progress.get(seq)
            if not callback:
                return True
            del self._rpc_in_progress[seq]
            callback.exception(error)
            return True

        log.error('unknown packet type %s', type)
        return True


    def _request_auth_packet(self):
        """
        Request an auth packet response for initial setup.
        """
        rbytes = file("/dev/urandom").read(64)
        self._pending_challenge = sha.sha(str(time.time()) + rbytes).digest()
        self._send_packet(0, 'AUTH', 20, self._pending_challenge)


    def _get_challenge_response(self, challenge, salt = None):
        """
        Generate a response for the challenge based on the auth secret
        supplied to the constructor.  This hashes twice to prevent against
        certain attacks on the hash function.  If salt is not None, it is
        the value generated by the remote end that was used in computing
        their response.  If it is None, a new 20-byte salt is generated
        and used in computing our response.
        """
        if salt == None:
            rbytes = file("/dev/urandom").read(64)
            salt = sha.sha(str(time.time()) + rbytes).digest()
        m = challenge + self._auth_secret + salt
        return sha.sha(sha.sha(m).digest() + m).digest(), salt


    def __repr__(self):
        return '<kaa.rpc.server.channel %s' % self._socket.fileno()


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
        fd.connect(address)
        fd.setblocking(False)
        Channel.__init__(self, fd, auth_secret)


    def __repr__(self):
        return '<kaa.rpc.client.channel %s' % self._socket.fileno()



def expose(command):
    """
    Decorator to expose a function.
    """
    def decorator(func):
        func._kaa_rpc = command
        return func
    return decorator
