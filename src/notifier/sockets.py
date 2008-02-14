# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# sockets.py - Socket (fd) classes for the notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2005-2008 Dirk Meyer, Jason Tackaberry, et al.
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

__all__ = [ 'IOMonitor', 'WeakIOMonitor', 'Socket', 'IO_READ', 'IO_WRITE' ]

import socket
import logging

import nf_wrapper as notifier
from callback import Callback, WeakCallback
from signals import Signals, Signal
from thread import MainThreadCallback, ThreadCallback, is_mainthread, threaded
from async import InProgress, InProgressCallback
from kaa.utils import property
from timer import OneShotTimer, timed, POLICY_ONCE

# get logging object
log = logging.getLogger('notifier')

IO_READ   = 0
IO_WRITE  = 1

class IOMonitor(notifier.NotifierCallback):
    def __init__(self, callback, *args, **kwargs):
        super(IOMonitor, self).__init__(callback, *args, **kwargs)
        self.set_ignore_caller_args()


    def register(self, fd, condition = IO_READ):
        if self.active():
            if fd != self._id or condition != self._condition:
                raise ValueError('Existing file descriptor already registered with this IOMonitor.')
            return
        if not is_mainthread():
            return MainThreadCallback(self.register)(fd, condition)
        notifier.socket_add(fd, self, condition)
        self._condition = condition
        # Must be called _id to correspond with base class.
        self._id = fd


    def unregister(self):
        if not self.active():
            return
        if not is_mainthread():
            return MainThreadCallback(self.unregister)()
        notifier.socket_remove(self._id, self._condition)
        super(IOMonitor, self).unregister()



class WeakIOMonitor(notifier.WeakNotifierCallback, IOMonitor):
    pass


