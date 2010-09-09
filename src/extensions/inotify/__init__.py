# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# inotify/__init__.py - Inotify interface
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright 2006-2009 Jason Tackaberry, Dirk Meyer
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
from __future__ import absolute_import

# python imports
import os
import struct
import logging
import fcntl
import select
import errno
import socket
import string

# kaa imports
import kaa
from ..strutils import py3_b, py3_str
try:
    # imports C module
    from . import _inotify
except ImportError:
    _inotify = None

# get logging object
log = logging.getLogger('inotify')

class INotify(kaa.Object):
    """
    Monitor files and directories, invoking callbacks when changes occur.

    Multiple instances of this class can be created, but note that there is
    a per-user limit of the number of INotify instances allowed, which is
    controlled by /proc/sys/fs/inotify/max_user_instances
    """
    __kaasignals__ = {
        'event':
            '''
            Emitted when an event occurs on any file or directory currently
            being monitored by this INotify instance.

            .. describe:: def callback(mask, filename, target)

               :param mask: a bitmask of events
               :type mask: int
               :param source: the filename the event applies to
               :type filename: str
               :param target: if the mask contains both MOVED_TO | MOVED_FROM,
                              filename was renamed to target.  Otherwise,
                              target is None.
            '''
    }

    @staticmethod
    def mask_to_string(mask):
        """
        Converts a bitmask of events to a human-readable string.

        :param mask: the bitmask of events
        :type mask: int
        :returns: a string in the form EVENT1 | EVENT2 | EVENT3 ...
        """
        events = []
        for attr in ['CHANGE'] + INotify.__dict__.keys():
            if attr == 'WATCH_MASK' or attr[0] not in string.ascii_uppercase:
                continue
            event = getattr(INotify, attr)
            if mask & event == event:
                events.append(attr)
                mask &= ~event
        return ' | '.join(events)


    def __init__(self):
        super(INotify, self).__init__()
        if not _inotify:
            self._fd = -1
            raise SystemError('INotify support not compiled.')

        self._watches = {}
        self._watches_by_path = {}
        # We keep track of recently removed watches so we don't get confused
        # if an event callback removes a watch while we're currently
        # processing a batch of events and we receive an event for a watch
        # we just removed.
        self._watches_recently_removed = []
        self._read_buffer = py3_b('')
        self._move_state = None  # For MOVED_FROM events
        self._moved_timer = kaa.WeakOneShotTimer(self._emit_last_move)

        self._fd = _inotify.init()

        if self._fd < 0:
            raise SystemError('INotify support not detected on this system.')

        fcntl.fcntl(self._fd, fcntl.F_SETFL, os.O_NONBLOCK)
        self._mon = kaa.WeakIOMonitor(self._handle_data)
        self._mon.register(self._fd)


    def __del__(self):
        if os and self._fd >= 0 and self._mon:
            os.close(self._fd)
            self._mon.unregister()
            self._mon = None


    def watch(self, path, mask=None):
        """
        Begin monitoring a file or directory for specific events.

        :param path: the full path to the file or directory to be monitored
        :type path: str
        :param mask: a bitmask of events for which to notify, or None
                     to use the default mask (see below).
        :type mask: int
        :returns: :class:`~kaa.Signal` object that is emitted when an event occurs
                  on ``path``.

        
        The default mask is anything that causes a change (new file, deleted
        file, modified file, or attribute change on the file).
        
        Callbacks connected to the returned signal are invoked with the same
        arguments as the :attr:`~kaa.INotify.signals.event` signal.

        The total number of watches (across all INotify instances) is controlled
        by /proc/sys/fs/inotify/max_user_watches
        """
        path = os.path.realpath(path)
        if path in self._watches_by_path:
            return self._watches_by_path[path][0]

        if mask == None:
            mask = INotify.WATCH_MASK

        wd = _inotify.add_watch(self._fd, path, mask)
        if wd < 0:
            raise IOError('Failed to add watch on "%s"' % path)

        signal = kaa.Signal()
        self._watches[wd] = [signal, path]
        self._watches_by_path[path] = [signal, wd]
        return signal


    def ignore(self, path):
        """
        Removes a watch on the given path.

        :param path: the path that had been previously passed to 
                     :meth:`~kaa.INotify.watch`
        :type path: str
        :returns: True if a matching monitor was removed, or False otherwise.
        """
        path = os.path.realpath(path)
        if path not in self._watches_by_path:
            return False

        wd = self._watches_by_path[path][1]
        _inotify.rm_watch(self._fd, wd)
        del self._watches[wd]
        del self._watches_by_path[path]
        self._watches_recently_removed.append(wd)
        return True


    def has_watch(self, path):
        """
        Determine if the given path is currently watched by the INotify object.

        :param path: the path that had been previously passed to 
                     :meth:`~kaa.INotify.watch`
        :type path: str
        :returns: True if there is a matching monitor, or False otherwise.
        """
        path = os.path.realpath(path)
        return path in self._watches_by_path


    def get_watches(self):
        """
        Returns a list of all paths monitored by the object.

        :returns: list of strings
        """
        return self._watches_by_path.keys()


    def _emit_last_move(self):
        """
        Emits the last move event (MOVED_FROM), if it exists.
        """
        if not self._move_state:
            return

        prev_wd, prev_mask, dummy, prev_path = self._move_state
        self._watches[prev_wd][0].emit(prev_mask, prev_path)
        self.signals["event"].emit(prev_mask, prev_path, None)
        self._move_state = None
        self._moved_timer.stop()


    def _handle_data(self):
        try:
            data = os.read(self._fd, 32768)
        except socket.error, (err, msg):
            if err == errno.EAGAIN:
                # Resource temporarily unavailable -- we are trying to read
                # data on a socket when none is avilable.  This should not
                # happen under normal circumstances, so log an error.
                log.error("INotify data handler called but no data available.")
            return

        self._read_buffer += data

        event_len = struct.calcsize('IIII')
        while True:
            if len(self._read_buffer) < event_len:
                if self._move_state:
                    # We received a MOVED_FROM event with no matching
                    # MOVED_TO.  If we don't get a matching MOVED_TO in 0.1
                    # seconds, emit the MOVED_FROM event.
                    self._moved_timer.start(0.1)
                break

            wd, mask, cookie, size = struct.unpack("IIII", self._read_buffer[0:event_len])
            if size:
                name = py3_str(self._read_buffer[event_len:event_len+size]).rstrip('\0')
            else:
                name = None

            self._read_buffer = self._read_buffer[event_len+size:]
            if wd not in self._watches:
                if wd not in self._watches_recently_removed:
                    # Weird, received an event for an unknown watch; this
                    # shouldn't happen under sane circumstances, so log this as
                    # an error.
                    log.error("INotify received event for unknown watch.")
                continue

            path = self._watches[wd][1]
            if name:
                path = os.path.join(path, name)

            if self._move_state:
                # Last event was a MOVED_FROM. So if this is a MOVED_TO and the
                # cookie matches, emit once specifying both paths. If not,
                # we will end up emitting two separate MOVED_FROM and MOVED_TO
                # events.
                if mask & INotify.MOVED_TO and cookie == self._move_state[2]:
                    # Great, they match. Fire a MOVE signal with both paths.
                    mask |= INotify.MOVED_FROM
                    prev_wd, dummy, dummy, prev_path = self._move_state
                    self._watches[wd][0].emit(mask, prev_path, path)
                    if prev_wd != wd:
                        # The src and target watch descriptors are different.
                        # Not entirely sure if this can happen, but if it can,
                        # we should emit on both signal.s
                        self._watches[prev_wd][0].emit(mask, prev_path, path)
                    self.signals["event"].emit(mask, prev_path, path)
                    self._move_state = None
                    self._moved_timer.stop()
                    continue

                # No match, fire the earlier MOVED_FROM signal now
                # with no target.
                self._emit_last_move()

            if mask & INotify.MOVED_FROM:
                # This is a MOVED_FROM. Don't emit the signals now, let's wait
                # for a MOVED_TO, which we expect to be next.
                self._move_state = wd, mask, cookie, path
                continue

            self._watches[wd][0].emit(mask, path, None)
            self.signals["event"].emit(mask, path, None)

            if mask & INotify.IGNORED:
                # Self got deleted, so remove the watch data.
                del self._watches[wd]
                del self._watches_by_path[path]
                self._watches_recently_removed.append(wd)

        if not self._read_buffer and len(self._watches_recently_removed) and \
           not select.select([self._fd], [], [], 0)[0]:
            # We've processed all pending inotify events.  We can reset the
            # recently removed watches list.
            self._watches_recently_removed = []


if _inotify:
    # Copy constants from _inotify to INotify
    for attr in dir(_inotify):
        if attr[0].isupper():
            setattr(INotify, attr, getattr(_inotify, attr))

    INotify.WATCH_MASK = INotify.MODIFY | INotify.ATTRIB | INotify.DELETE | \
                         INotify.CREATE | INotify.DELETE_SELF | \
                         INotify.UNMOUNT | INotify.MOVE | INotify.MOVE_SELF | \
                         INotify.MOVED_FROM | INotify.MOVED_TO

    INotify.CHANGE     = INotify.MODIFY | INotify.ATTRIB

