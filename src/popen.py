# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# popen.py - process control
# -----------------------------------------------------------------------------
# $Id$
#
# This module defines a process class similar to the once defined in popen2
# except that this class is aware of the mainloop.
#
# When creating a Process object you can add files for logging the stdout and
# stderr of the process, you can send data to it and add a callback to be
# called when the process is dead. See the class member functions for more
# details.
#
# By inherting from the class you can also override the functions stdout_cb
# and stderr_cb to process stdout and stderr line by line.
#
# The kill_all function of this class can be called at the end of the programm
# to stop all running processes.
#
# -----------------------------------------------------------------------------
# kaa.base - The Kaa Application Framework
# Copyright (C) 2005-2009 Dirk Meyer, Jason Tackaberry, et al.
#
# Based on code by Krister Lagerstrom and Andreas Büsching
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

__all__ = [ 'Process', 'proclist' ]

# python imports
import os
import sys
import fcntl
import popen2
import glob
import re
import logging

# kaa imports
import nf_wrapper as notifier
from callback import Callback
from signals import Signal
from thread import MainThreadCallback, is_mainthread
from async import InProgress, inprogress
from io import IOMonitor, IO_WRITE

# get logging object
log = logging.getLogger('base')

# FIXME: rewrite :)

class Process(object):
    """
    Base class for started child processes
    """
    def __init__( self, cmd, debugname = None ):
        """
        Init the child process 'cmd'. This can either be a string or a list
        of arguments (similar to popen2). If debugname is given, the stdout
        and stderr will also be written.
        """

        # Setup signal handlers for the process; allows the class to be
        # useful without subclassing.
        self.signals = {
            "stderr": Signal(),
            "stdout": Signal(),
            "raw-stderr": Signal(),
            "raw-stdout": Signal(),
            "completed": Signal(),
        }

        self._cmd = self._normalize_cmd(cmd)
        self._stop_cmd = None
        self._debugname = debugname
        self.__dead = True
        self.stopping = False
        self.__kill_timer = None
        self.child = None
        self.in_progress = None
        self._write_buffer = []
        self._wmon = None
        self._close_stdin = False


    def __inprogress__(self):
        return self.in_progress


    def _normalize_cmd(self, cmd):
        """
        Converts a command string into a list while honoring quoting, or
        removes empty strings if the cmd is a list.
        """
        if cmd == None:
            return []
        if isinstance(cmd, tuple):
            cmd = list(cmd)
        if isinstance(cmd, list):
            # Remove empty strings from argument list.
            while '' in cmd:
                cmd.remove('')
            return cmd

        assert(isinstance(cmd, str))

        # This might be how you'd do it in C. :)
        cmdlist = []
        curarg = ""
        waiting = None
        last = None
        for c in cmd:
            if (c == ' ' and not waiting) or c == waiting:
                if curarg:
                    cmdlist.append(curarg)
                    curarg = ""
                waiting = None
            elif c in ("'", '"') and not waiting and last != '\\':
                waiting = c
            else:
                curarg += c
            last = c

        if curarg:
            cmdlist.append(curarg)

        return cmdlist


    def start(self, args = None):
        """
        Starts the process.  If args is not None, it can be either a list or
        string, as with the constructor, and is appended to the command line
        specified in the constructor.
        """
        if not self.__dead:
            raise SystemError, "Process is already running."
        if self.stopping:
            raise SystemError, "Process isn't done stopping yet."

        cmd = self._cmd + self._normalize_cmd(args)
        self.__kill_timer = None
        self.__dead = False
        self.binary = cmd[0]

        self.child = popen2.Popen3( cmd, True, 100 )

        flags = fcntl.fcntl(self.child.tochild.fileno(), fcntl.F_GETFL)
        fcntl.fcntl( self.child.tochild.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK )
        self._wmon = IOMonitor(self._handle_write)
        if self._write_buffer:
            self._wmon.register(self.child.tochild, IO_WRITE)

        log.info('running %s (pid=%s)' % ( self.binary, self.child.pid ) )

        # IO_Handler for stdout
        self.stdout = IO_Handler( 'stdout', self.child.fromchild,
                                  self.signals["stdout"], self.signals['raw-stdout'], self._debugname )
        # IO_Handler for stderr
        self.stderr = IO_Handler( 'stderr', self.child.childerr,
                                  self.signals["stderr"], self.signals['raw-stderr'], self._debugname )

        # add child to watcher
        if not is_mainthread():
            MainThreadCallback(proclist.append)(self, self.__child_died)
        else:
            proclist.append( self, self.__child_died )
        self.in_progress = InProgress()
        return self.in_progress


    def get_pid(self):
        """
        Returns the pid of the child process if it has been spawned.  Otherwise
        returns None
        """
        if self.child:
            return self.child.pid


    def close_stdin(self):
        """
        Closes stdin either now, or once the write buffer has been flushed.
        This might be necessary when, for example, we know we have nothing
        more to send to the child, but the child is waiting for either more
        data or a closed fd before outputting data we're interested in.
        """
        if not self.child:
            return

        if self._wmon and self._wmon.active:
            self._close_stdin = True
        else:
            self.child.tochild.close()


    def write(self, data):
        """
        Queue data for writing when the child is ready to receive it.
        """
        if self.child.tochild.closed:
            raise ValueError("Can't write when stdin has been closed")

        self._write_buffer.append(data)
        if self.child and self._wmon and not self._wmon.active:
            self._wmon.register(self.child.tochild, IO_WRITE)


    def _handle_write(self):
        if not self.child:
            # The child process might have died before we had a chance to
            # flush the write buffer.
            del self._write_buffer[:]
            return False

        try:
            while self._write_buffer:
                data = self._write_buffer[0]
                sent = os.write(self.child.tochild.fileno(), data)
                # If we got here, no exception was raised, so we can pop the
                # data from the buffer.
                self._write_buffer.pop(0)
                if sent != len(data):
                    # Not all data was sent, so push the remaining bytes back and
                    # abort the loop.
                    self._write_buffer.insert(0, data[sent:])
                    break
        except IOError, (errno, msg):
            if errno == 11:
                # Resource temporarily unavailable -- trying to write too
                # much data.
                return
        except OSError, (errno, msg):
            if errno == 32 and self.stopping:
                # Broken pipe.  Child is dead while we are trying to
                # issue stop command.  Safe to ignore.
                pass
            else:
                # Reraise exception.
                raise

        if not self._write_buffer:
            if self._close_stdin:
                self.child.tochild.close()
            return False


    def is_alive( self ):
        """
        Return True if the app is still running
        """
        return self.child and not self.__dead


    def set_stop_command(self, cmd):
        """
        Sets the stop command for this process.  The argument 'cmd' can be
        either a callable or a string.  The command is invoked (if cmd is
        a callback) or the command is written to the child's stdin (if cmd
        is a string or unicode) when the process is being terminated with
        a call to stop().

        Shutdown handlers for the process should be set with this method.
        """
        assert(callable(cmd) or type(cmd) in (str, unicode) or cmd == None)
        self._stop_cmd = cmd


    def stop( self, cmd = None ):
        """
        Stop the child. If 'cmd' is given, this stop command will send to
        the app to stop itself. If this is not working, kill -15 and kill -9
        will be used to kill the app.

        Returns an InProgress which finishes when the process stops.
        """
        if self.stopping:
            return inprogress(self.signals['completed'])

        if not is_mainthread():
            return MainThreadCallback(self.stop, cmd)()

        self.stopping = True
        cmd = cmd or self._stop_cmd

        if self.is_alive() and not self.__kill_timer:
            if cmd:
                log.info('sending exit command to app')
                if callable(cmd):
                    cmd()
                else:
                    self.write(cmd)

                cb = Callback( self.__kill, 15 )
                self.__kill_timer = notifier.timer_add( 3000, cb )
            else:
                cb = Callback( self.__kill, 15 )
                self.__kill_timer = notifier.timer_add( 0, cb )

        return inprogress(self.signals['completed'])


    def __kill( self, signal ):
        """
        Internal kill helper function
        """
        if not self.is_alive():
            self.__dead = True
            self.stopping = False
            return False
        # child needs some assistance with dying ...
        try:
            os.kill( self.child.pid, signal )
        except OSError:
            pass

        if signal == 15:
            cb = Callback( self.__kill, 9 )
        else:
            cb = Callback( self.__killall, 15 )

        self.__kill_timer = notifier.timer_add( 3000, cb )
        return False


    def __killall( self, signal ):
        """
        Internal killall helper function
        """
        if not self.is_alive():
            self.__dead = True
            self.stopping = False
            return False
        # child needs some assistance with dying ...
        try:
            # kill all applications with the string <appname> in their
            # commandline. This implementation uses the /proc filesystem,
            # it is Linux-dependent.
            unify_name = re.compile('[^A-Za-z0-9]').sub
            appname = unify_name('', self.binary)

            cmdline_filenames = glob.glob('/proc/[0-9]*/cmdline')

            for cmdline_filename in cmdline_filenames:
                try:
                    fd = open(cmdline_filename)
                    cmdline = fd.read()
                    fd.close()
                except IOError:
                    continue
                if unify_name('', cmdline).find(appname) != -1:
                    # Found one, kill it
                    pid = int(cmdline_filename.split('/')[2])
                    try:
                        os.kill(pid, signal)
                    except (KeyboardInterrupt, SystemExit), e:
                        os.kill(pid, signal)
                        sys.exit(0)
                    except Exception:
                        pass
        except OSError:
            pass

        log.info('kill -%d %s' % ( signal, self.binary ))
        if signal == 15:
            cb = Callback( self.__killall, 9 )
            self.__kill_timer = notifier.timer_add( 2000, cb )
        else:
            log.critical('PANIC %s' % self.binary)

        return False


    def __child_died( self, pid, status ):
        """
        Callback from watcher when the child died.
        """
        if pid != self.get_pid():
            # We received notification from the watcher concerning another
            # process, so ignore.
            return

        self.__dead = True
        self.stopping = False
        # close IO handler and kill timer
        self.stdout.flush()
        self.stderr.flush()
        self.child.tochild.close()
        self.child = None
        if self.__kill_timer:
            notifier.timer_remove( self.__kill_timer )
        if self.in_progress is not None:
            # no idea why this can happen
            self.in_progress.finish(status >> 8)
            self.in_progress = None
        self.signals['completed'].emit(status >> 8)



