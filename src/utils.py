# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# utils.py - Miscellaneous system utilities
# -----------------------------------------------------------------------------
# $Id: utils.py 1373 2006-03-31 15:49:37Z dmeyer $
#
# -----------------------------------------------------------------------------
# Copyright (C) 2005 Dirk Meyer, Jason Tackaberry
#
# First Edition: Jason Tackaberry <tack@sault.org>
# Maintainer:    Jason Tackaberry <tack@sault.org>
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

__all__ = [ ]

import sys, os, stat, logging

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


def daemonize(stdin = '/dev/null', stdout = '/dev/null', stderr = None, pidfile=None, exit = True):
    """
    Does a double-fork to daemonize the current process using the technique
    described at http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16 .

    If exit is True (default), parent exits immediately.  If false, caller will receive
    the pid of the forked child.
    """

    # First fork.
    try: 
        pid = os.fork() 
        if pid > 0: 
            if exit:
                # Exit from the first parent.
                sys.exit(0)

            # Wait for child to fork again (otherwise we have a zombie)
            os.waitpid(pid, 0)
            return pid
    except OSError, e: 
        log.error("Initial daemonize fork failed: %d, %s\n" % (e.errno, e.strerror))
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
        log.error("Second daemonize fork failed: %d, %s\n" % (e.errno, e.strerror))
        sys.exit(1)
    
    # Create new standard file descriptors.
    if not stderr: 
        stderr = stdout
    stdin = file(stdin, 'r')
    stdout = file(stdout, 'a+')
    stderr = file(stderr, 'a+', 0)
    if pidfile: 
        file(pidfile, 'w+').write("%d\n" % os.getpid())
    
    # Remap standard fds.
    os.dup2(stdin.fileno(), sys.stdin.fileno())
    os.dup2(stdout.fileno(), sys.stdout.fileno())
    os.dup2(stderr.fileno(), sys.stderr.fileno())

    return 0
