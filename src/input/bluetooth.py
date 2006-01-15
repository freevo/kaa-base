# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# bluetooth.py - Bluetooth input module
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.input - Kaa input subsystem
# Copyright (C) 2005-2006 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# Please see the file doc/AUTHORS for a complete list of authors.
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

# python imports
import re

try:
    # We use the _bluetooth module from pybluez. No need to use the
    # bluetooth.py wrapper for this file, in fact, it would conflict
    # with this file here because we use the same filename.
    import _bluetooth as bt
except ImportError:
    # Oops, pybluez is not installed.
    raise ImportError('pybluez no installed')

# kaa.notifier imports
from kaa.notifier import SocketDispatcher, IO_WRITE, WeakOneShotTimer, Signal

class Bluetooth(object):
    """
    Bluetooth connection handling to use a mobile phone as input. The class has
    signals for reading keys pressed on a phone, connted and disconnected.
    You need to supply a hardware address and channel for the serial service
    to the constructur. Use 'hcitool scan' to find the hardware address of the
    phone and 'sdptool  browse <addr>' to get the channel id of the SerialPort
    service.
    """
    def __init__(self, addr):
        self._sock = None
        self._addr = addr
        self.signals = {
            'key': Signal(),
            'connected': Signal(),
            'disconnected': Signal() }
        self._connect()
        self._regexp = re.compile(r"\+CKEV: *(.*?),(\w)")


    def _connect(self):
        """
        Try to connect to the device.
        """
        if self._sock:
            self._disconnect()

        self._sock = bt.btsocket(bt.RFCOMM)

        for port in range(1,31):
            try:
                self._sock.bind(('', port))
                break
            except Exception, e:
                pass
        else:
            raise IOError('unable to bind bluetooth device')

        self._sock.setblocking(0)
        try:
            self._sock.connect(self._addr)
        except Exception, e:
            if e.args[0] == 11:
                # doing the connect, just wait until we can write
                SocketDispatcher(self._write).register(self._sock.fileno(), IO_WRITE)
            elif e.args[0] == 16:
                # busy, try again later
                self._sock = None
                WeakOneShotTimer(self._connect).start(1)
            else:
                raise IOError(e.args)


    def _disconnect(self):
        """
        Disconnect from the device.
        """
        if not self._sock:
            return
        self._sock.close()
        self._sock = None


    def _write(self):
        """
        Ready to send data. This is only needed to know when the connect function
        is done and we are ready for reading or have an error.
        """
        try:
            data = self._sock.recv(1)
        except Exception, e:
            if e.args[0] == 112:
                # host is down, try again later
                self._sock = None
                WeakOneShotTimer(self._connect).start(1)
                return False
            elif e.args[0] == 11:
                # no data yet, this is ok
                pass
            else:
                raise IOError(e.args)

        self.signals['connected'].emit()
        SocketDispatcher(self._read).register(self._sock.fileno())
        return False


    def _read(self):
        """
        Read data from the device and convert into key codes.
        """
        try:
            data = self._sock.recv(512)
        except Exception, e:
            if e.args[0] == 110:
                # timeout
                self.signals['disconnected'].emit()
                self._connect()
                return False
            else:
                raise IOError(e.args)

        if not data:
            self.signals['disconnected'].emit()
            self._connect()
            return False
        else:
            if self._regexp.search(data):
                key, arg = self._regexp.search(data).groups()
                if not arg == '0':
                    # send key signal
                    self.signals['key'].emit(key)
            return True


    def __del__(self):
        """
        Disconnect on deletion of the object.
        """
        self._disconnect()



if __name__ == "__main__":
    # some test code
    import kaa

    def debug(msg):
        print msg

    b = Bluetooth(('00:01:E3:6D:1A:18', 1))
    b.signals['key'].connect(debug)
    b.signals['connected'].connect(debug, 'connected')
    b.signals['disconnected'].connect(debug, 'disconnected')

    kaa.main()
