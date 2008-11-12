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
import time

import nf_wrapper as notifier
from callback import WeakCallback
from signals import Signals, Signal
from thread import MainThreadCallback, is_mainthread, threaded
from async import InProgress, inprogress
from kaa.utils import property
from kaa.tmpfile import tempfile

# FIXME: this file is getting big enough: move IOMonitor and IODescriptor to
# io.py, and leave Socket in this file.

# get logging object
log = logging.getLogger('notifier')

IO_READ   = 1
IO_WRITE  = 2

class IOMonitor(notifier.NotifierCallback):
    def __init__(self, callback, *args, **kwargs):
        """
        Creates an IOMonitor to monitor IO activity.
        """
        super(IOMonitor, self).__init__(callback, *args, **kwargs)
        self.set_ignore_caller_args()


    def register(self, fd, condition = IO_READ):
        """
        Register the IOMonitor to a specific file descriptor
        @param fd: File descriptor or Python socket object
        @param condition: IO_READ or IO_WRITE
        """
        if self.active():
            if fd != self._id or condition != self._condition:
                raise ValueError('Existing file descriptor already registered with this IOMonitor.')
            return
        if not is_mainthread():
            return MainThreadCallback(self.register)(fd, condition)
        notifier.socket_add(fd, self, condition-1)
        self._condition = condition
        # Must be called _id to correspond with base class.
        self._id = fd


    def unregister(self):
        """
        Unregister the IOMonitor
        """
        if not self.active():
            return
        if not is_mainthread():
            return MainThreadCallback(self.unregister)()
        notifier.socket_remove(self._id, self._condition-1)
        super(IOMonitor, self).unregister()



class WeakIOMonitor(notifier.WeakNotifierCallback, IOMonitor):
    """
    IOMonitor using weak references for the callback.
    """
    pass


# We need to import main for the signals dict (we add a handler to
# shutdown to gracefully close sockets), but main itself imports us
# for IOMonitor.  So we must import main _after_ declaring IOMonitor,
# instead of doing so at the top of the file.
from kaa.notifier import main

