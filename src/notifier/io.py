# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# io.py - Supporting classes for notifier-aware I/O
# -----------------------------------------------------------------------------
# $Id: io.py 3661 2008-11-12 02:31:59Z tack $
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

__all__ = [ 'IO_READ', 'IO_WRITE', 'IOMonitor', 'WeakIOMonitor', 'IOChannel' ]

import sys
import os
import socket
import logging
import time
import fcntl

import nf_wrapper as notifier
from callback import WeakCallback
from signals import Signals, Signal
from thread import MainThreadCallback, is_mainthread
from async import InProgress, inprogress
from kaa.utils import property

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

class IOChannel(object):
    """
    Base class for read-only, write-only or read-write descriptors such as
    Socket and Process.  Implements logic common to communication over
    such channels such as async read/writes and read/write buffering.
    """
    def __init__(self, channel=None, mode=IO_READ|IO_WRITE, chunk_size=1024*1024):
        self.signals = Signals('closed', 'read', 'readline', 'write')
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
        # a monitor when the channel is connected to avoid a ref cycle so that
        # disconnected channels will get properly deleted when they are not
        # referenced.
        self._rmon = None
        self._wmon = None

        self.wrap(channel, mode)


    @property
    def alive(self):
        """
        Returns True if the channel exists and is open.
        """
        # If the channel is closed, self._channel will be None.
        return self._channel != None


    @property
    def fileno(self):
        """
        Returns the file descriptor (integer) for this channel, or None if no
        channel has been set.
        """
        try:
            return self._channel.fileno()
        except AttributeError:
            return self._channel


    @property
    def chunk_size(self):
        """
        Number of bytes to attempt to read from the channel at a time.  The
        default is 1M.  A 'read' signal is emitted for each chunk read from the
        channel.  (The number of bytes read at a time may be less than the chunk
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
        channel.
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
        there is no point in reading data from the channel since it will go 
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
        Low-level call to set the channel non-blocking.  Can be overridden by
        subclasses.
        """
        flags = fcntl.fcntl(self.fileno, fcntl.F_GETFL)
        fcntl.fcntl(self.fileno, fcntl.F_SETFL, flags | os.O_NONBLOCK)


    def wrap(self, channel, mode):
        """
        Wraps an existing channel.  Assumes a file-like object or a file
        descriptor (int).
        """
        self._channel = channel
        self._mode = mode
        if not channel:
            return
        self._set_non_blocking()

        if self._rmon:
            self._rmon.unregister()
            self._rmon = None
        if self._wmon:
            self._wmon.unregister()
            self._wmon = None

        if self._mode & IO_READ:
            self._rmon = IOMonitor(self._handle_read)
            self._update_read_monitor()
        if self._mode & IO_WRITE:
            self._wmon = IOMonitor(self._handle_write)
            if self._write_queue:
                self._wmon.register(self.fileno, IO_WRITE)

        # Disconnect socket and remove socket file (if unix socket) on shutdown
        main.signals['shutdown'].connect_weak(self.close)


    def _is_readable(self):
        """
        Low-level call to read from channel.  Can be overridden by subclasses.
        """
        return self._channel != None


    def _async_read(self, signal):
        """
        Common implementation for read() and readline().
        """
        if not (self._mode & IO_READ):
            raise IOError(9, 'Cannot read on a write-only channel')
        if not self._is_readable():
            # channel is not readable.  Return an InProgress pre-finished
            # with None
            return InProgress().finish(None)

        return inprogress(signal)


    def read(self):
        """
        Reads a chunk of data from the channel.  This function returns an 
        InProgress object.  If the InProgress is finished with None, it
        means that no data was collected and the channel closed.

        It is therefore possible to busy-loop by reading on a closed
        channel::

            while True:
                channel.read().wait()

        So the return value of read() should be checked.  Alternatively,
        channel.alive could be tested::

            while channel.alive:
                channel.read().wait()

        """
        return self._async_read(self._read_signal)


    def readline(self):
        """
        Reads a line from the channel (with newline stripped).  The function
        returns an InProgress object.  If the InProgress is finished with None
        or the empty string, it means that no data was collected and the socket
        closed.
        """
        return self._async_read(self._readline_signal)


    def _read(self, size):
        """
        Low-level call to read from channel.  Can be overridden by subclasses.
        Must return a string of at most size bytes, or the empty string or
        None if no data is available.
        """
        return os.read(self.fileno, size)


    def _handle_read(self):
        """
        IOMonitor callback when there is data to be read from the channel.
        
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
            log.exception('%s._handle_read failed, closing socket', self.__class__.__name__)
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
        Low-level call to write to the channel  Can be overridden by subclasses.
        Must return number of bytes written to the channel.
        """
        return os.write(self.fileno, data)


    def write(self, data):
        """
        Writes the given data to the channel.  This method returns an InProgress
        object which is finished when the given data is fully written to the
        channel.

        It is not required that the channel be open in order to write to it.
        Written data is queued until the channel open and then flushed.  As
        writes are asynchronous, all written data is queued.  It is the
        caller's responsibility to ensure the internal write queue does not
        exceed the desired size by waiting for past write() InProgress to
        finish before writing more data.

        If a write does not complete because the channel was closed
        prematurely, an IOError is thrown to the InProgress.
        """
        if not (self._mode & IO_WRITE):
            raise IOError(9, 'Cannot write to a read-only channel')

        inprogress = InProgress()
        if data:
            self._write_queue.append((data, inprogress))
            if self._channel and self._wmon and not self._wmon.active():
                self._wmon.register(self.fileno, IO_WRITE)
        else:
            # We're writing the null string, nothing really to do.  We're
            # implicitly done.
            inprogress.finish(0)
        return inprogress


    def _handle_write(self):
        """
        IOMonitor callback when the channel is writable.  This callback is not
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

        except Exception, args:
            tp, exc, tb = sys.exc_info()
            if tp in (IOError, socket.error) and args[0] == 11:
                # Resource temporarily unavailable -- we are trying to write
                # data to a socket which is not ready.  To prevent a busy loop
                # (notifier loop will keep calling us back) we sleep a tiny
                # bit.  It's admittedly a bit kludgy, but it's a simple
                # solution to a condition which should not occur often.
                time.sleep(0.001)
                return

            if tp in (IOError, socket.error, OSError):
                # Any of these are treated as fatal.  We close, which
                # also throws to any other pending InProgress writes.
                self.close(immediate=True, expected=False)
    
            # Throw the current exception to the InProgress for this write.
            # If nobody is listening for it, it will eventually get logged
            # as unhandled.
            inprogress.throw(tp, exc, tb)

            # XXX: this seems to be necessary in order to get the unhandled
            # InProgress to log, but I've no idea why.
            del inprogress


    def _close(self):
        """
        Low-level call to close the channel.  Can be overridden by subclasses.
        """
        try:
            self._channel.close()
        except AttributeError:
            os.close(self.fileno)


    def close(self, immediate=False, expected=True):
        """
        Closes the channel.  If immediate is False and there is data in the
        write buffer, the channel is closed once the write buffer is emptied.
        Otherwise the channel is closed immediately and the 'closed' signal
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
                inprogress.throw(IOError, IOError(9, 'Channel closed prematurely'), None)
        del self._write_queue[:]

        try:
            self._close()
        except (IOError, socket.error), (errno, msg):
            # Channel may already be closed, which is ok.
            if errno != 9:
                # It isn't, this is some other error, so reraise exception.
                raise
        finally:
            self._channel = None

            self.signals['closed'].emit(expected)
            main.signals['shutdown'].disconnect(self.close)
