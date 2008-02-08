# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# utils.py - Miscellaneous system utilities
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2006 Dirk Meyer, Jason Tackaberry
#
# First Edition: Jason Tackaberry <tack@urandom.ca>
# Maintainer:    Jason Tackaberry <tack@urandom.ca>
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

__all__ = [ ]

import sys
import os
import stat
import time
import logging

import kaa
import _utils

# get logging object
log = logging.getLogger('kaa')


def which(file, path = None):
    """
    Does what which(1) does: searches the PATH for a given file
    name and returns a list of matches.
    """
    if not path:
        path = os.getenv("PATH")

    for p in path.split(":"):
        fullpath = os.path.join(p, file)
        try:
            st = os.stat(fullpath)
        except OSError:
            continue

        if os.geteuid() == st[stat.ST_UID]:
            mask = stat.S_IXUSR
        elif st[stat.ST_GID] in os.getgroups():
            mask = stat.S_IXGRP
        else:
            mask = stat.S_IXOTH

        if stat.S_IMODE(st[stat.ST_MODE]) & mask:
            return fullpath

    return None


class Lock(object):
    def __init__(self):
        self._read, self._write = os.pipe()

    def release(self, exitcode):
        os.write(self._write, str(exitcode))
        os.close(self._read)
        os.close(self._write)

    def wait(self):
        exitcode = os.read(self._read, 1)
        os.close(self._read)
        os.close(self._write)
        return int(exitcode)

    def ignore(self):
        os.close(self._read)
        os.close(self._write)


def daemonize(stdin = '/dev/null', stdout = '/dev/null', stderr = None,
              pidfile=None, exit = True, wait = False):
    """
    Does a double-fork to daemonize the current process using the technique
    described at http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16 .

    If exit is True (default), parent exits immediately.  If false, caller will receive
    the pid of the forked child.
    """

    lock = 0
    if wait:
        lock = Lock()

    # First fork.
    try:
        pid = os.fork()
        if pid > 0:
            if wait:
                exitcode = lock.wait()
                if exitcode:
                    sys.exit(exitcode)
            if exit:
                # Exit from the first parent.
                sys.exit(0)

            # Wait for child to fork again (otherwise we have a zombie)
            os.waitpid(pid, 0)
            return pid
    except OSError, e:
        log.error("Initial daemonize fork failed: %d, %s\n",
                  e.errno, e.strerror)
        sys.exit(1)

    os.chdir("/")
    os.setsid()

    # Second fork.
    try:
        pid = os.fork()
        if pid > 0:
            # Exit from the second parent.
            sys.exit(0)
    except OSError, e:
        log.error("Second daemonize fork failed: %d, %s\n", e.errno, e.strerror)
        sys.exit(1)

    # Create new standard file descriptors.
    if not stderr:
        stderr = stdout
    stdin = file(stdin, 'r')
    stdout = file(stdout, 'a+')
    stderr = file(stderr, 'a+', 0)
    if pidfile:
        pidfile = file(pidfile, 'w+')
        pidfile.write("%d\n" % os.getpid())
        pidfile.close()

    # Remap standard fds.
    os.dup2(stdin.fileno(), sys.stdin.fileno())
    os.dup2(stdout.fileno(), sys.stdout.fileno())
    os.dup2(stderr.fileno(), sys.stderr.fileno())

    return lock


def is_running(name):
    """
    Check if the program with the given name is running. The program
    must have called set_running itself. Returns the pid or 0.
    """
    if not os.path.isfile(kaa.tempfile('run/' + name)):
        return 0
    run = open(kaa.tempfile('run/' + name))
    pid = run.readline().strip()
    cmdline = run.readline()
    run.close()
    if not os.path.exists('/proc/%s/cmdline' % pid):
        return 0
    if open('/proc/%s/cmdline' % pid).readline() == cmdline:
        return int(pid)
    return 0


def set_running(name, modify = True):
    """
    Set this program as running with the given name.  If modify is True, 
    the process name is updated as described in set_process_name().
    """
    cmdline = open('/proc/%s/cmdline' % os.getpid()).readline()
    run = open(kaa.tempfile('run/' + name), 'w')
    run.write(str(os.getpid()) + '\n')
    run.write(cmdline)
    run.close()
    if modify:
        _utils.set_process_name(name, len(cmdline))


def set_process_name(name):
    """
    On Linux systems later than 2.6.9, this function sets the process name as it
    appears in ps, and so that it can be found with killall.
    
    Note: name will be truncated to the cumulative length of the original
    process name and all its arguments; once updated, passed arguments will no
    longer be visible.
    """
    cmdline = open('/proc/%s/cmdline' % os.getpid()).readline()
    _utils.set_process_name(name, len(cmdline))


def get_plugins(path, include_files=True, include_directories=True):
    """
    Get a list of plugins in the given plugin directory. The 'path' argument
    can also be a full path of an __init__ file.
    """
    if os.path.isfile(path):
        path = os.path.dirname(path)
    result = []
    for plugin in os.listdir(path):
        for ext in ('.py', '.pyc', '.pyo'):
            if plugin.endswith(ext) and include_files:
                plugin = plugin[:-len(ext)]
                break
        else:
            if not include_directories or not os.path.isdir(os.path.join(path, plugin)):
                continue
        if not plugin in result and not plugin == '__init__':
            result.append(plugin)
    return result


class Singleton(object):
    """
    Create Singleton object from classref on demand.
    """

    class MemberFunction(object):
        def __init__(self, singleton, name):
            self._singleton = singleton
            self._name = name

        def __call__(self, *args, **kwargs):
            return getattr(self._singleton(), self._name)(*args, **kwargs)
        

    def __init__(self, classref):
        self._singleton = None
        self._class = classref

    def __call__(self):
        if self._singleton is None:
            self._singleton = self._class()
        return self._singleton

    def __getattr__(self, attr):
        if self._singleton is None:
            return Singleton.MemberFunction(self, attr)
        return getattr(self._singleton, attr)
