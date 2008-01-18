# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# sockets.py - Socket (fd) classes for the notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2005-2007 Dirk Meyer, Jason Tackaberry, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#                Jason Tackaberry <tack@urandom.ca>
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

__all__ = [ 'SocketDispatcher', 'WeakSocketDispatcher', 'Socket',
            'IO_READ', 'IO_WRITE' ]

import socket
import logging

import nf_wrapper as notifier
from callback import Callback, Signal
from thread import MainThreadCallback, ThreadCallback, is_mainthread

# get logging object
log = logging.getLogger('notifier')

IO_READ   = 0
IO_WRITE  = 1

class SocketDispatcher(notifier.NotifierCallback):

    def __init__(self, callback, *args, **kwargs):
        super(SocketDispatcher, self).__init__(callback, *args, **kwargs)
        self.set_ignore_caller_args()


    def register(self, fd, condition = IO_READ):
        if self.active():
            return
        if not is_mainthread():
            return MainThreadCallback(self.register, fd, condition)()
        notifier.socket_add(fd, self, condition)
        self._condition = condition
        self._id = fd


    def unregister(self):
        if not self.active():
            return
        if not is_mainthread():
            return MainThreadCallback(self.unregister)()
        notifier.socket_remove(self._id, self._condition)
        super(SocketDispatcher, self).unregister()



class WeakSocketDispatcher(notifier.WeakNotifierCallback, SocketDispatcher):
    pass


class Socket(object):
    """
    Notifier-aware socket class.
    """
    def __init__(self, addr = None, async = None):
        self._addr = self._socket = None
        self._write_buffer = ""
        self._read_delim = None

        self.signals = {
            "closed": Signal(),
            "read": Signal(),
            "connected": Signal()
        }

        # These variables hold the socket dispatchers for monitoring; we
        # only allocate a dispatcher when the socket is connected to avoid
        # a ref cycle so that disconnected sockets will get properly deleted
        # when they are not referenced.
        self._rmon = self._wmon = None

        self._listening = False

        if addr:
            self.connect(addr, async = async)


    def _normalize_address(self, addr):
        if isinstance(addr, basestring) and ":" in addr:
            addr = addr.split(":")
            assert(len(addr) == 2)
            addr[1] = int(addr[1])
            addr = tuple(addr)

        return addr


    def _make_socket(self, addr = None):
        addr = self._normalize_address(addr)

        if self._socket:
            self.close()

        assert(type(addr) in (str, tuple, None))

        if isinstance(addr, basestring):
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self._addr = addr


    def listen(self, bind_info, qlen = 5):
        if isinstance(bind_info, int):
            # Change port to (None, port)
            bind_info = ("", bind_info)

        if not isinstance(bind_info, (tuple, list)) or \
               not isinstance(bind_info[0], (tuple, list)):
            bind_info = (bind_info, )


        self._make_socket(bind_info[0])

        for addr in bind_info:
            addr = self._normalize_address(addr)
            try:
                self._socket.bind(addr)
            except socket.error:
                log.error('Failed to bind socket to: %s' % str(addr))

        self._socket.listen(qlen)
        self._listening = True
        self.wrap()



    def connect(self, addr, async = False):
        """
        Connects to the host specified in addr.  If addr is a string in the
        form host:port, or a tuple the form (host, port), a TCP socket is
        established.  Otherwise a Unix socket is established and addr is
        treated as a filename.

        If async is not None, it is a callback that will be invoked when the
        connection has been established.  This callback takes one parameter,
        which is True if the connection was established successfully, or an
        Exception object otherwise.

        If async is None, this call will block until either connected or an
        exception is raised.  Although this call blocks, the notifier loop
        remains active.
        """
        self._make_socket(addr)


        in_progress = ThreadCallback(self._connect_thread)()
        result_holder = []
        if not async:
            cb = Callback(lambda res, x: x.append(res), result_holder)
        else:
            cb = self.signals["connected"].emit
        in_progress.connect_both(cb, cb)

        if async != None:
            return

        while len(result_holder) == 0:
            notifier.step()

        if isinstance(result_holder[0], (Exception, socket.error)):
            raise result_holder[0]


    def _connect_thread(self):
        if type(self._addr) == str:
            # Unix socket, just connect.
            self._socket.connect(self._addr)
        else:
            host, port = self._addr
            if not host.replace(".", "").isdigit():
                # Resolve the hostname.
                host = socket.gethostbyname(host)
            self._socket.connect((host, port))

        self.wrap()
        return True



    def wrap(self, sock = None, addr = None):
        if sock:
            self._socket = sock
        if addr:
            self._addr = addr

        self._socket.setblocking(False)

        if self._rmon:
            self._rmon.unregister()
            self._wmon.unregister()

        self._rmon = SocketDispatcher(self._handle_read)
        self._wmon = SocketDispatcher(self._handle_write)

        self._rmon.register(self._socket, IO_READ)
        if self._write_buffer:
            self._wmon.register(self._socket, IO_WRITE)


    def _handle_read(self):
        if self._listening:
            sock, addr = self._socket.accept()
            client_socket = Socket()
            client_socket.wrap(sock, addr)
            self.signals["connected"].emit(client_socket)
            return

        try:
            data = self._socket.recv(1024*1024)
        except socket.error, (errno, msg):
            if errno == 11:
                # Resource temporarily unavailable -- we are trying to read
                # data on a socket when none is available.
                return
            # If we're here, then the socket is likely disconnected.
            data = None

        if not data:
            return self.close(False)

        self.signals["read"].emit(data)


    def close(self, expected = True):
        self._rmon.unregister()
        self._wmon.unregister()
        self._rmon = self._wmon = None
        self._write_buffer = ""

        self._socket.close()
        self._socket = None
        self.signals["closed"].emit(expected)


    def write(self, data):
        self._write_buffer += data
        if self._socket and not self._wmon.active():
            self._wmon.register(self._socket, IO_WRITE)

    def _handle_write(self):
        if len(self._write_buffer) == 0:
            return

        try:
            sent = self._socket.send(self._write_buffer)
            self._write_buffer = self._write_buffer[sent:]
            if not self._write_buffer:
                self._wmon.unregister()
        except socket.error, (errno, msg):
            if errno == 11:
                # Resource temporarily unavailable -- we are trying to write
                # data to a socket when none is available.
                return
            # If we're here, then the socket is likely disconnected.
            self.close(False)


    def is_connected(self):
        return self._socket != None
