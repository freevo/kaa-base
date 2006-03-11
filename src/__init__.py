import os
import stat

# import logger to update the Python logging module
import logger

# import some basic notifier functions
from kaa.notifier import signals, loop as main, shutdown

# strutils
import strutils

TEMP = '/tmp/kaa-%s' % os.getuid()

if os.path.isdir(TEMP):
    # temp dir is already there, check permissions
    if os.path.islink(TEMP):
        raise IOError('Security Error: %s is a link, please remove')
    if stat.S_IMODE(os.stat(TEMP)[stat.ST_MODE]) != 0700:
        raise IOError('Security Error: %s has wrong permissions, please remove')
    if os.stat(TEMP)[stat.ST_UID] != os.getuid():
        raise IOError('Security Error: %s does not belong to you, please remove')
else:
    os.mkdir(TEMP, 0700)