class IODescriptor(object):
    """
    Base class for read-only, write-only or read-write descriptors such as
    Socket and Process.  Implements logic common to communication over
    descriptors such as async read/writes and read/write buffering.
    """
    def __init__(self, fd=None, mode=IO_READ|IO_WRITE, chunk_size=1024*1024):
        self.signals = Signals('closed', 'read', 'readline', 'write')
        self.wrap(fd, mode)
        self._write_queue = []
        self._queue_close = False
        self._chunk_size = chunk_size
    
        # Internal signals for read() and readline()  (these are different from
        # the same-named public signals as they get emitted even when data is
        # None.  When these signals get updated, we call _update_read_monitor
        # to register the read IOMonitor.
        cb = WeakCallback(self._update_read_monitor)
        self._read_signal = Signal(cb)
        self._readline_signal = Signal(cb)
        self.signals['read'].changed_cb = cb
        self.signals['readline'].changed_cb = cb

        # These variables hold the IOMonitors for monitoring; we only allocate
        # a monitor when the fd is connected to avoid a ref cycle so that
        # disconnected fds will get properly deleted when they are not
        # referenced.
        self._rmon = None
        self._wmon = None


    @property
    def alive(self):
        """
        Returns True if the fd exists and is open.
        """
        # If the fd is closed, self._fd will be None.
        return self._fd != None


    @property
    def fileno(self):
        """
        Returns the integer for this file descriptor, or None if no descriptor
        has been set.
        """
        try:
            return self._fd.fileno()
        except AttributeError:
            return self._fd


    @property
    def chunk_size(self):
        """
        Number of bytes to attempt to read from the fd at a time.  The
        default is 1M.  A 'read' signal is emitted for each chunk read from the
        fd.  (The number of bytes read at a time may be less than the chunk
        size, but will never be more.)
        """
        return self._chunk_size


    @chunk_size.setter
    def chunk_size(self, size):
        self._chunk_size = size


    # TODO: settable write_queue_max property

    @property
    def write_queue_size(self):
        """
        Returns the number of bytes queued in memory to be written to the
        descriptor.
        """
        # XXX: this is not terribly efficient when the write queue has
        # many elements.  We may decide to keep a separate counter.
        return sum(len(data) for data, inprogress in self._write_queue)


    def _is_read_connected(self):
        """
        Returns True if we're interested in read events.
        """
        return not len(self._read_signal) == len(self._readline_signal) == \
                   len(self.signals['read']) == len(self.signals['readline']) == 0
        

    def _update_read_monitor(self, signal=None, change=None):
        """
        Update read IOMonitor to register or unregister based on if there are
        any handlers attached to the read signals.  If there are no handlers,
        there is no point in reading data from the descriptor since it will go 
        nowhere.  This also allows us to push back the read buffer to the OS.

        We must call this immediately after reading a block, and not defer
        it until the end of the mainloop iteration via a timer in order not
        to lose incoming data between read() calls.
        """
        if not (self._mode & IO_READ) or not self._rmon or change == Signal.SIGNAL_DISCONNECTED:
            return
        elif not self._is_read_connected():
            self._rmon.unregister()
        elif not self._rmon.active():
            self._rmon.register(self.fileno, IO_READ)


    def _set_non_blocking(self):
        """
        Low-level call to set the fd non-blocking.  Can be overridden by
        subclasses.
        """
        flags = fcntl.fcntl(self.fileno, fcntl.F_GETFL)
        fcntl.fcntl(self.fileno, fcntl.F_SETFL, flags | os.O_NONBLOCK)


    def wrap(self, fd, mode):
        """
        Wraps an existing file descriptor.
        """
        self._fd = fd
        self._mode = mode
        if not fd:
            return
        self._set_non_blocking()

        if self._mode & IO_READ:
            if self._rmon:
                self._rmon.unregister()
            self._rmon = IOMonitor(self._handle_read)
            self._update_read_monitor()

        if self._mode & IO_WRITE:
            if self._wmon:
                self._wmon.unregister()
            self._wmon = IOMonitor(self._handle_write)
            if self._write_queue:
                self._wmon.register(self.fileno, IO_WRITE)

        # Disconnect socket and remove socket file (if unix socket) on shutdown
        main.signals['shutdown'].connect_weak(self.close)


    def _is_readable(self):
        """
        Low-level call to read from fd.  Can be overridden by subclasses.
        """
        return self._fd != None


    def _async_read(self, signal):
        """
        Common implementation for read() and readline().
        """
        if not (self._mode & IO_READ):
            raise IOError(9, 'Cannot read on a write-only descriptor')
        if not self._is_readable():
            # fd is not readable.  Return an InProgress pre-finished
            # with None
            return InProgress().finish(None)

        return inprogress(signal)


    def read(self):
        """
        Reads a chunk of data from the fd.  This function returns an 
        InProgress object.  If the InProgress is finished with None, it
        means that no data was collected and the fd closed.

        It is therefore possible to busy-loop by reading on a closed
        fd::

            while True:
                fd.read().wait()

        So the return value of read() should be checked.  Alternatively,
        fd.alive could be tested::

            while fd.alive:
                fd.read().wait()

        """
        return self._async_read(self._read_signal)


    def readline(self):
        """
        Reads a line from the fd (with newline stripped).  The function
        returns an InProgress object.  If the InProgress is finished with None
        or the empty string, it means that no data was collected and the socket
        closed.
        """
        return self._async_read(self._readline_signal)


    def _read(self, size):
        """
        Low-level call to read from fd.  Can be overridden by subclasses.
        """
        return os.read(self.fileno, size)


    def _handle_read(self):
        """
        IOMonitor callback when there is data to be read from the fd.
        
        This callback is only registered when we know the user is interested in
        reading data (by connecting to the read or readline signals, or calling
        read() or readline()).  This is necessary for flow control.
        """
        try:
            data = self._read(self._chunk_size)
        except (IOError, socket.error), (errno, msg):
            if errno == 11:
                # Resource temporarily unavailable -- we are trying to read
                # data on a socket when none is available.
                return
            # If we're here, then the socket is likely disconnected.
            data = None
        except:
            log.exception('%s._handle_read failed with unknown exception, closing socket', self.__class__.__name__)
            data = None

        # _read_signal is for InProgress objects waiting on the next read().
        # For these we must emit even when data is None.
        self._read_signal.emit(data)

        if not data:
            self._readline_signal.emit(data)
            return self.close(immediate=True, expected=False)

        self.signals['read'].emit(data)
        # Update read monitor if necessary.  If there are no longer any
        # callbacks left on any of the read signals (most likely _read_signal
        # or _readline_signal), we want to prevent _handle_read() from being
        # called, otherwise next time read() or readline() is called, we will
        # have lost that data.
        self._update_read_monitor()


        # TODO: parse input into separate lines and emit readline.


    def _write(self, data):
        """
        Low-level call to write to the fd  Can be overridden by subclasses.
        """
        return os.write(self.fileno, data)


    def write(self, data):
        """
        Writes the given data to the fd.  This method returns an InProgress
        object which is finished when the given data is fully written to the
        file descriptor.

        It is not required that the descriptor be open in order to write to it.
        Written data is queued until the descriptor open and then flushed.  As
        writes are asynchronous, all written data is queued.  It is the
        caller's responsibility to ensure the internal write queue does not
        exceed the desired size by waiting for past write() InProgress to
        finish before writing more data.

        If a write does not complete because the file descriptor was closed
        prematurely, an IOError is thrown to the InProgress.
        """
        if not (self._mode & IO_WRITE):
            raise IOError(9, 'Cannot write to a read-only descriptor')

        inprogress = InProgress()
        if data:
            self._write_queue.append((data, inprogress))
            if self._fd and self._wmon and not self._wmon.active():
                self._wmon.register(self.fileno, IO_WRITE)
        else:
            # We're writing the null string, nothing really to do.  We're
            # implicitly done.
            inprogress.finish(0)
        return inprogress


    def _handle_write(self):
        """
        IOMonitor callback when the fd is writable.  This callback is not
        registered then the write queue is empty, so we only get called when
        there is something to write.
        """
        if not self._write_queue:
            # Shouldn't happen; sanity check.
            return

        try:
            while self._write_queue:
                data, inprogress = self._write_queue.pop(0)
                sent = self._write(data)
                if sent != len(data):
                    # Not all data was able to be sent; push remaining data
                    # back onto the write buffer.
                    self._write_queue.insert(0, (data[sent:], inprogress))
                    break
                else:
                    # All data is written, finish the InProgress associated
                    # with this write.
                    inprogress.finish(sent)

            if not self._write_queue:
                if self._queue_close:
                    return self.close(immediate=True)
                self._wmon.unregister()

        except (IOError, socket.error), (errno, msg):
            if errno == 11:
                # Resource temporarily unavailable -- we are trying to write
                # data to a socket when none is available.  To prevent a busy
                # loop (notifier loop will keep calling us back) we sleep a
                # tiny bit.  It's admittedly a bit kludgy, but it's a simple
                # solution to a condition which should not occur often.
                time.sleep(0.001)
                return

            # If we're here, then the socket is likely disconnected.
            self.close(immediate=True, expected=False)


    def _close(self):
        """
        Low-level call to close the fd  Can be overridden by subclasses.
        """
        os.close(self.fileno)


    def close(self, immediate=False, expected=True):
        """
        Closes the fd.  If immediate is False and there is data in the
        write buffer, the fd is closed once the write buffer is emptied.
        Otherwise the fd is closed immediately and the 'closed' signal
        is emitted.
        """
        if not immediate and self._write_queue:
            # Immediate close not requested and we have some data left
            # to be written, so defer close until after write queue
            # is empty.
            self._queue_close = True
            return

        if not self._rmon and not self._wmon:
            # already closed
            return

        if self._rmon:
            self._rmon.unregister()
        if self._wmon:
            self._wmon.unregister()
        self._rmon = None
        self._wmon = None
        self._queue_close = False

        # Throw IOError to any pending InProgress in the write queue
        for data, inprogress in self._write_queue:
            if len(inprogress):
                # Somebody cares about this InProgress, so we need to finish
                # it.
                inprogress.throw(IOError, IOError(9, "Descriptor closed prematurely"), None)
        del self._write_queue[:]

        self._close()
        self._fd = None

        self.signals['closed'].emit(expected)
        main.signals['shutdown'].disconnect(self.close)