class IO_Handler(object):
    """
    Reading data from socket (stdout or stderr)
    """
    def __init__( self, name, fp, signal, raw_signal, logger = None):
        self.name = name
        self.fp = fp
        flags = fcntl.fcntl(self.fp.fileno(), fcntl.F_GETFL)
        fcntl.fcntl( self.fp.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK )
        self.signal = signal
        self.raw_signal = raw_signal
        self.logger = None
        self.saved = ''
        notifier.socket_add( fp, self._handle_input )
        if logger:
            logger = '%s-%s.log' % ( logger, name )
            try:
                try:
                    os.unlink(logger)
                except Exception:
                    pass
                self.logger = open(logger, 'w')
                log.info('logging child to "%s"' % logger)
            except IOError:
                log.warning('Error: Cannot open "%s" for logging' % logger)


    def close( self ):
        """
        Close the IO to the child.
        """
        notifier.socket_remove( self.fp )
        self.fp.close()
        if self.logger:
            self.logger.close()
            self.logger = None


    def flush( self ):
        """
        Read as much as possible and close socket later.
        """
        while self._handle_input( self.fp, True ):
            pass

        
    def _handle_input( self, socket, flushing = False ):
        """
        Handle data input from socket.
        """
        try:
            data = self.fp.read(512*1024)
        except IOError, (errno, msg):
            if errno == 11 and not flushing:
                # Resource temporarily unavailable; if we try to read on a
                # non-blocking descriptor we'll get this message.  If we're
                # being called from flush(), it could be because the child
                # process is dead, in which case this errno will occur but
                # we don't want to return True.
                return True
            data = None
        except ValueError:
            # socket already closed
            return False
            
        if not data:
            log.info('No data on %s for pid %s.' % ( self.name, os.getpid()))
            notifier.socket_remove( self.fp )
            self.fp.close()
            if self.logger:
                self.logger.close()
            # FIXME: we know the child is dead.  Rather than wait for it
            # to be reaped we can call __child_died in Process instance.
            return False

        if self.raw_signal.count():
            self.raw_signal.emit(data)

        if self.signal.count() == 0:
            # Nothing connected to the per-line handler, so need to parse.
            # (And if we're dealing with binary data, it may be important
            # _not to parse.)
            return True

        data  = data.replace('\r', '\n')
        lines = data.split('\n')

        # Only one partial line?
        if len(lines) == 1:
            self.saved += data
            return True

        # Combine saved data and first line, send to app
        if self.logger:
            self.logger.write( self.saved + lines[ 0 ] + '\n' )
        self.signal.emit( self.saved + lines[ 0 ] )
        self.saved = ''

        # There's one or more lines + possibly a partial line
        if lines[ -1 ] != '':
            # The last line is partial, save it for the next time
            self.saved = lines[ -1 ]

            # Send all lines except the last partial line to the app
            for line in lines[ 1 : -1 ]:
                if not line:
                    continue
                if self.logger:
                    self.logger.write( line + '\n' )
                self.signal.emit( line )
        else:
            # Send all lines to the app
            for line in lines[ 1 : ]:
                if not line:
                    continue
                if self.logger:
                    self.logger.write( line + '\n' )
                self.signal.emit( line )
        return True


