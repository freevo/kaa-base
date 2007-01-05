# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# config.py - config file reader
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2006 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
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

__all__ = [ "Var", "Group", "Dict", "List", "Config" ]

# Python imports
import os
import re
import copy
import logging
import stat
from new import classobj

# kaa.base modules
from strutils import str_to_unicode, unicode_to_str, get_encoding
from kaa.notifier import Callback, WeakCallback, WeakTimer, WeakOneShotTimer
from kaa.inotify import INotify

# get logging object
log = logging.getLogger('config')

# align regexp
align = re.compile(u'\n( *)[^\n]', re.MULTILINE)

def _format(text):
    """
    Format a description with multiple lines.
    """
    if text.find('\n') == -1:
        return text.strip()

    # This can happen if you use multiple lines and use the python
    # code formating. So there are spaces at each line. Find the maximum
    # number of spaces to delete.

    # description with more than one line, format the text
    if not text.startswith(u'\n'):
        # add newline at the beginning for regexp
        text = u'\n' + text
    # align desc
    strip = 100
    for m in align.findall(text, re.MULTILINE):
        strip = min(len(m), strip)
    if strip == 100 or strip < 1:
        # nothing found
        return text

    newtext = []
    for line in text.split(u'\n'):
        newtext.append(line[strip+1:])
    return u'\n'.join(newtext)[1:].strip()


class Base(object):
    """
    Base class for all config objects.
    """

    def __init__(self, name='', desc=u'', default=None):
        self._parent = None
        self._name = name
        self._desc = _format(str_to_unicode(desc))
        self._default = default
        self._value = default
        self._monitors = []

    def copy(self):
        """
        Return a deep copy of the object.
        """
        return copy.deepcopy(self)

    def add_monitor(self, callback):
        # Wrap the function or method in a class that will ignore deep copies
        # because deepcopy() is unable to copy callables.
        self._monitors.append(Callback(callback))

    def remove_monitor(self, callback):
        for monitor in self._monitors:
            if callback == monitor:
                self._monitors.remove(monitor)

    def _notify_monitors(self, oldval):
        names = []
        o = self
        while o:
            if o._name:
                if names and names[0][0] == "[":
                    # List/dict index, just concat to previous name.
                    names[0] = o._name + names[0]
                else:
                    names.insert(0, o._name)

            for monitor in o._monitors:
                if not callable(monitor):
                    # Happens when deepcopying, callables don't get copied,
                    # they become None.  So remove them now.
                    o._monitors.remove(monitor)
                if names:
                    name = ".".join(names)
                else:
                    name = None
                monitor(name, oldval, self._value)
            o = o._parent

    def get_parent(self):
        return self._parent


    def __repr__(self):
        return repr(self._value)


class VarProxy(Base):
    """
    Wraps a config variable value, inheriting the actual type of that
    value (int, str, unicode, etc.) and offers add_monitor and remove_monitor
    methods to manage the monitor list of the original Var object.
    """
    def __new__(cls, value = None, monitors = [], parent = None):
        clstype = realclass = type(value)
        if clstype == bool:
            # You can't subclass a boolean, so use int instead.  In practice,
            # this isn't a problem, since __class__ will end up being bool,
            # thanks to __getattribute__, so isinstance(o, bool) will be True.
            clstype = int
        newclass = classobj("VarProxy", (clstype, cls), {
            "__getattribute__": cls.__getattribute__,
            "__str__": cls.__str__,
        })
        if value:
            self = newclass(value)
        else:
            self = newclass()
        self._class = realclass
        return self


    def __init__(self, value = None, monitors = [], parent = None):
        super(Base, self).__init__(default = value)
        self._monitors = monitors
        self._parent = parent

    def __getattribute__(self, attr):
        if attr == "__class__":
            return super(VarProxy, self).__getattribute__("_class")
        return super(VarProxy, self).__getattribute__(attr)

    def __str__(self):
        return self._class.__str__(self)

    def __repr__(self):
        return self._class.__repr__(self)