class SocketError(Exception):
    pass

class Socket(IODescriptor):
    """
    Notifier-aware socket class, implementing fully asynchronous reads
    and writes.
    """

    def __init__(self, buffer_size=None, chunk_size=1024*1024):
        self._connecting = False
        self._addr = None
        self._listening = False
        self._buffer_size = buffer_size

        super(Socket, self).__init__(chunk_size=chunk_size)
        self.signals += ('new-client',)


    def __repr__(self):
        if not self._fd:
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
    def connecting(self):
        """
        True if the socket is in the process of establishing a connection
        but is not yet connected.  Once the socket is connected, the
        connecting property will be False, but the connected property
        will be True.
        """
        return self._connecting


    @property
    def connected(self):
        """
        Boolean representing the connected state of the socket.
        """
        try:
            # Will raise exception if socket is not connected.
            self._fd.getpeername()
            return True
        except:
            return False


    @property
    def alive(self):
        """
        Returns True if the socket is alive, and False otherwise.  A socket is
        considered alive when it is connected or in the process of connecting.
        """
        return self.connected or self.connecting


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
        if self._fd and size:
            self._set_buffer_size(self._fd, size)


    def _set_buffer_size(self, s, size):
        """
        Sets the send and receive buffers of the given socket s to size.
        """
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, size)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, size)
        

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


    def _make_socket(self, addr=None, overwrite=False):
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


    def listen(self, bind_info, qlen=5):
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
    def _connect(self, addr):
        sock, addr = self._make_socket(addr)
        try:
            if type(addr) == str:
                # Unix socket, just connect.
                sock.connect(addr)
            else:
                host, port = addr
                if not host.replace(".", "").isdigit():
                    # Resolve the hostname.
                    host = socket.gethostbyname(host)
                sock.connect((host, port))
        finally:
            self._connecting = False

        self.wrap(sock, addr)


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
        self._connecting = True
        return self._connect(addr)


    def wrap(self, sock, addr=None):
        """
        Wraps an existing low-level socket object.  addr specifies the address
        corresponding to the socket.
        """
        super(Socket, self).wrap(sock, IO_READ|IO_WRITE)
        self._addr = addr or self._addr

        if self._buffer_size:
            self._set_buffer_size(sock, self._buffer_size)


    def _is_read_connected(self):
        return self._listening or super(Socket, self)._is_read_connected()


    def _set_non_blocking(self):
        self._fd.setblocking(False)


    def _is_readable(self):
        return self._fd and not self._connecting


    def _read(self, size):
        return self._fd.recv(size)


    def _write(self, data):
        return self._fd.send(data)


    def _close(self):
        self._fd.close()


    def _accept(self):
        """
        Accept a new connection and return a new Socket object.
        """
        sock, addr = self._fd.accept()
        # create new Socket from the same class this object is
        client_socket = self.__class__()
        client_socket.wrap(sock, addr)
        self.signals['new-client'].emit(client_socket)


    def _handle_read(self):
        if self._listening:
            return self._accept()

        return super(Socket, self)._handle_read()
        

    def close(self, immediate=False, expected=True):
        super(Socket, self).close(immediate, expected)
        if self._listening and isinstance(self._addr, basestring) and self._addr.startswith('/'):
            # Remove unix socket if it exists.
            try:
                os.unlink(self._addr)
            except OSError:
                pass

        self._addr = None