class Socket(object):
    """
    Notifier-aware socket class.
    """

    signals = Signals('closed', 'read', 'readline', 'new-client')

    def __init__(self):
        self._socket = None
        self._write_buffer = []
        self._addr = None
        self._listening = False
        self._queue_close = False

        # Internal signals for read() and readline()  (these are different from
        # the public signals 'read' and 'readline' as they get emitted even
        # when data is None.  When these signals get updated, we call
        # _update_read_monitor to register the read IOMonitor.
        cb = WeakCallback(self._update_read_monitor)
        self._read_signal = Signal(cb)
        self._readline_signal = Signal(cb)
        self.signals['read'].changed_cb = cb
        self.signals['readline'].changed_cb = cb

        # These variables hold the IOMonitors for monitoring; we only allocate
        # a monitor when the socket is connected to avoid a ref cycle so
        # that disconnected sockets will get properly deleted when they are not
        # referenced.
        self._rmon = self._wmon = None


    @property
    def address(self):
        """
        Either a 2-tuple containing the (host, port) of the remote end of the
        socket (host may be an IP address or hostname, but it always a string),
        or a string in the case of a UNIX socket.

        If this is a listening socket, it is a 2-tuple of the address
        the socket was bound to.
        """
        return self._addr


    @property
    def listening(self):
        """
        True if this is a listening socket, and False otherwise.
        """
        return self._listening


    @property
    def connected(self):
        """
        Boolean representing the connected state of the socket.
        """
        return self._socket != None


    @timed(0, OneShotTimer, POLICY_ONCE)
    def _update_read_monitor(self, signal = None, change = None):
        # Update read IOMonitor to register or unregister based on if there are
        # any handlers attached to the read signals.  If there are no handlers,
        # there is no point in reading data from the socket since it will go 
        # nowhere.  This also allows us to push back the read buffer to the OS.
        if not self._rmon or change == Signal.SIGNAL_DISCONNECTED:
            return
        elif not self._listening and len(self._read_signal) == len(self._readline_signal) == \
                                     len(self.signals['read']) == len(self.signals['readline']) == 0:
           self._rmon.unregister()
        elif not self._rmon.active():
            self._rmon.register(self._socket, IO_READ)


    def _normalize_address(self, addr):
        """
        Converts address strings in the form host:port into 2-tuples 
        containing the hostname and integer port.  Strings not in that
        form are left untouched (as they represent unix socket paths).
        """
        if isinstance(addr, basestring) and ":" in addr:
            addr = addr.split(":")
            assert(len(addr) == 2)
            addr[1] = int(addr[1])
            addr = tuple(addr)

        return addr


    def _make_socket(self, addr = None):
        """
        Constructs a socket based on the given addr.  Returns the socket and
        the normalized address as a 2-tuple.
        """
        addr = self._normalize_address(addr)
        assert(type(addr) in (str, tuple, None))

        if isinstance(addr, basestring):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        return sock, addr


    def _replace_socket(self, sock, addr):
        """
        Replaces the existing socket and address spec with the ones supplied.
        Any existing socket is closed.
        """
        if self._socket:
            self._socket.close()

        self._socket, self._addr = sock, addr


    def listen(self, bind_info, qlen = 5):
        """
        Sets the socket to listen on bind_info, which is either an integer
        corresponding the port to listen to, or a 2-tuple of the IP and port.
        In the case where only the port number is specified, the socket will
        be bound to all interfaces.

        If the bind fails, an exception is raised.

        Once listening, new connections are automatically accepted, and
        the 'new-client' signal is emitted for each new connection.  Callbacks
        connecting to the signal will receive a new Socket object representing
        the client connection.
        """
        if isinstance(bind_info, int):
            # Only port number specified; translate to tuple that can be
            # used with socket.bind()
            bind_info = ('', bind_info)

        sock, addr = self._make_socket(bind_info)
        sock.bind(addr)
        sock.listen(qlen)
        self._listening = True
        self.wrap(sock, addr)


    @threaded()
    def connect(self, addr):
        """
        Connects to the host specified in addr.  If addr is a string in the
        form host:port, or a tuple the form (host, port), a TCP socket is
        established.  Otherwise a Unix socket is established and addr is
        treated as a filename.

        This function is executed in a thread to avoid blocking.  It therefore
        returns an InProgress object.  If the socket is connected, the InProgress
        is finished with no arguments.  If the connection cannot be established,
        an exception is thrown to the InProgress.
        """
        sock, addr = self._make_socket(addr)
        if type(addr) == str:
            # Unix socket, just connect.
            sock.connect(addr)
        else:
            host, port = addr
            if not host.replace(".", "").isdigit():
                # Resolve the hostname.
                host = socket.gethostbyname(host)
            sock.connect((host, port))

        self.wrap(sock, addr)


    def wrap(self, sock, addr = None):
        """
        Wraps an existing low-level socket object.  addr specifies the address
        corresponding to the socket.
        """
        self._socket = sock or self._socket
        self._addr = addr or self._addr
        self._queue_close = False

        sock.setblocking(False)

        if self._rmon:
            self._rmon.unregister()
            self._wmon.unregister()

        self._rmon = IOMonitor(self._handle_read)
        self._wmon = IOMonitor(self._handle_write)

        self._update_read_monitor()
        if self._write_buffer:
            self._wmon.register(sock, IO_WRITE)


    def _async_read(self, signal):
        if self._listening:
            raise RuntimeError("Can't read on a listening socket.")

        return InProgressCallback(signal)


    def read(self):
        """
        Reads a chunk of data from the socket.  This function returns an 
        InProgress object.  If the InProgress is finished with None, it
        means that no data was collected and the socket closed.
        """
        return self._async_read(self._read_signal)


    def readline(self):
        """
        Reads a line from the socket (with newline stripped).  The function
        returns an InProgress object.  If the InProgress is finished with
        None, it means that no data was collected and the socket closed.
        """
        return self._async_read(self._readline_signal)


    def _handle_read(self):
        if self._listening:
            sock, addr = self._socket.accept()
            client_socket = Socket()
            client_socket.wrap(sock, addr)
            self.signals['new-client'].emit(client_socket)
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

        self._read_signal.emit(data)

        if not data:
            self._readline_signal.emit(data)
            return self.close(immediate=True, expected=False)

        self.signals['read'].emit(data)
        self._update_read_monitor()

        # TODO: parse input into separate lines and emit readline.

        

    def close(self, immediate = False, expected = True):
        """
        Closes the socket.  If immediate is False and there is data in the
        write buffer, the socket is closed once the write buffer is emptied.
        Otherwise the socket is closed immediately and the 'closed' signal
        is emitted.
        """
        if not immediate and self._write_buffer:
            # Immediate close not requested and we have some data left
            # to be written, so defer close until after write buffer
            # is empty.
            self._queue_close = True
            return

        self._rmon.unregister()
        self._wmon.unregister()
        self._rmon = self._wmon = None
        del self._write_buffer[:]
        self._queue_close = False

        self._socket.close()
        self._socket = None
        self.signals['closed'].emit(expected)


    def write(self, data):
        self._write_buffer.append(data)
        if self._socket and self._wmon and not self._wmon.active():
            self._wmon.register(self._socket.fileno(), IO_WRITE)


    def _handle_write(self):
        if not self._write_buffer:
            return

        try:
            while self._write_buffer:
                data = self._write_buffer.pop(0)
                sent = self._socket.send(data)
                if sent != len(data):
                    # Not all data was able to be sent; push remaining data
                    # back onto the write buffer.
                    self._write_buffer.insert(0, data[sent:])
                    break

            if not self._write_buffer:
                if self._queue_close:
                    return self.close(immediate=True)
                self._wmon.unregister()

        except socket.error, (errno, msg):
            if errno == 11:
                # Resource temporarily unavailable -- we are trying to write
                # data to a socket when none is available.
                return

            # If we're here, then the socket is likely disconnected.
            self.close(immediate=True, expected=False)