class Var(Base):
    """
    A config variable.
    """
    def __init__(self, name='', type='', desc=u'', default=None):
        super(Var, self).__init__(name, desc, default)
        if type == '':
            # create type based on default
            if default == None:
                raise AttributeError('define type or default')
            type = default.__class__

        self._type = type


    def _cfg_string(self, prefix, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        # create description
        desc = newline = comment = ''
        if print_desc:
            if self._desc:
                desc = '# %s\n' % unicode_to_str(self._desc).replace('\n', '\n# ')
            newline = '\n'
        if self._value == self._default:
            comment = '# '
        value = unicode_to_str(self._value)
        prefix += self._name
        return '%s%s%s = %s%s' % (desc, comment, prefix, value, newline)


    def _cfg_set(self, value, default=False):
        """
        Set variable to value. If the type is not right, an expection will
        be raised. The function will convert between string and unicode.
        If default is set to True, the default value will also be changed.
        """
        if isinstance(self._type, (list, tuple)):
            if not value in self._type:
                # This could crash, but that is ok
                value = self._type[0].__class__(value)
            if not value in self._type:
                raise AttributeError('Variable must be one of %s' % str(self._type))
        elif not isinstance(value, self._type):
            if self._type == str:
                value = unicode_to_str(value)
            elif self._type == unicode:
                value = str_to_unicode(value)
            elif self._type == bool:
                if not value or value.lower() in ('0', 'false', 'no'):
                    value = False
                else:
                    value = True
            else:
                # This could crash, but that is ok
                value = self._type(value)
        if default:
            self._default = value
        if self._value != value:
            oldval = self._value
            self._value = value
            self._notify_monitors(oldval)
        return value


class Group(Base):
    """
    A config group.
    """
    def __init__(self, schema, desc=u'', name='', desc_type='default'):
        super(Group, self).__init__(name, desc)
        self._dict = {}
        self._vars = []
        self._schema = schema
        # 'default' will print all data
        # 'group' will only print the group description
        self._desc_type = desc_type

        for data in schema:
            if not data._name:
                raise AttributeError('no name given')
            self._dict[data._name] = data
            self._vars.append(data._name)

        # the value of a group is the group itself
        self._value = self

        # Parent all the items in the schema
        for item in schema:
            item._parent = self


    def add_variable(self, name, value):
        """
        Add a variable to the group. The name will be set into the
        given value. The object will _not_ be copied.
        """
        value._name = name
        value._parent = self
        self._dict[name] = value
        self._vars.append(name)


    def _cfg_string(self, prefix, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        ret  = []
        desc = unicode_to_str(self._desc).replace('\n', '\n# ')
        if self._name:
            # add self._name to prefix and add a '.'
            prefix = prefix + self._name + '.'
        print_var_desc = print_desc
        if prefix and not prefix.endswith('].') and print_desc:
            if not desc:
                desc = 'group %s settings' % prefix[:-1]
            ret.append('#\n# %s\n#\n' % desc)
            if not self._desc_type == 'default':
                print_var_desc = False

        for name in self._vars:
            var = self._dict[name]
            if not isinstance(var, Var) or var._desc:
                break
        else:
            print_var_desc = False
        for name in self._vars:
            var = self._dict[name]
            ret.append(var._cfg_string(prefix, print_var_desc))
        if print_desc and not print_var_desc:
            ret.append('')
        return '\n'.join(ret)


    def _cfg_get(self, key):
        """
        Get variable, subgroup, dict or list object (as object not value).
        """
        if not key in self._dict:
            if key.replace('_', '-') in self._dict:
                return self._dict[key.replace('_', '-')]
            raise AttributeError('No attribute %s' % key)
        return self._dict[key]


    def __setattr__(self, key, value):
        """
        Set a variable in the group.
        """
        if key.startswith('_'):
            return object.__setattr__(self, key, value)
        self._cfg_get(key)._cfg_set(value)


    def __getattr__(self, key):
        """
        Get variable, subgroup, dict or list.
        """
        if key.startswith('_'):
            return object.__getattribute__(self, key)
        item = self._cfg_get(key)
        if isinstance(item, Var):
            return VarProxy(item._value, item._monitors, item._parent)

        return item

    def __repr__(self):
        return repr(self._dict)


class Dict(Base):
    """
    A config dict.
    """
    def __init__(self, schema, desc=u'', name='', type=unicode, defaults={}):
        super(Dict, self).__init__(name, desc)
        self._schema = schema
        self._dict = {}
        self._type = type
        # the value of a dict is the dict itself
        self._value = self
        schema._parent = self
        for key, value in defaults.items():
            # FIXME: how to handle complex dict defaults with a dict in
            # dict or group in dict?
            var = self._cfg_get(key)
            var._default = var._value = value
            


    def keys(self):
        """
        Return the keys (sorted by name)
        """
        keys = self._dict.keys()[:]
        keys.sort()
        return keys


    def items(self):
        """
        Return key,value list (sorted by key name)
        """
        return [ (key, self._dict[key]._value) for key in self.keys() ]


    def values(self):
        """
        Return value list (sorted by key name)
        """
        return [ self._dict[key]._value for key in self.keys() ]


    def _cfg_string(self, prefix, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        ret = []
        prefix = prefix + self._name
        if type(self._schema) == Var and print_desc:
            # TODO: more detailed comments, show full spec of var and some examples.
            d = unicode_to_str(self._desc).replace('\n', '\n# ')
            ret.append('#\n# %s\n# %s\n#\n' % (prefix, d))
            print_desc = False
        for key in self.keys():
            ret.append(self._dict[key]._cfg_string(prefix, print_desc))
        if not print_desc:
            ret.append('')
        return '\n'.join(ret)


    def _cfg_get(self, index, create=True):
        """
        Get group or variable with the given index (as object, not value).
        """
        if not isinstance(index, self._type):
            if self._type == str:
                index = unicode_to_str(index)
            elif self._type == unicode:
                index = str_to_unicode(index)
            else:
                # this could crash, we don't care.
                index = self._type(index)
        if not index in self._dict and create:
            newitem = self._dict[index] = self._schema.copy()
            newitem._parent = self
            newitem._name = u"[%s]" % unicode(index)
            if isinstance(newitem, Group):
                for item in newitem._schema:
                    item._parent = newitem
            elif isinstance(newitem, Dict):
                newitem._schema._parent = newitem

        return self._dict[index]


    def get(self, index):
        """
        Get group or variable with the given index. Return None if it does
        not exist.
        """
        try:
            return self._cfg_get(index, False)._value
        except KeyError:
            return None


    def __getitem__(self, index):
        """
        Get group or variable with the given index.
        """
        return self._cfg_get(index)._value


    def __setitem__(self, index, value):
        """
        Access group or variable with the given index.
        """
        self._cfg_get(index)._cfg_set(value)


    def __iter__(self):
        """
        Iterate through keys.
        """
        return self.keys().__iter__()


    def __nonzero__(self):
        """
        Return False if there are no elements in the dict.
        """
        return len(self._dict.keys()) > 0

    def __len__(self):
        """
        Returns number of items in the dict.
        """
        return len(self._dict.keys())


    def __repr__(self):
        return repr(self._dict)


class List(Dict):
    """
    A config list. A list is only a dict with integers as index.
    """
    def __init__(self, schema, desc=u'', name='', defaults=[]):
        defaults_dict = {}
        for key, value in enumerate(defaults):
            defaults_dict[key] = value
        Dict.__init__(self, schema, desc, name, int, defaults_dict)


    def __iter__(self):
        """
        Iterate through values.
        """
        return self.values().__iter__()

    def __repr__(self):
        return repr(self._dict.values())


class Config(Group):
    """
    A config object. This is a group with functions to load and save a file.
    """
    def __init__(self, schema, desc=u'', name=''):
        Group.__init__(self, schema, desc, name)
        self._filename = None
        self._bad_lines = []

        # Whether or not to autosave config file when options have changed
        self._autosave = None
        self._autosave_timer = WeakOneShotTimer(self.save)
        self.set_autosave(True)

        # If we are watching the config file for changes.
        self._watching = False
        self._watch_mtime = 0
        self._watch_timer = WeakTimer(self._check_file_changed)
        self._inotify = None


    def copy(self):
        """
        Make a deepcopy of the config.  Reset the filename so we don't clobber
        the original config object's config file, and recreate the timers for
        the new object.
        """
        copy = Group.copy(self)
        copy._filename = None
        copy._watch_timer = WeakTimer(copy._check_file_changed)
        copy._autosave_timer = WeakOneShotTimer(copy.save)
        return copy


    def save(self, filename=None):
        """
        Save file. If filename is not given use filename from last load.
        """
        if not filename:
            if not self._filename:
                raise ValueError, "Filename not specified and no default filename set."
            filename = self._filename

        if os.path.dirname(filename) and not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))

        self._autosave_timer.stop()
        f = open(filename, 'w')
        f.write('# -*- coding: %s -*-\n' % get_encoding().lower())
        f.write('# *************************************************************\n')
        f.write('# This file is auto-generated\n#\n')
        f.write('# The possible variables are commented out with the default\n')
        f.write('# values. Removing lines has no effect, they will be added\n')
        f.write('# again when this file is saved again. Changing the order of\n')
        f.write('# the items will also be changed back on the next write.\n')
        # FIXME: custom comments lost, would be nice if they were kept.  Might
        # be tricky to fix.
        f.write('# Any custom comments will also be removed.\n')
        if self._bad_lines:
            f.write('#\n# See the end of the file for bad lines ignored when the file\n')
            f.write('# was last saved.\n')
        f.write('# *************************************************************\n\n')
        f.write(self._cfg_string(''))
        if self._bad_lines:
            f.write('\n\n\n')
            f.write('# *************************************************************\n')
            f.write('# The following lines caused some errors and were ignored\n')
            f.write('# Possible reasons are removed variables or bad configuration\n')
            f.write('# *************************************************************\n\n')
            for error in self._bad_lines:
                f.write('# %s\n%s\n\n' % error)
        f.close()


    def load(self, filename = None, remember = True):
        """
        Load config from a config file.
        """
        local_encoding = get_encoding()
        if not filename:
            if not self._filename:
                raise ValueError, "Filename not specified and no default filename set."
            filename = self._filename
        elif remember:
            self._filename = filename
        line_regexp = re.compile('^([a-zA-Z0-9_]+|\[.*?\]|\.)+ *= *(.*)')
        key_regexp = re.compile('(([a-zA-Z0-9_]+)|(\[.*?\]))')

        if not os.path.isfile(filename):
            # filename not found
            return False

        # Disable autosaving while we load the config file.
        autosave_orig = self.get_autosave()
        self.set_autosave(False)

        f = open(filename)
        for line in f.readlines():
            line = line.strip()
            if line.startswith('# -*- coding:'):
                # a encoding is set in the config file, use it
                try:
                    encoding = line[14:-4]
                    ''.encode(encoding)
                    local_encoding = encoding
                except:
                    # bad encoding, ignore it
                    pass
            # convert lines based on local encoding
            line = unicode(line, local_encoding)
            if line.find('#') >= 0:
                line = line[:line.find('#')]
            line = line.strip()
            if not line:
                continue

            # split line in key = value
            m = line_regexp.match(line.strip())
            if not m:
                error = ('Unable to parse the line', line.encode(local_encoding))
                if not error in self._bad_lines:
                    log.warning('%s: %s' % error)
                    self._bad_lines.append(error)
                continue
            value = m.groups()[1]
            if value:
                key = line[:-len(value)].rstrip(' =')
            else:
                key = line.rstrip(' =')
            try:
                keylist = [x[0] for x in key_regexp.findall(key.strip()) if x[0] ]
                object = self
                while len(keylist) > 1:
                    key = keylist.pop(0)
                    if key.startswith('['):
                        object = object[key[1:-1]]
                    else:
                        object = getattr(object, key)
                key = keylist[0]
                value = value.strip()
                if isinstance(object, (Dict, List)):
                    object[key[1:-1]] = value
                else:
                    setattr(object, key, value)
            except Exception, e:
                error = (str(e), line.encode(local_encoding))
                if not error in self._bad_lines:
                    log.warning('%s: %s' % error)
                    self._bad_lines.append(error)
        f.close()
        self.set_autosave(autosave_orig)
        self._watch_mtime = os.stat(filename)[stat.ST_MTIME]
        return len(self._bad_lines) == 0


    def get_filename(self):
        """
        Return the current used filename.
        """
        return self._filename

    def set_filename(self, filename):
        """
        Set the default filename for this config.
        """
        self._filename = filename


    def get_autosave(self):
        """
        Fetches the current autosave value.
        """
        return self._autosave

    def set_autosave(self, autosave = True):
        """
        Sets whether or not to automatically save configuration changes.
        If True, will write the config file set by set_filename 5 seconds
        after the last config value update.
        """
        if autosave and not self._autosave:
            self.add_monitor(WeakCallback(self._config_changed_cb))
        elif not autosave and self._autosave:
            self.remove_monitor(WeakCallback(self._config_changed_cb))
            self._autosave_timer.stop()
        self._autosave = autosave


    def _config_changed_cb(self, name, oldval, newval):
        if self._filename:
            # Start/restart the timer to save in 5 seconds.
            self._autosave_timer.start(5)

    def watch(self, watch = True):
        """
        If argument is True (default), adds a watch to the config file and will
        reload the config if it changes.  If INotify is available, use that,
        otherwise stat the file every 3 seconds.

        If argument is False, disable any watches.
        """
        if not watch and not self._inotify:
            try:
                self._inotify = INotify()
            except SystemError:
                pass
            
        assert(self._filename)
        if self._watch_mtime == 0:
            self.load()

        if not watch and self._watching:
            if self._inotify:
                self._inotify.ignore(self._filename)
            self._watch_timer.stop()
            self._watching = False

        elif watch and not self._watching:
            if self._inotify:
                try:
                    signal = self._inotify.watch(self._filename, INotify.MODIFY)
                    signal.connect_weak(self._file_changed)
                except IOError:
                    # Adding watch falied, use timer to wait for file to
                    # appear.
                    self._watch_timer.start(3)
            else:
                self._watch_timer.start(3)

            self._watching = True


    def _check_file_changed(self):
        try:
            mtime = os.stat(self._filename)[stat.ST_MTIME]
        except:
            # Config file not available.
            return

        if self._inotify:
            # Config file is now available, stop this timer and add INotify
            # watch.
            self.watch(False)
            self.watch()

        if mtime != self._watch_mtime:
            return self._file_changed(INotify.MODIFY, self._filename)


    def _file_changed(self, mask, path):
        if mask & (INotify.MODIFY | INotify.ATTRIB):
            self.load()
        elif mask & INotify.DELETE_SELF:
            # Edited with vim?  Check immediately.
            WeakOneShotTimer(self._check_file_changed).start(0.1)
            # Add a slower timer in case it doesn't reappear right away.
            self._watch_timer.start(3)

