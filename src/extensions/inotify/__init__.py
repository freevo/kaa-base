try:
    from kaa.inotify import _inotify
except ImportError:
    _inotify = None

import kaa.notifier
import os
import struct

# TODO: hook in gamin if it is running. See gamin.py

class INotify:

    # TODO: use singleton design pattern.

    def __init__(self):
        if not _inotify:
            self._fd = -1
            raise SystemError, "INotify support not compiled."

        self.signals = {
            # Master signal: this signal gets emitted on all events.
            "event": kaa.notifier.Signal()
        }

        self._watches = {}
        self._watches_by_path = {}
        self._read_buffer = ""

        self._fd = _inotify.init()
        if self._fd < 0:
            raise SystemError, "INotify support not detected on this system."

        self._mon = kaa.notifier.WeakSocketDispatcher(self._handle_data)
        self._mon.register(self._fd)
        kaa.notifier.signals['shutdown'].connect_weak(self._close)


    def _close(self):
        if os and self._fd >= 0 and self._mon:
            os.close(self._fd)
            self._mon.unregister()
            self._mon = None
        
    def __del__(self):
        if os and self._fd >= 0 and self._mon:
            os.close(self._fd)
            self._mon.unregister()
            self._mon = None


    def watch(self, path, mask = None):
        """
        Adds a watch to the given path.  The default mask is anything that
        causes a change (new file, deleted file, modified file, or attribute
        change on the file).  This function returns a Signal that the caller
        can then connect to.  Any time there is a notification, the signal
        will get emitted.  Callbacks connected to the signal must accept 2
        arguments: notify mask and filename.
        """
        path = os.path.realpath(path)
        if path in self._watches_by_path:
            return self._watches_by_path[path][0]

        if mask == None:
            mask = INotify.WATCH_MASK

        wd = _inotify.add_watch(self._fd, path, mask)
        if wd < 0:
            raise IOError, "Failed to add watch on '%s'" % path

        signal = kaa.notifier.Signal()
        self._watches[wd] = [signal, path]
        self._watches_by_path[path] = [signal, wd]
        return signal


    def ignore(self, path):
        """
        Removes a watch on the given path.
        """
        path = os.path.realpath(path)
        if path not in self._watches_by_path:
            return False

        wd = self._watches_by_path[path][1]
        _inotify.rm_watch(self._fd, wd)
        del self._watches[wd]
        del self._watches_by_path[path]
        return True


    def has_watch(self, path):
        """
        Return if the given path is currently watched by the inotify
        object.
        """
        path = os.path.realpath(path)
        return path in self._watches_by_path


    def get_watches(self):
        """
        Returns a list of all paths monitored by the object.
        """
        return self._watches_by_path.keys()

    
    def _handle_data(self):
        data = os.read(self._fd, 32768)
        self._read_buffer += data
        is_move = None
        
        while True:
            if len(self._read_buffer) < 16:
                if is_move:
                    # We had a MOVED_FROM without MOVED_TO. Too bad, just send
                    # the MOVED_FROM without target
                    wd, mask, cookie, path = is_move
                    self._watches[wd][0].emit(mask, path)
                    self.signals["event"].emit(mask, path)
                break

            wd, mask, cookie, size = struct.unpack("LLLL", self._read_buffer[0:16])
            if size:
                name = self._read_buffer[16:16+size].rstrip('\0')
            else:
                name = None

            self._read_buffer = self._read_buffer[16+size:]
            if wd not in self._watches:
                continue

            path = self._watches[wd][1]
            if name:
                path = os.path.join(path, name)

            if mask & INotify.MOVED_FROM:
                # This is a MOVED_FROM. Don't emit the signals now, let's wait
                # for a MOVED_TO.
                is_move = wd, mask, cookie, path
                continue
            if is_move:
                # Last check was a MOVED_FROM. So if this is a MOVED_TO and the
                # cookie matches, emit both paths. If not, send two signals.
                if mask & INotify.MOVED_TO and cookie == is_move[2]:
                    # Great, they match. Fire a MOVE signal with both paths.
                    # Use the all three signals (global, from, to)
                    mask |= INotify.MOVED_FROM
                    self._watches[is_move[0]][0].emit(mask, is_move[3], path)
                    self._watches[wd][0].emit(mask, is_move[3], path)
                    self.signals["event"].emit(mask, is_move[3], path)
                    is_move = None
                    continue
                # No match, fire the is_move signal now
                wd, cookie, path = is_move
                self._watches[is_move[0]][0].emit(is_move[1], is_move[3])
                self.signals["event"].emit(is_move[1], is_move[3])
                is_move = None

            self._watches[wd][0].emit(mask, path)
            self.signals["event"].emit(mask, path)

            if mask & INotify.DELETE_SELF:
                # Self got deleted, so remove the watch data.
                del self._watches[wd]
                del self._watches_by_path[path]


if _inotify:
    # Copy constants from _inotify to INotify
    for attr in dir(_inotify):
        if attr[0].isupper():
            setattr(INotify, attr, getattr(_inotify, attr))

    INotify.WATCH_MASK = INotify.MODIFY | INotify.ATTRIB | INotify.DELETE | \
                         INotify.CREATE | INotify.DELETE_SELF | INotify.UNMOUNT | \
                         INotify.MOVE

    INotify.CHANGE     = INotify.MODIFY | INotify.ATTRIB
    
