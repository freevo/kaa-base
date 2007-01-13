import os
import stat
import tempfile

__all__ = [ 'tempfile' ]

TEMP = '/tmp/kaa-%s' % os.getuid()

if os.path.isdir(TEMP):
    # temp dir is already there, check permissions
    if os.path.islink(TEMP):
        raise IOError('Security Error: %s is a link, aborted')
    if stat.S_IMODE(os.stat(TEMP)[stat.ST_MODE]) != 0700:
        raise IOError('Security Error: %s has wrong permissions, aborted')
    if os.stat(TEMP)[stat.ST_UID] != os.getuid():
        raise IOError('Security Error: %s does not belong to you, aborted')
else:
    os.mkdir(TEMP, 0700)


def tempfile(name, unique=False):
    """
    Return a filename in the secure kaa tmp directory with the given name.
    Name can also be a relative path in the temp directory, directories will
    be created if missing. If unique is set, it will return a unique name based
    on the given name.
    """
    name = os.path.join(TEMP, name)
    if not os.path.isdir(os.path.dirname(name)):
        os.mkdir(os.path.dirname(name))
    if not unique:
        return name
    return tempfile.mktemp(os.path.basename(name), dir=os.path.dirname(name))
