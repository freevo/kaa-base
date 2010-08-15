import sys
import distutils.util


def get_build_directory():
    """
    Returns current build-lib directory.
    """
    return "lib.%s-%s" % (distutils.util.get_platform(), sys.version[0:3])
