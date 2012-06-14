# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# setup.py - Setup script for kaa.base
# -----------------------------------------------------------------------------
# Copyright 2005-2012 Dirk Meyer, Jason Tackaberry
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

MODULE = 'base'
VERSION = '0.99.2'

# python imports
import sys
import os
import time
import platform

# We require python 2.5 or later, so complain if that isn't satisfied.
if sys.hexversion < 0x02050000:
    print('Python 2.5 or later required.')
    sys.exit(1)

# TODO: remove below at some suitable time in the future.
#
# Older version of kaa.base (0.6.0 or earlier) installed all package files
# directly under kaa/ whereas newer versions install under kaa/base/
#
# First chdir out of the src directory, which seems to confuse setuptools,
# and get a list of top-level kaa namespace paths.
cwd = os.getcwd()
os.chdir('/tmp')
paths = os.popen("%s -c 'import kaa; print \"\\x00\".join(kaa.__path__)' 2>/dev/null" % sys.executable).readline()
paths = paths.strip().split('\x00')
# We should not find a kaa.base module (e.g. rpc.py) in any of these paths.
# If we do, it means an old version is present.
conflicts = [p for p in paths if os.path.exists(os.path.join(p, 'rpc.py'))]
if conflicts:
    print('ERROR: detected conflicting files from an old kaa.base version.\n\n'
          "To fix, you'll need to run:\n"
          '   $ sudo rm -rf build %s\n\n'
          "Once you delete #2, you'll need to reinstall all the kaa\n"
          'sub-modules you use.' % ' '.join(conflicts))
    sys.exit(1)
os.chdir(cwd)

# If kaa.base is already installed as an egg and we're now attempting to
# install without --egg, we error out now, because this won't work (the
# egg package will always get imported).
eggs = [p for p in paths if '.egg/' in p]
if eggs and 'install' in sys.argv and not '--egg' in sys.argv:
    print('ERROR: attempting to install a non-egg version of kaa.base, but the following\n'
          'kaa eggs were found:\n')
    for egg in eggs:
        print('  * ' + egg)
    print('\nEither remove the current kaa egg(s) or install now with --egg')
    sys.exit(1)

# Remove anything to do with kaa from the path.  We want to use kaa.distribution
# from the source tree, not any previously installed kaa.base.
#
# Moreover, any installed kaa eggs will be a problem, because they install
# kaa/__init__.py stubs that declare the kaa namespace _and_ import kaa.base,
# which could get imported when kaa.distribution.core imports setuptools (because
# importing setuptools implicitly imports all declared namespace packages).
#
# So to avoid any problems, remove anything kaa from the path, since we don't
# need it.
[sys.path.remove(x) for x in sys.path[:] if '/kaa' in x and x != os.getcwd()]

# Now import the src directory and masquerade it as kaa and kaa.base modules so
# we can import distribution.core.
import src
sys.modules['kaa'] = sys.modules['kaa.base'] = src

# And now import it from the source tree.
from kaa.distribution.core import Extension, setup

extensions = []

objectrow_ext = Extension('kaa.base._objectrow', ['src/extensions/objectrow.c'])
if objectrow_ext.has_python_h():
    extensions.append(objectrow_ext)

if sys.hexversion < 0x02060000:
    # Fixed os.listdir for Python 2.5.  This module is optional for Python 2.5
    # (only installed if headers/libs are available) and not compiled for later
    # versions.
    utils_ext = Extension('kaa.base._utils', ['src/extensions/utils.c'])
    if utils_ext.has_python_h():
        extensions.append(utils_ext)

# Automagically construct version.  If installing from a git clone, the
# version is based on the number of revisions since the last tag.  Otherwise,
# if PKG-INFO exists, assume it's a dist tarball and pull the version from
# that.
version = VERSION
if os.path.isdir('.git'):
    # Fetch all revisions since last tag.  The first item is the current HEAD object name
    # and the last is the tag object name.
    revs = os.popen('git rev-list --all | grep -B9999  `git rev-list --tags --max-count=1`').read().splitlines()
    if len(revs) > 1:
        # We're at least one commit past the last tag, so this is considered a
        # dev release.
        version = '%sdev-%d-%s' % (VERSION, len(revs)-1, revs[0][:8])
elif os.path.isfile('PKG-INFO'):
    ver = [l.split(':')[1].strip() for l in open('PKG-INFO') if l.startswith('Version')]
    if ver:
        version = ver[0]
else:
    # Lack of PKG-INFO means installation was not from an official dist bundle,
    # so treat it as a development version.
    version += 'dev'

setup(
    module = MODULE,
    version = version,
    license = 'LGPL',
    url = 'http://api.freevo.org/kaa-base/',
    summary = 'An application framework specializing in asynchronous programming.',
    description  = 'kaa.base is an LGPL-licensed generic application framework, providing the '
                   'foundation for other modules within Kaa, and can be used in any type of project, '
                   'from small event-driven tools, to larger, complex applications.',
    rpminfo = {
        'requires': 'glib2 >= 2.6.0, python-sqlite2 >= 2.3.0, libxml2-python >= 2.6.0',
        'build_requires': 'glib2-devel >= 2.6.0, python-devel >= 2.5.0'
    },
    ext_modules = extensions,
    opts_2to3 = {
        # Everything listed in 'exclude' is imported directly here (for distribution),
        # so it must compile with both python 2.6 and 3.x.
        'exclude': ['distribution/*', 'saxutils.py', 'strutils.py'],
        'nofix': {
            '*.py': ['import'],
            'utils.py': ['filter'],
            'io.py': ['throw'],
            'rpc.py': ['throw'],
        }
    },
    auto_changelog = True,
    # Don't declare kaa.base as part of the kaa namespace.  Doing so will
    # suppress installation of kaa/__init__.py when installing with pip.  This
    # needs to be installed with kaa.base in order to make our namespace hack
    # work (where everything in kaa.base is under kaa).
    # namespace_packages = ['kaa']
)
