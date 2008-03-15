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

import sys
import os
import socket
import errno
import logging

import nf_wrapper as notifier
from callback import Callback, WeakCallback
from signals import Signals, Signal
from thread import MainThreadCallback, ThreadCallback, is_mainthread, threaded
from async import InProgress, InProgressCallback
from kaa.utils import property
from timer import OneShotTimer, timed, POLICY_ONCE
from kaa.tmpfile import tempfile

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

    def __init__(self, buffer_size=None, chunk_size=1024*1024):
        self.signals = Signals('closed', 'read', 'readline', 'new-client')
        self._socket = None
        self._write_buffer = []
        self._addr = None
        self._listening = False
        self._queue_close = False
        self._buffer_size = buffer_size
        self._chunk_size = chunk_size

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

    def __repr__(self):
        if not self._socket:
            return '<kaa.Socket - disconnected>'
        return '<kaa.Socket fd=%d>' % self.fileno


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


    @property
    def buffer_size(self):
        """
        Size of the send and receive socket buffers (SO_SNDBUF and SO_RCVBUF)
        in bytes.  Setting this to higher values (say 1M) improves performance
        when sending large amounts of data across the socket.  Note that the
        upper bound may be restricted by the kernel.  (Under Linux, this can be
        tuned by adjusting /proc/sys/net/core/[rw]mem_max)
        """
        return self._buffer_size


    @buffer_size.setter
    def buffer_size(self, size):
        self._buffer_size = size
        if self._socket and size:
            self._set_buffer_size(self._socket, size)


    @property
    def chunk_size(self):
        """
        Number of bytes to attempt to read from the socket at a time.  The
        default is 1M.  A 'read' signal is emitted for each chunk read from the
        socket.  (The number of bytes read at a time may be less than the chunk
        size, but will never be more.)
        """
        return self._chunk_size


    @chunk_size.setter
    def chunk_size(self, size):
        self._chunk_size = size


    @property
    def fileno(self):
        """
        Returns the file descriptor of the socket, or None if the socket is
        not connected.
        """
        if not self._socket:
            return None
        return self._socket.fileno()


    def _set_buffer_size(self, s, size):
        """
        Sets the send and receive buffers of the given socket s to size.
        """
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, size)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, size)
        

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
        Converts address strings in the form host:port into 2-tuples containing
        the hostname and integer port.  Strings not in that form are assumed to
        represent unix socket paths.  If such a string does not start with /, a
        tempfile is used using kaa.tempfile().  If we can't make sense of the
        given address, a ValueError exception will be raised.
        """
        if isinstance(addr, basestring):
            if addr.count(':') == 1:
                addr, port = addr.split(':')
                if not port.isdigit():
                    raise ValueError('Port specified is not an integer')
                return addr, int(port)
            elif not addr.startswith('/'):
                return tempfile(addr)
        elif not isinstance(addr, (tuple, list)) or len(addr) != 2:
            raise ValueError('Invalid address')

        return addr


    def _make_socket(self, addr = None, overwrite = False):
        """
        Constructs a socket based on the given addr.  Returns the socket and
        the normalized address as a 2-tuple.

        If overwrite is True, if addr specifies a path to a unix socket and
        that unix socket already exists, it will be removed if the socket is
        not actually in use.  If it is in use, an IOError will be raised.
        """
        addr = self._normalize_address(addr)
        assert(type(addr) in (str, tuple, None))

        if isinstance(addr, basestring):
            if overwrite and os.path.exists(addr):
                # Unix socket exists; test to see if it's active.
                try:
                    dummy = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    dummy.connect(addr)
                except socket.error, (err, msg):
                    if err == errno.ECONNREFUSED:
                        # Socket is not active, so we can remove it.
                        log.debug('Replacing dead unix socket at %s' % addr)
                    else:
                        # Reraise unexpected exception
                        tp, exc, tb = sys.exc_info()
                        raise tp, exc, tb
                else:
                    # We were able to connect to the existing socket, so it's
                    # in use.  We won't overwrite it.
                    raise IOError('Address already in use')
                os.unlink(addr)

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

        sock, addr = self._make_socket(bind_info, overwrite=True)
        sock.bind(addr)
        if addr[1] == 0:
            # get real port used
            addr = (addr[0], sock.getsockname()[1])
        sock.listen(qlen)
        self._listening = True
        self.wrap(sock, addr)


    @threaded()
    def connect(self, addr):
        """
        Connects to the host specified in addr.  If addr is a string in the
        form host:port, or a tuple the form (host, port), a TCP socket is
        established.  Otherwise a Unix socket is established and addr is
        treated as a filename.  In this case, if addr does not start with a /
        character, a kaa tempfile is created.

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
        # wrap() must be called from the mainthread or the internal import kaa
        # will block. No idea why.
        return MainThreadCallback(self.wrap, sock, addr)()


    def wrap(self, sock, addr = None):
        """
        Wraps an existing low-level socket object.  addr specifies the address
        corresponding to the socket.
        """
        self._socket = sock or self._socket
        self._addr = addr or self._addr
        self._queue_close = False

        sock.setblocking(False)
        if self._buffer_size:
            self._set_buffer_size(sock, self._buffer_size)

        if self._rmon:
            self._rmon.unregister()
            self._wmon.unregister()

        self._rmon = IOMonitor(self._handle_read)
        self._wmon = IOMonitor(self._handle_write)

        self._update_read_monitor()
        if self._write_buffer:
            self._wmon.register(sock, IO_WRITE)

        import kaa
        # Disconnect socket and remove socket file (if unix socket) on shutdown
        kaa.signals['shutdown'].connect_weak(self.close)
        

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


    def _accept(self):
        """
        Accept a new connection and return a new Socket object.
        """
        sock, addr = self._socket.accept()
        client_socket = Socket()
        client_socket.wrap(sock, addr)
        self.signals['new-client'].emit(client_socket)


    def _handle_read(self):
        if self._listening:
            return self._accept()

        try:
            data = self._socket.recv(self._chunk_size)
        except socket.error, (errno, msg):
            if errno == 11:
                # Resource temporarily unavailable -- we are trying to read
                # data on a socket when none is available.
                return
            # If we're here, then the socket is likely disconnected.
            data = None
        except:
            log.exception('kaa.Socket._handle_read failed with unknown exception, closing socket')
            data = None

        # _read_signal is for InProgress objects waiting on the next read().
        # For these we must emit even when data is None.
        self._read_signal.emit(data)

        if not data:
            self._readline_signal.emit(data)
            return self.close(immediate=True, expected=False)

        self.signals['read'].emit(data)
        # FIXME: why do this here?
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
        if self._listening and isinstance(self._addr, basestring) and self._addr.startswith('/'):
            # Remove unix socket if it exists.
            try:
                os.unlink(self._addr)
            except OSError:
                pass

        self._addr = None
        self._socket = None

        self.signals['closed'].emit(expected)
        import kaa
        kaa.signals['shutdown'].disconnect(self.close)


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