class Watcher(object):
    def __init__( self ):
        log.info('new process watcher instance')
        self.__processes = {}
        self.__timer = None
        self.status = 'running'

    def append( self, proc, cb ):
        self.__processes[ proc ] = cb
        if not self.__timer:
            log.info('start process watching')
            # FIXME: there is no reason to reap 20 times a second.
            self.__timer = notifier.timer_add(50, self.check)


    def check( self ):
        remove_proc = []

        # check all processes
        for p in self.__processes:

            if isinstance( p.child, popen2.Popen3 ):
                pid = p.child.pid
            else:
                pid = p.pid

            try:
                pid, status = os.waitpid( pid, os.WNOHANG )
            except OSError, (errno, err):
                # FIXME: sometimes we get ECHILD ("No child processes", errno=10) even
                # though we definitely have children.  This happens with pppd, for
                # example.  Need to figure out why.
                remove_proc.append( (p, pid, -1) )
                continue

            if not pid:
                continue

            log.info('Dead child: %s (%s)' % ( pid, status ))
            if status == -1:
                log.error('error retrieving process information from %d' % p)
            elif os.WIFEXITED( status ) or os.WIFSIGNALED( status ) or \
                     os.WCOREDUMP( status ):
                remove_proc.append( (p, pid, status) )

        # remove dead processes
        for p, pid, status in remove_proc:
            if p in self.__processes:
                # call stopped callback
                callback = self.__processes[p]
                # Delete the callback from the processes list before calling
                # it, since it's possible the callback could call append
                # again.
                del self.__processes[p]
                callback(pid, status)

        # check if this function needs to be called again
        if not self.__processes:
            # no process left, remove timer
            self.__timer = None
            log.info('stop process watching')
            return False

        # return True to be called again
        return True


    def stop_all( self ):
        if self.status != 'running':
            return
        # stop all childs without waiting
        for p in self.__processes.keys():
            p.stop()
        self.status = 'stopping'


    def kill_all( self ):
        # prevent recursion
        if not self.status in ('running', 'stopping'):
            return
        # make sure every child is stopped
        self.stop_all()
        self.status = 'stopped'


# global watcher instance
proclist = Watcher()
